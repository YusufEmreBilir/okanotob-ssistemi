"""Live scraper for the public Okan University campus-ring timetable pages."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from html import unescape
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.request import Request, urlopen

from iett_client import ISTANBUL

RING_INDEX = 'https://www.okan.edu.tr/sayfa/7459/ring-seferleri/'
USER_AGENT = 'OkanDurak/1.0 (campus timetable display)'


def clean(value):
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()


def normalized(value):
    value = unicodedata.normalize('NFKD', value)
    return ''.join(ch for ch in value if not unicodedata.combining(ch)).casefold().strip()


def get_html(url):
    request = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(request, timeout=12) as response:
        return response.read().decode('utf-8', 'replace')


def parse_ring_links(html):
    links = []
    for listing in re.findall(r'<ul\b[^>]*class=["\'][^"\']*\bservice-list\b[^"\']*["\'][^>]*>([\s\S]*?)</ul>', html, re.I):
        for href, body in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', listing, re.I):
            title = clean(body)
            parts = [part.strip() for part in title.split(' - ')]
            normalized_parts = [normalized(part) for part in parts]
            if len(parts) < 2 or 'kampus' not in normalized_parts:
                continue
            if normalized_parts[-1] == 'kampus':
                side, endpoints = 'to_campus', parts[:-1]
            elif normalized_parts[0] == 'kampus':
                side, endpoints = 'from_campus', parts[1:]
            else:
                continue
            key = tuple(sorted(normalized(part) for part in endpoints))
            name = ' / '.join(endpoints)
            links.append(dict(key=key, name=name, side=side, title=title,
                              url=href if href.startswith('http') else 'https://www.okan.edu.tr' + href))
    return links


def parse_ring_schedule(html):
    section = re.search(r'<div\b[^>]*id=["\']times["\'][^>]*>([\s\S]*?)</div>', html, re.I)
    if not section:
        return []
    schedules = []
    current_day = 'Tüm günler'
    for row in re.findall(r'<tr\b[^>]*>([\s\S]*?)</tr>', section.group(1), re.I):
        heading = re.search(r'<th\b[^>]*>([\s\S]*?)</th>', row, re.I)
        cell = re.search(r'<td\b[^>]*>([\s\S]*?)</td>', row, re.I)
        if heading:
            current_day = clean(heading.group(1)) or current_day
        if cell:
            times = re.findall(r'(?<!\d)(\d{1,2})[:.](\d{2})(?!\d)', cell.group(1))
            values = sorted({f'{int(hour):02d}:{minute}' for hour, minute in times})
            if values:
                schedules.append(dict(day=current_day, times=values))
    return schedules


def next_departure(direction, now=None):
    now = now or datetime.now(ISTANBUL)
    schedules = direction.get('schedules', [])
    if not schedules:
        return None
    today = now.date()
    for offset in range(8):
        date = today + timedelta(days=offset)
        clock = now.strftime('%H:%M') if offset == 0 else '00:00'
        for schedule in schedules:
            label = normalized(schedule['day'])
            weekday = date.weekday()
            applies = (
                'hafta ici' in label and weekday < 5
                or 'cumartesi' in label and weekday == 5
                or 'pazar' in label and weekday == 6
                or not any(day in label for day in ('hafta ici', 'cumartesi', 'pazar'))
            )
            if not applies:
                continue
            for departure in schedule['times']:
                if offset or departure >= clock:
                    hour, minute = map(int, departure.split(':'))
                    minutes = max(0, int((datetime.combine(date, datetime.min.time(), ISTANBUL)
                                          + timedelta(hours=hour, minutes=minute) - now).total_seconds() // 60))
                    return dict(time=departure, minutes=minutes, days_ahead=offset,
                                day_name=('Bugün' if offset == 0 else 'Yarın' if offset == 1 else
                                          ('Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar')[date.weekday()]))
    return None


class RingClient:
    CACHE_SECONDS = 12 * 60 * 60

    def __init__(self, cache_path=None):
        self.cache_path = Path(cache_path) if cache_path else Path.home() / 'OkanDurak' / 'ring_cache.json'

    def _read_cache(self):
        try:
            data = json.loads(self.cache_path.read_text(encoding='utf-8'))
            if data.get('routes'):
                age = time.time() - data.get('updated_at', 0)
                data['cached'] = age < self.CACHE_SECONDS
                data['stale'] = age >= self.CACHE_SECONDS
                return data
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _save_cache(self, data):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.cache_path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            temp.replace(self.cache_path)
        except OSError:
            pass

    def board(self):
        """Use saved official timetables for 12 hours, then scrape and replace them."""
        cached = self._read_cache()
        if cached and not cached.get('stale'):
            return cached
        try:
            return self._scrape()
        except Exception as exc:
            if cached:
                cached['errors'] = ['Okan sayfası yenilenemedi; kayıtlı tarife gösteriliyor: ' + str(exc)]
                return cached
            raise

    def _scrape(self):
        html = get_html(RING_INDEX)
        links = parse_ring_links(html)
        if not links:
            raise ValueError('Okan ring seferleri sayfasında güzergâh bulunamadı')

        def fetch(link):
            try:
                page = get_html(link['url'])
                schedules = parse_ring_schedule(page)
                if not schedules:
                    raise ValueError('Saat tablosu bulunamadı')
                return link, schedules, None
            except Exception as exc:
                return link, [], str(exc)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(fetch, links))

        groups = {}
        errors = []
        for link, schedules, error in results:
            group = groups.setdefault(link['key'], dict(key=link['key'], name=link['name'], directions=[]))
            group['directions'].append(dict(title=link['title'], side=link['side'],
                                            url=link['url'], schedules=schedules))
            if error:
                errors.append(link['title'] + ': ' + error)
        routes = list(groups.values())
        for route in routes:
            route['directions'].sort(key=lambda item: 0 if item['side'] == 'to_campus' else 1)
        data = dict(routes=routes, updated_at=time.time(), errors=errors, cached=False, stale=False)
        if routes:
            self._save_cache(data)
        return data
