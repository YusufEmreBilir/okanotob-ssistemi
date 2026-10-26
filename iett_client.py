"""Public IETT website adapters. Python standard library only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import unescape
import json
import re
import threading
import time
from urllib.parse import urlencode, unquote
from urllib.request import Request, urlopen

BASE = 'https://iett.istanbul'
ARRIVAL_SOURCES = (BASE, 'https://www.iett.istanbul')
STOPS = ('209482', '209481')
ISTANBUL = timezone(timedelta(hours=3))

def clean(value):
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()

def parse_routes(html):
    return [dict(code=unquote(code), name=clean(name)) for code, name in re.findall(
        r'<a\b[^>]*href="[^\"]*hkod=([^&"\s]+)[^\"]*"[^>]*>[\s\S]*?<p[^>]*>([\s\S]*?)</p>[\s\S]*?</a>', html)]

def parse_arrivals(html, stop, source=BASE):
    result = []
    observed = time.time()
    for body in re.findall(r'''<div\b[^>]*class=["'][^"']*\bcontent\b[^"']*["'][^>]*>([\s\S]*?)</div>''', html):
        code = re.search(r'<span[^>]*>([\s\S]*?)</span>', body)
        label = re.search(r'<b[^>]*>([\s\S]*?)</b>', body)
        if not code or not label:
            continue
        label = clean(label[1])
        clock = re.search(r'\b(\d{1,2}:\d{2})\b', label)
        minutes = re.search(r'(\d+)\s*dk', label)
        destination = re.search(r'<p[^>]*>([\s\S]*?)<b', body)
        if clock or minutes:
            now = datetime.fromtimestamp(observed, ISTANBUL)
            clock_value = clock[1].zfill(5) if clock else (now + timedelta(minutes=int(minutes[1]))).strftime('%H:%M')
            if minutes:
                remaining = int(minutes[1])
            else:
                hour, minute = map(int, clock_value.split(':'))
                remaining = (hour * 60 + minute - now.hour * 60 - now.minute) % 1440
                if remaining > 180:
                    continue  # Do not turn an already-passed prediction into tomorrow's arrival.
            result.append(dict(code=clean(code[1]), stop=stop, time=clock_value,
                               minutes=remaining,
                               uncertain=bool(re.search(r'\bB\b', label)),
                               destination=clean(destination[1]) if destination else '',
                               observed_at=observed, source=source))
    return result

def parse_stop_notices(html):
    notices = {}
    section = re.search(r'''<div[^>]*class=["']duyuru-scroll["'][^>]*>([\s\S]*?)</div>''', html)
    if section:
        for paragraph in re.findall(r'<p[^>]*>([\s\S]*?)</p>', section[1]):
            code = re.search(r'<b[^>]*>([\s\S]*?)</b>', paragraph)
            if code:
                message = clean(paragraph[code.end():]).lstrip(': ').strip()
                if message:
                    notices.setdefault(clean(code[1]), []).append(message)
    return notices

def merge_arrivals(primary, backup):
    """Keep the preferred source's prediction; fill missing route/directions only."""
    keys = {(a['code'], a['stop'], a['destination']) for a in primary}
    return primary + [a for a in backup if (a['code'], a['stop'], a['destination']) not in keys]

def parse_schedule(html):
    result = []
    for table in re.findall(r'<table\b[^>]*class="line-table"[^>]*>([\s\S]*?)</table>', html):
        heading = re.search(r'<th[^>]*colspan="3"[^>]*>([\s\S]*?)</th>', table)
        days = [[], [], []]
        for row in re.findall(r'<tr[^>]*>([\s\S]*?)</tr>', table):
            for index, cell in enumerate(re.findall(r'<td[^>]*>([\s\S]*?)</td>', row)[:3]):
                label = clean(cell)
                clock = re.search(r'\b(\d{1,2}:\d{2})\b', label)
                if clock:
                    days[index].append(dict(time=clock[1].zfill(5), note=label.replace(clock[1], '').strip()))
        for day in days:
            day.sort(key=lambda entry: entry['time'])
        result.append(dict(origin=re.sub(r'\s+KALKIŞ$', '', clean(heading[1]) if heading else ''), days=days))
    return result

def day_index(now=None):
    weekday = (now or datetime.now(ISTANBUL)).weekday()
    return 1 if weekday == 5 else 2 if weekday == 6 else 0

def parse_campus_profiles(html):
    """Associate each special-route timetable with its own ordered stop list."""
    starts = list(re.finditer(r'<div\b[^>]*id="([A-Z0-9]+_[GD]_D\d+)"[^>]*class="tab-line-content"[^>]*>', html))
    profiles = []
    for index, match in enumerate(starts):
        section = html[match.end():starts[index + 1].start() if index + 1 < len(starts) else len(html)]
        table_start = section.find('<table')
        schedules = parse_schedule(section)
        if table_start < 0 or not schedules:
            continue
        stops = []
        for code, body in re.findall(r'<a\b[^>]*href="[^\"]*dkod=(\d+)[^\"]*"[^>]*>([\s\S]*?)</a>', section[:table_start]):
            name = re.sub(r'<span[^>]*>[\s\S]*?</span>', '', body)
            stops.append(dict(code=code, name=re.sub(r'^\d+\.\s*', '', clean(name))))
        targets = [(i, stop) for i, stop in enumerate(stops) if stop['code'] in STOPS]
        if len(stops) < 2 or not targets:
            continue
        for position, stop in targets:
            profiles.append(dict(schedules[0], branch=match[1], stop=stop['code'],
                                 position=position, stop_count=len(stops), destination=stops[-1]['name']))
    return profiles

