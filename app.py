"""Okan Durak: native Python/Tkinter departure board, no browser/server required."""
import argparse
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import math
from pathlib import Path
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

from iett_client import IettClient, ISTANBUL, day_index, upcoming

BG = '#181818'
CARD = '#222222'
LINE = '#353535'
TEXT = '#e7e7e7'
MUTED = '#999999'
ACCENT = '#bfcede'
AMBER = '#cfac7e'

class App:
    def __init__(self, root, kiosk=False):
        self.root, self.kiosk = root, kiosk
        self.board = None
        self.error = ''
        self.busy = False
        self.closed = False
        self.client = IettClient()
        self.results = queue.Queue()
        self.selected = None
        self.day = day_index()
        self.draw_job = None
        root.title('Okan Durak')
        root.configure(bg=BG)
        root.geometry('1360x760')
        root.minsize(800, 450)
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        root.protocol('WM_DELETE_WINDOW', self.request_close)
        root.bind('<Configure>', self.resized)
        root.bind('<Escape>', self.escape)
        root.bind('<F5>', lambda _: self.refresh())
        root.bind('<Control-Shift-Q>', lambda _: self.admin_exit())
        root.bind('<Control-Shift-q>', lambda _: self.admin_exit())
        if kiosk:
            root.attributes('-fullscreen', True)
            root.attributes('-topmost', True)
            root.bind('<Alt-F4>', lambda _: 'break')
            root.bind('<F11>', lambda _: 'break')
            self.keep_awake(True)
        self.refresh()
        root.after(100, self.poll)
        root.after(1000, self.tick)
        root.after(30000, self.auto_refresh)

    def keep_awake(self, enabled):
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000003 if enabled else 0x80000000)

    def resized(self, event):
        if event.widget is self.root:
            if self.draw_job:
                self.root.after_cancel(self.draw_job)
            self.draw_job = self.root.after(70, self.draw)

    def label(self, x, y, value, size=12, color=TEXT, anchor='nw', width=0, bold=False, tag=None):
        return self.canvas.create_text(x, y, text=value, fill=color, anchor=anchor, width=width,
                                       font=('Segoe UI', max(7, int(size)), 'bold' if bold else 'normal'), tags=tag or ())

    def button(self, x, y, width, title, command, active=False):
        tag = 'button_' + str(self.canvas.find_all()[-1] if self.canvas.find_all() else 0)
        self.canvas.create_rectangle(x, y, x + width, y + 32, fill='#303030' if active else BG, outline='', tags=tag)
        self.label(x + width / 2, y + 16, title, 10, ACCENT if active else MUTED, anchor='center', tag=tag)
        self.canvas.tag_bind(tag, '<Button-1>', lambda _: command())
        self.canvas.tag_bind(tag, '<Enter>', lambda _: self.canvas.configure(cursor='hand2'))
        self.canvas.tag_bind(tag, '<Leave>', lambda _: self.canvas.configure(cursor=''))

    def draw(self):
        self.draw_job = None
        if self.closed:
            return
        c = self.canvas
        c.delete('all')
        w, h = c.winfo_width(), c.winfo_height()
        if w < 100:
            return
        pad = max(18, min(40, w * .025))
        now = datetime.now(ISTANBUL)
        self.label(pad, 22, 'Okan otobüsleri', 14, bold=True)
        self.label(pad, 49, 'Tuzla kampüsü', 9, MUTED)
        self.label(w - pad, 20, now.strftime('%H:%M'), 20, anchor='ne')
        self.label(w - pad, 52, now.strftime('%d.%m.%Y'), 8, MUTED, anchor='ne')
        c.create_line(pad, 82, w - pad, 82, fill=LINE)
        if self.selected:
            self.draw_detail(w, h, pad)
            return
        self.label(pad, 104, 'Kampüs durağına geliş saatleri · Tüm seferler için hatta tıkla.', 9, MUTED, width=w - 2 * pad - 110)
        self.button(w - pad - 95, 94, 95, 'Yenileniyor…' if self.busy else 'Yenile', self.refresh)
        routes = self.board['routes'] if self.board else []
        n = len(routes)
        warnings = []
        warning_font = 9 if w >= 1000 else 8
        for route in routes:
            if route['notices']:
                message = route['code'] + ': ' + ' / '.join(route['notices'])
                probe = self.label(0, 0, message, warning_font, width=w - 2 * pad - 24)
                bounds = c.bbox(probe)
                warnings.append((message, bounds[3] - bounds[1] + 20))
                c.delete(probe)
        warning_height = sum(height for _, height in warnings)
        if not n:
            self.label(w / 2, h / 2, self.error or 'İETT’ye bağlanılıyor…', 17, MUTED, 'center', width=w - 80)
        else:
            gap = max(8, min(18, w * .012))
            cw = (w - 2 * pad - gap * (n - 1)) / n
            top = 155
            bottom = min(h - 95 - warning_height, top + 365)
            ch = bottom - top
            scale = min(1.05, cw / 225, ch / 310)
            for index, route in enumerate(routes):
                x = pad + index * (cw + gap)
                tag = 'route_' + route['code']
                # A transparent-looking hit area keeps the whole column clickable.
                c.create_rectangle(x, top, x + cw, bottom, fill=BG, outline='', tags=tag)
                if index:
                    c.create_line(x - gap / 2, top, x - gap / 2, bottom, fill=LINE)
                inner = max(8, cw * .04)
                self.label(x + inner, top + 6, route['code'], 21 * scale, bold=True, tag=tag)
                # Reserve a fixed area for route labels so every next-arrival time aligns.
                self.label(x + inner, top + 49 * scale, route['name'], 9 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                entries = upcoming(route)
                next_bus = entries[0] if entries else None
                y = top + 100 * scale
                heading = ('Tahmini varış' if next_bus.get('live') else 'Sinyal belirsiz' if next_bus.get('uncertain') else 'Hesaplanan varış' if next_bus.get('estimated') else 'Planlı kampüs kalkışı') if next_bus else 'Tahmini varış'
                self.label(x + inner, y, heading, 9 * scale, MUTED, tag=tag)
                time_label = ('~' if next_bus.get('estimated') else '') + next_bus['time'] if next_bus else '—'
                self.label(x + inner, y + 23 * scale, time_label, 29 * scale, bold=True, tag=tag)
                if next_bus:
                    remaining = 'Durakta / geliyor' if next_bus['minutes'] == 0 else f"{next_bus['minutes']} dk kaldı"
                    if next_bus.get('days_ahead', 0):
                        remaining = 'Yarın' if next_bus['days_ahead'] == 1 else next_bus['arrival_date'][8:10] + '.' + next_bus['arrival_date'][5:7] + ' tarihinde'
                    self.label(x + inner, y + 77 * scale, remaining, 13 * scale, tag=tag)
                    destination = next_bus.get('destination', '').rsplit(' - ', 1)[-1]
                    if next_bus.get('live') or next_bus.get('uncertain'):
                        self.label(x + inner, y + 112 * scale, 'Yön: ' + destination, 8 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                        if ch > 280:
                            self.label(x + inner, y + 147 * scale, 'Kaynak: İETT · ' + next_bus['stop'], 8 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                    elif next_bus.get('estimated'):
                        self.label(x + inner, y + 109 * scale, f"Yaklaşık · ±{next_bus['margin']} dk model payı", 8 * scale, AMBER, width=cw - 2 * inner, tag=tag)
                        if ch > 280:
                            self.label(x + inner, y + 133 * scale, 'Yön: ' + destination + '\nTarife + durak sırası · GPS yok', 8 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                    else:
                        self.label(x + inner, y + 112 * scale, 'Tarifeden · Canlı tahmin değil', 8 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                else:
                    reason = 'İETT şu an araç tahmini paylaşmıyor.' if route.get('arrivals_available', True) else 'Canlı veri bağlantısı kurulamadı.'
                    self.label(x + inner, y + 81 * scale, reason, 9 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                status, color = self.status(route)
                self.label(x + inner, bottom - 57 * scale, status, 8 * scale, color, width=cw - 2 * inner, tag=tag)
                self.label(x + inner, bottom - 27 * scale, 'Tüm saatler', 8 * scale, MUTED, tag=tag)
                c.tag_bind(tag, '<Button-1>', lambda _, code=route['code']: self.open_detail(code))
                c.tag_bind(tag, '<Enter>', lambda _: c.configure(cursor='hand2'))
                c.tag_bind(tag, '<Leave>', lambda _: c.configure(cursor=''))
            warning_y = bottom + 14
            for message, height in warnings:
                c.create_rectangle(pad, warning_y, w - pad, warning_y + height - 5, fill='#29241e', outline='')
                self.label(pad + 12, warning_y + 7, message, warning_font, AMBER, width=w - 2 * pad - 24)
                warning_y += height
        footer = 'İETT / Otomatik yenileme: 30 sn'
        if self.board:
            footer += '  /  Son veri ' + datetime.fromtimestamp(self.board['updated_at'], ISTANBUL).strftime('%H:%M:%S')
        c.create_line(pad, h - 77, w - pad, h - 77, fill=LINE)
        self.label(pad, h - 60, self.error or ('Bazı veriler alınamadı. Tekrar deneniyor.' if self.board and self.board['errors'] else footer), 8, AMBER if self.error else MUTED, width=w - 2 * pad)
        self.label(pad, h - 34, '~ işaretli saatler tarife ve durak sırasından hesaplanır; canlı konum değildir.', 8, MUTED, width=w - 2 * pad - 95)
        self.label(w - pad, h - 34, 'KİOSK' if self.kiosk else 'F5 · Yenile', 8, MUTED, anchor='ne')

    @staticmethod
    def status(route):
        if not route['status_available']:
            return 'İptal bilgisi alınamadı', AMBER
        if any(re.search(r'iptal|yapılama|hizmet verem', n, re.I) for n in route['notices']):
            return 'İptal duyurusu var', '#df9b9b'
        if route['notices']:
            return 'Hat duyurusu var', AMBER
        return 'İptal duyurusu yok', MUTED

    def open_detail(self, code):
        self.selected = code
        self.day = day_index()
        self.draw()

    def close_detail(self):
        self.selected = None
        self.draw()

    def select_day(self, day):
        self.day = day
        self.draw()

    def draw_detail(self, w, h, pad):
        route = next((r for r in self.board['routes'] if r['code'] == self.selected), None)
        if not route:
            self.selected = None
            return
        self.label(pad, 102, route['code'] + '  /  ' + route['name'], 12, TEXT, bold=True, width=w - 2 * pad - 120)
        self.button(w - pad - 95, 98, 95, 'Geri', self.close_detail)
        for i, label in enumerate(('Hafta içi', 'Cumartesi', 'Pazar')):
            self.button(pad + i * 108, 151, 100, label, lambda day=i: self.select_day(day), self.day == i)
        self.label(pad, 201, 'Kampüse uğrayan seferlerin ilk duraktan kalkış saatleri · Ara durak varışı değildir.', 9, MUTED, width=w - 2 * pad)
        notices = '  /  '.join(route['notices'])
        notice_height = 65 if notices else 0
        if notices:
            self.label(pad, h - 85, notices, 9, AMBER, width=w - 2 * pad)
        schedules = route['schedule']
        if not schedules:
            self.label(pad, 255, 'Tarife alınamadı. Biraz sonra yeniden denenecek.', 13, AMBER)
        count = max(1, len(schedules))
        block_width = (w - 2 * pad - 28 * (count - 1)) / count
        now = datetime.now(ISTANBUL).strftime('%H:%M')
        for index, schedule in enumerate(schedules):
            x = pad + index * (block_width + 28)
            self.label(x, 239, schedule['origin'] + ' kalkış', 10, TEXT, width=block_width)
            times = schedule['days'][self.day]
            cols = max(3, int(block_width / 85))
            rows = max(1, math.ceil(len(times) / cols))
            row_h = min(47, max(12, (h - 315 - notice_height) / rows))
            font = max(7, min(16, row_h * .36, block_width / cols * .18))
            if not times:
                self.label(x, 281, 'Bu gün için sefer yayımlanmamış.', 10, MUTED)
            for i, entry in enumerate(times):
                col, row = i % cols, i // cols
                cell_w = block_width / cols
                xx, yy = x + col * cell_w, 279 + row * row_h
                past = self.day == day_index() and entry['time'] < now
                self.canvas.create_rectangle(xx, yy, xx + cell_w - 6, yy + row_h - 5,
                                             fill=BG if past else CARD, outline=LINE)
                self.label(xx + (cell_w - 6) / 2, yy + (row_h - 5) / 2, entry['time'] + (' ' + entry['note'] if entry['note'] else ''), font, MUTED if past else TEXT, 'center')
        self.label(pad, h - 30, 'Resmî tatillerde tarife değişebilir. Tek tek seferlerin kesin iptal bilgisi sunulmaz.', 8, MUTED)

    def refresh(self):
        if self.busy or self.closed:
            return
        self.busy = True
        self.draw()
        def work():
            try:
                self.results.put((self.client.board(), None))
            except Exception as exc:
                logging.exception('İETT bağlantısı')
                self.results.put((None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            data, error = self.results.get_nowait()
            self.busy = False
            if data:
                self.board = data
            self.error = error or ''
            self.draw()
        except queue.Empty:
            pass
        if not self.closed:
            self.root.after(100, self.poll)

    def auto_refresh(self):
        self.refresh()
        if not self.closed:
            self.root.after(30000, self.auto_refresh)

    def tick(self):
        self.draw()
        if not self.closed:
            self.root.after(1000, self.tick)

    def escape(self, _):
        if self.selected:
            self.close_detail()
        return 'break'

    def request_close(self):
        if not self.kiosk:
            self.close()

    def admin_exit(self):
        if not self.kiosk or messagebox.askyesno('Kiosk bakım çıkışı', 'Kiosk uygulamasını kapatmak istiyor musunuz?', parent=self.root):
            self.close()

    def close(self):
        self.closed = True
        self.keep_awake(False)
        self.root.destroy()

def main():
    parser = argparse.ArgumentParser(description='Okan Üniversitesi İETT ekranı')
    parser.add_argument('--kiosk', action='store_true', help='Tam ekran, üstte tutulan kiosk penceresi')
    parser.add_argument('--smoke-test', action='store_true', help='Arayüzü kısa süre açıp kapatarak doğrula')
    args = parser.parse_args()
    import os
    log_dir = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'OkanDurak'
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(handlers=[RotatingFileHandler(log_dir / 'app.log', maxBytes=1_000_000, backupCount=2, encoding='utf-8')], level=logging.WARNING)
    root = tk.Tk()
    app = App(root, kiosk=args.kiosk)
    if args.smoke_test:
        root.after(8000, app.close)
    root.mainloop()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