def parse_default_profiles(html, schedules, code):
    profiles = []
    sections = re.split(r'<div\b[^>]*class="col-md-6 col-12"[^>]*>', html)[1:]
    for index, (section, schedule) in enumerate(zip(sections, schedules)):
        stops = []
        for stop_code, body in re.findall(r'<a\b[^>]*href="[^\"]*dkod=(\d+)[^\"]*"[^>]*>([\s\S]*?)</a>', section):
            name = re.sub(r'<span[^>]*>[\s\S]*?</span>', '', body)
            stops.append(dict(code=stop_code, name=re.sub(r'^\d+\.\s*', '', clean(name))))
        if len(stops) < 2:
            continue
        for position, stop in enumerate(stops):
            if stop['code'] in STOPS:
                profiles.append(dict(schedule, days=[[e for e in day if not e['note']] for day in schedule['days']],
                                     branch=f'{code}_main_{index}', stop=stop['code'], position=position,
                                     stop_count=len(stops), destination=stops[-1]['name']))
    return profiles

def campus_timetables(profiles):
    grouped = {}
    for profile in profiles:
        key = (profile['origin'], profile['destination'])
        schedule = grouped.setdefault(key, dict(origin=profile['origin'] + ' → ' + profile['destination'], days=[[], [], []]))
        for i, day in enumerate(profile['days']):
            schedule['days'][i].extend(day)
    for schedule in grouped.values():
        schedule['days'] = [sorted({(e['time'], e['note']): e for e in day}.values(), key=lambda e: e['time']) for day in schedule['days']]
    return list(grouped.values())

def calculated_arrivals(route, now):
    """Coarse timetable model, NOT a GPS prediction: duration × stop-index fraction."""
    entries = []
    for profile in route.get('campus_profiles', []):
        position = profile['position']
        duration = route.get('duration_minutes')
        if position and not duration:
            continue
        offset = round(duration * position / (profile['stop_count'] - 1)) if position else 0
        margin = max(5, round(offset * .30)) if offset else 0
        # Search a full week so limited weekday-only campus services remain visible.
        for days_ahead in range(-1, 8):
            date = now + timedelta(days=days_ahead)
            for departure in profile['days'][day_index(date)]:
                hour, minute = map(int, departure['time'].split(':'))
                start = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                arrival = start + timedelta(minutes=offset)
                if arrival < now.replace(second=0, microsecond=0):
                    continue
                entries.append(dict(time=arrival.strftime('%H:%M'),
                                    minutes=max(0, round((arrival - now).total_seconds() / 60)),
                                    live=False, estimated=bool(position), margin=margin,
                                    kind='Tarifeden hesaplanan varış' if position else 'Planlı kampüs kalkışı',
                                    destination=profile['destination'], stop=profile['stop'],
                                    arrival_date=arrival.strftime('%Y-%m-%d'), days_ahead=(arrival.date() - now.date()).days,
                                    origin=profile['origin'], departure=departure['time'],
                                    travel_minutes=offset, branch=profile['branch']))
            if entries and any(e['branch'] == profile['branch'] for e in entries):
                break
    return sorted(entries, key=lambda entry: (entry['arrival_date'], entry['time']))

def upcoming(route, now=None, stamp=None):
    now = now or datetime.now(ISTANBUL)
    stamp = time.time() if stamp is None else stamp
    live = []
    for arrival in route.get('arrivals', []):
        age = stamp - arrival['observed_at']
        minutes = arrival['minutes']
        if minutes is not None and 0 <= age < 120 and minutes * 60 >= age - 30:
            live.append(dict(arrival, minutes=max(0, round(minutes - age / 60)),
                             kind='Sinyal belirsiz · İETT' if arrival['uncertain'] else 'Tahmini durak varışı',
                             live=not arrival['uncertain']))
    live.sort(key=lambda entry: (entry['uncertain'], entry['minutes']))
    if live:
        return live
    calculated = calculated_arrivals(route, now)
    if calculated:
        return calculated
    clock = now.strftime('%H:%M')
    for schedule in route.get('schedule', []):
        if 'OKAN' in schedule['origin']:
            entries = []
            for entry in schedule['days'][day_index(now)]:
                if entry['time'] >= clock:
                    hours, mins = map(int, entry['time'].split(':'))
                    entries.append(dict(entry, minutes=hours * 60 + mins - now.hour * 60 - now.minute,
                                        kind='Planlı kampüs kalkışı', live=False, destination=schedule['origin'], stop='209482'))
            return entries
    return []

class IettClient:
    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()

    def request(self, path, ttl=0, form=None, base=BASE):
        key = (base, path, urlencode(form) if form else '')
        with self.lock:
            cached = self.cache.get(key)
        if cached and time.time() - cached[0] < ttl:
            return cached[1]
        data = urlencode(form).encode() if form else None
        headers = {'User-Agent': 'OkanDurak/2.0'}
        if form:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        with urlopen(Request(base + path, data=data, headers=headers), timeout=12) as response:
            value = response.read().decode('utf-8')
        with self.lock:
            self.cache[key] = (time.time(), value)
        return value

    def stop(self, stop):
        result = dict(code=stop, routes=[], arrivals=[], notices={}, arrivals_available=False, errors=[])
        try:
            data = json.loads(self.request('/tr/RouteStationAgent/GetRouteByStation?' + urlencode(dict(dcode=stop, langid=1)), ttl=300))
            result['routes'] = parse_routes(data.get('html', ''))
            if not result['routes']:
                raise ValueError('Hat listesi boş')
        except Exception:
            result['errors'].append(f'{stop}: Hat listesi alınamadı')
        def predictions(base):
            try:
                html = self.request('/tr/RouteStation/GetStationInfo?' + urlencode(dict(dcode=stop, langid=1)), base=base)
                if not re.search(r'line-list|departure-times-header', html):
                    raise ValueError('Beklenmeyen durak yanıtı')
                return parse_arrivals(html, stop, base), parse_stop_notices(html), True
            except Exception:
                return [], {}, False
        # Both public hosts can return different subsets; never overwrite a primary prediction.
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(predictions, ARRIVAL_SOURCES))
        for arrivals, notices, available in responses:
            result['arrivals'] = merge_arrivals(result['arrivals'], arrivals)
            result['arrivals_available'] |= available
            for code, messages in notices.items():
                result['notices'].setdefault(code, []).extend(messages)
        if not result['arrivals_available']:
            result['errors'].append(f'{stop}: Canlı varış alınamadı')
        return result

    def route(self, route, arrivals):
        result = dict(route, arrivals=[a for a in arrivals if a['code'] == route['code']], schedule=[], notices=[], status_available=False, errors=[])
        try:
            result['schedule'] = parse_schedule(self.request('/tr/RouteStation/GetScheduledDepartureTimes', ttl=300, form=dict(hCode=route['code'], lngid=1)))
            if not result['schedule']:
                raise ValueError('Tarife boş')
        except Exception:
            result['errors'].append('Tarife alınamadı')
        try:
            html = self.request('/tr/RouteStation/GetFastStation?' + urlencode(dict(routeid=route['code'], langid=1)), ttl=300)
            result['campus_profiles'] = parse_campus_profiles(html)
            normal = self.request('/tr/RouteStation/GetStationForRoute?' + urlencode(dict(hatkod=route['code'], langid=1)), ttl=300)
            result['campus_profiles'].extend(parse_default_profiles(normal, result['schedule'], route['code']))
            if any(p['position'] for p in result['campus_profiles']):
                page = clean(self.request('/RouteDetail?' + urlencode(dict(hkod=route['code'])), ttl=3600))
                duration = re.search(r'Tek yön sefer süresi:\s*(\d+)\s*dk', page, re.I)
                if duration:
                    result['duration_minutes'] = int(duration[1])
            # The default timetable omits special departures. Include campus profiles in detail.
            if result['campus_profiles']:
                result['schedule'] = campus_timetables(result['campus_profiles'])
        except Exception:
            result['errors'].append('Okan depar tarifesi alınamadı')
        try:
            notices = json.loads(self.request('/tr/RouteStation/GetLineStatus?' + urlencode(dict(rcode=route['code']))))
            if not isinstance(notices, list):
                raise ValueError('Geçersiz duyuru')
            result.update(notices=[clean(n) for n in notices if isinstance(n, str)], status_available=True)
        except Exception:
            result['errors'].append('İptal durumu bilinmiyor')
        return result

    def board(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            stops = list(pool.map(self.stop, STOPS))
        routes = {}
        for stop in stops:
            for route in stop['routes']:
                item = routes.setdefault(route['code'], dict(route, stops=[]))
                item['stops'].append(stop['code'])
        if not routes:
            raise ConnectionError('İETT verisine ulaşılamıyor. Bağlantı yeniden denenecek.')
        arrivals = [arrival for stop in stops for arrival in stop['arrivals']]
        with ThreadPoolExecutor(max_workers=5) as pool:
            data = list(pool.map(lambda route: self.route(route, arrivals), routes.values()))
        for route in data:
            route['arrivals_available'] = all(s['arrivals_available'] for s in stops if s['code'] in route['stops'])
            route['notices'] = list(dict.fromkeys(route['notices'] + [n for s in stops for n in s['notices'].get(route['code'], [])]))
        return dict(routes=sorted(data, key=lambda route: route['code']), updated_at=time.time(),
                    errors=[error for stop in stops for error in stop['errors']] +
                    [route['code'] + ': ' + error for route in data for error in route['errors']])
