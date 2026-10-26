"""Okan Durak: native Python/Tkinter departure board, no browser/server required."""
import argparse
import csv
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
from ring_client import RingClient, next_departure

BG = '#181818'
CARD = '#222222'
LINE = '#353535'
TEXT = '#e7e7e7'
MUTED = '#999999'
ACCENT = '#bfcede'
AMBER = '#cfac7e'
LIVE_GREEN = '#9bc9a4'

class App:
    def __init__(self, root, kiosk=False, log_dir=None):
        self.root, self.kiosk = root, kiosk
        self.log_dir = log_dir or Path.home() / 'OkanDurak'
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.board = None
        self.error = ''
        self.busy = False
        self.closed = False
        self.client = IettClient()
        self.ring_client = RingClient(self.log_dir / 'ring_cache.json')
        self.results = queue.Queue()
        self.selected = None
        self.selected_ring = None
        self.page = 'board'
        self.feedback_route = None
        self.feedback_message = ''
        self.feedback_snapshot = None
        self.feedback_step = 1
        self.feedback_cache_mtime = None
        self.feedback_cache_rows = []
        self.admin_password = ''
        self.admin_message = ''
        self.admin_page_index = 0
        self.admin_feedback_index = None
        self.admin_message_loaded_index = None
        self.keyboard_open = False
        self.keyboard_target = None
        self.keyboard_shift = False
        self.day = day_index()
        self.draw_job = None
        self.idle_job = None
        root.title('Okan Durak')
        root.configure(bg=BG)
        root.geometry('1360x760')
        root.minsize(800, 620)
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.feedback_text_widget = tk.Text(
            self.canvas, height=3, wrap='word', font=('Segoe UI', 12),
            bg=CARD, fg=TEXT, insertbackground=TEXT, relief='flat',
            highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
            padx=12, pady=8, undo=True,
        )
        self.admin_message_widget = tk.Text(
            self.canvas, height=8, wrap='word', font=('Segoe UI', 12),
            bg=CARD, fg=TEXT, relief='flat', highlightthickness=1,
            highlightbackground=LINE, padx=14, pady=12,
        )
        self.admin_message_scroll = tk.Scrollbar(self.canvas, command=self.admin_message_widget.yview)
        self.admin_message_widget.configure(yscrollcommand=self.admin_message_scroll.set)
        self.admin_message_widget.configure(state='disabled')
        root.protocol('WM_DELETE_WINDOW', self.request_close)
        root.bind('<Configure>', self.resized)
        root.bind('<Escape>', self.escape)
        root.bind('<F5>', lambda _: self.refresh())
        root.bind('<Control-Shift-Q>', lambda _: self.admin_exit())
        root.bind('<Control-Shift-q>', lambda _: self.admin_exit())
        root.bind_all('<ButtonPress>', self.activity)
        root.bind_all('<KeyPress>', self.activity)
        root.bind_all('<Motion>', self.activity)
        root.bind_all('<MouseWheel>', self.activity)
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
        self.reset_idle_timer()

    def activity(self, _event=None):
        self.reset_idle_timer()
        if self.page == 'admin_login' and _event is not None:
            if _event.keysym in ('Return', 'KP_Enter'):
                self.submit_admin_password()
            elif _event.keysym == 'BackSpace':
                self.admin_password = self.admin_password[:-1]
                self.draw()
            elif len(_event.char) == 1 and _event.char.isprintable():
                self.admin_password += _event.char
                self.draw()
            return 'break'

    def reset_idle_timer(self):
        if self.closed:
            return
        if self.idle_job:
            self.root.after_cancel(self.idle_job)
        self.idle_job = self.root.after(30000, self.return_home_if_idle)

    def return_home_if_idle(self):
        self.idle_job = None
        if self.page != 'board' or self.selected:
            self.page = 'board'
            self.selected = None
            self.feedback_message = ''
            self.admin_password = ''
            self.admin_message = ''
            self.keyboard_open = False
            self.keyboard_target = None
            self.draw()

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

    def button(self, x, y, width, title, command, active=False, prominent=False, button_height=None):
        tag = 'button_' + str(self.canvas.find_all()[-1] if self.canvas.find_all() else 0)
        fill = '#c6d2dc' if prominent else '#303030' if active else BG
        fg = '#17191b' if prominent else ACCENT if active else MUTED
        height = button_height or (48 if prominent else 42)
        self.canvas.create_rectangle(x, y, x + width, y + height, fill=fill, outline='', tags=tag)
        self.label(x + width / 2, y + height / 2, title, 12 if prominent else 11, fg,
                   anchor='center', bold=prominent, tag=tag)
        self.canvas.tag_bind(tag, '<Button-1>', lambda _: command())
        self.canvas.tag_bind(tag, '<Enter>', lambda _: self.canvas.configure(cursor='hand2'))
        self.canvas.tag_bind(tag, '<Leave>', lambda _: self.canvas.configure(cursor=''))

    def draw_keyboard(self, w, h, pad):
        if not self.keyboard_open:
            return
        key_h = max(27, min(38, int(h * .05)))
        gap = max(3, int(key_h * .12))
        panel_pad = 8
        keyboard_h = 5 * key_h + 4 * gap + panel_pad * 2
        keyboard_y = h - keyboard_h
        keyboard_w = min(w - 2 * pad, 1000)
        x0 = (w - keyboard_w) / 2
        self.canvas.create_rectangle(x0 - 6, keyboard_y - 5, x0 + keyboard_w + 6, h - 6,
                                     fill='#202020', outline=LINE, width=1)
        rows = ('1234567890', 'qwertyuıopğü', 'asdfghjklşi', 'zxcvbnmöç.,?!')
        row_y = keyboard_y + panel_pad
        upper_map = {'i': 'İ', 'ı': 'I', 'ğ': 'Ğ', 'ü': 'Ü', 'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'}
        for row_index, row in enumerate(rows):
            key_w = (keyboard_w - gap * (len(row) - 1)) / len(row)
            row_x = x0
            for key in row:
                shown = upper_map.get(key, key.upper()) if self.keyboard_shift and key.isalpha() else key
                self.button(row_x, row_y, key_w, shown,
                            lambda value=key: self.keyboard_key(value), active=True, button_height=key_h)
                row_x += key_w + gap
            row_y += key_h + gap
        action_gap = gap
        action_space = keyboard_w - action_gap * 4
        action_widths = (action_space * .40, action_space * .15, action_space * .10,
                         action_space * .15, action_space * .20)
        actions = [('Boşluk', 'space'), ('⌫', 'backspace'), ('⇧', 'shift'), ('Sil', 'clear'),
                   ('Giriş yap' if self.keyboard_target == 'admin' else 'Bitti', 'done')]
        row_x = x0
        for (title, value), key_w in zip(actions, action_widths):
            self.button(row_x, row_y, key_w, title, lambda v=value: self.keyboard_key(v),
                        active=value != 'done', prominent=value == 'done', button_height=key_h)
            row_x += key_w + action_gap

    def keyboard_key(self, key):
        self.activity()
        if key == 'done':
            if self.keyboard_target == 'admin':
                self.submit_admin_password()
                return
            self.keyboard_open = False
        elif key == 'shift':
            self.keyboard_shift = not self.keyboard_shift
        elif self.keyboard_target == 'admin':
            if key == 'clear':
                self.admin_password = ''
            elif key == 'space':
                self.admin_password += ' '
            elif key == 'backspace':
                self.admin_password = self.admin_password[:-1]
            else:
                upper_map = {'i': 'İ', 'ı': 'I', 'ğ': 'Ğ', 'ü': 'Ü', 'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'}
                self.admin_password += upper_map.get(key, key.upper()) if self.keyboard_shift and key.isalpha() else key
        elif self.keyboard_target == 'feedback':
            if key == 'clear':
                self.feedback_text_widget.delete('1.0', 'end')
            elif key == 'space':
                self.feedback_text_widget.insert('end', ' ')
            elif key == 'backspace':
                if self.feedback_text_widget.get('1.0', 'end-1c'):
                    self.feedback_text_widget.delete('end-2c', 'end-1c')
            else:
                upper_map = {'i': 'İ', 'ı': 'I', 'ğ': 'Ğ', 'ü': 'Ü', 'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'}
                value = upper_map.get(key, key.upper()) if self.keyboard_shift and key.isalpha() else key
                self.feedback_text_widget.insert('end', value)
            self.feedback_text_widget.focus_set()
        self.draw()

    def bus_icon(self, x, y, color=ACCENT, scale=1.0, tag=None):
        c = self.canvas
        width, height = 34 * scale, 23 * scale
        c.create_rectangle(x, y, x + width, y + height, fill=color, outline='', tags=tag or ())
        c.create_rectangle(x + 4 * scale, y + 4 * scale, x + 12 * scale,
                           y + 10 * scale, fill=BG, outline='', tags=tag or ())
        c.create_rectangle(x + 15 * scale, y + 4 * scale, x + 27 * scale,
                           y + 10 * scale, fill=BG, outline='', tags=tag or ())
        c.create_oval(x + 5 * scale, y + 19 * scale, x + 12 * scale,
                      y + 26 * scale, fill=BG, outline='', tags=tag or ())
        c.create_oval(x + 23 * scale, y + 19 * scale, x + 30 * scale,
                      y + 26 * scale, fill=BG, outline='', tags=tag or ())

    def draw(self):
        self.draw_job = None
        if self.closed:
            return
        if not (self.page == 'feedback' and self.feedback_step == 2 and not self.feedback_message):
            self.feedback_text_widget.place_forget()
        if self.page != 'admin_detail':
            self.admin_message_widget.place_forget()
            self.admin_message_scroll.place_forget()
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
        if self.page == 'feedback':
            self.draw_feedback(w, h, pad)
            self.draw_keyboard(w, h, pad)
            return
        if self.page == 'ring_detail':
            self.draw_ring_detail(w, h, pad)
            return
        if self.page == 'feedback_log':
            self.draw_feedback_log(w, h, pad)
            return
        if self.page == 'admin_login':
            self.draw_admin_login(w, h, pad)
            self.draw_keyboard(w, h, pad)
            return
        if self.page == 'admin':
            self.draw_admin(w, h, pad)
            self.label(pad, h - 10, 'yusuf emre bilir tarafından geliştirilmiştir', 7, MUTED)
            return
        if self.page == 'admin_detail':
            self.draw_admin_detail(w, h, pad)
            self.label(pad, h - 10, 'yusuf emre bilir tarafından geliştirilmiştir', 7, MUTED)
            return
        if self.selected:
            self.draw_detail(w, h, pad)
            return
        self.label(pad, 104, 'Okan ring tarifeleri ve belediye otobüsleri', 9, MUTED, width=w - 2 * pad - 440)
        self.button(w - pad - 435, 91, 340, 'Otobüs zamanında geldi mi? Bize bildir', self.open_feedback, prominent=True)
        self.button(w - pad - 85, 94, 85, 'Yenileniyor…' if self.busy else 'Yenile', self.refresh)
        ring_routes = self.board.get('ring_routes', []) if self.board else []
        ring_error = self.board.get('ring_error', '') if self.board else ''
        ring_bottom = self.draw_ring_row(w, h, pad, ring_routes, ring_error)
        main_heading_y = ring_bottom + 13
        self.label(pad, main_heading_y, 'İETT belediye otobüsleri · karta dokun: tüm saatler', 10, TEXT,
                   bold=True, width=w - 2 * pad - 220)
        self.label(w - pad, main_heading_y + 2, '● Canlı tahmin    ● Hesaplanan', 8, MUTED, anchor='ne')
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
            self.label(w / 2, main_heading_y + 100, self.error or 'İETT’ye bağlanılıyor…', 14, MUTED, 'center', width=w - 80)
        else:
            gap = max(8, min(18, w * .012))
            cw = (w - 2 * pad - gap * (n - 1)) / n
            feedback_rows = self.read_feedback()
            top = main_heading_y + 31
            bottom = max(top + 190, h - 95 - warning_height)
            ch = bottom - top
            scale = min(1.18, cw / 205, ch / 290)
            for index, route in enumerate(routes):
                x = pad + index * (cw + gap)
                tag = 'route_' + route['code']
                c.create_rectangle(x, top, x + cw, bottom, fill=CARD, outline=LINE, width=1, tags=tag)
                inner = max(8, cw * .04)
                self.label(x + inner, top + 6, route['code'], 21 * scale, bold=True, tag=tag)
                self.bus_icon(x + cw - inner - 37 * scale, top + 12, scale=scale, tag=tag)
                # Reserve a fixed area for route labels so every next-arrival time aligns.
                self.label(x + inner, top + 48 * scale, route['name'], 9.5 * scale, MUTED, width=cw - 2 * inner - 36 * scale, tag=tag)
                c.create_line(x + inner, top + 83 * scale, x + cw - inner, top + 83 * scale, fill=LINE, tags=tag)
                entries = upcoming(route)
                next_bus = entries[0] if entries else None
                y = top + 65 * scale
                heading = ('Tahmini varış' if next_bus.get('live') else 'Sinyal belirsiz' if next_bus.get('uncertain') else 'Hesaplanan varış' if next_bus.get('estimated') else 'Planlı kampüs kalkışı') if next_bus else 'Tahmini varış'
                self.label(x + inner, y, heading, 9 * scale, MUTED, tag=tag)
                time_label = ('~' if next_bus.get('estimated') else '') + next_bus['time'] if next_bus else '—'
                eta_color = (LIVE_GREEN if next_bus.get('live') and not next_bus.get('uncertain')
                             else AMBER if next_bus.get('estimated') or next_bus.get('uncertain') else TEXT) if next_bus else MUTED
                self.label(x + inner, y + 23 * scale, time_label, 29 * scale, eta_color, bold=True, tag=tag)
                if next_bus:
                    remaining = 'Durakta / geliyor' if next_bus['minutes'] == 0 else f"{next_bus['minutes']} dk kaldı"
                    if next_bus.get('days_ahead', 0):
                        remaining = 'Yarın' if next_bus['days_ahead'] == 1 else next_bus['arrival_date'][8:10] + '.' + next_bus['arrival_date'][5:7] + ' tarihinde'
                    self.label(x + inner, y + 77 * scale, remaining, 13 * scale, eta_color, tag=tag)
                    destination = next_bus.get('destination', '').rsplit(' - ', 1)[-1]
                    if (next_bus.get('live') or next_bus.get('uncertain')) and ch > 350:
                        self.label(x + inner, y + 112 * scale, 'Yön: ' + destination, 8 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                        if ch > 430:
                            self.label(x + inner, y + 147 * scale, 'Kaynak: İETT · ' + next_bus['stop'], 8 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                    elif next_bus.get('estimated'):
                        self.label(x + inner, y + 109 * scale, f"Yaklaşık · ±{next_bus['margin']} dk model payı", 8 * scale, AMBER, width=cw - 2 * inner, tag=tag)
                        if ch > 430:
                            self.label(x + inner, y + 133 * scale, 'Yön: ' + destination + '\nTarife + durak sırası · GPS yok', 8 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                    else:
                        self.label(x + inner, y + 112 * scale, 'Tarifeden · Canlı tahmin değil', 8 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                else:
                    reason = 'İETT şu an araç tahmini paylaşmıyor.' if route.get('arrivals_available', True) else 'Canlı veri bağlantısı kurulamadı.'
                    self.label(x + inner, y + 81 * scale, reason, 9 * scale, MUTED, width=cw - 2 * inner, tag=tag)
                route_feedback = [r for r in feedback_rows if r.get('hat') == route['code']
                                  and r.get('geri_bildirim') in ('zamaninda', 'gec', 'gelmedi_iptal')]
                total_feedback = len(route_feedback)
                on_time = sum(r.get('geri_bildirim') == 'zamaninda' for r in route_feedback)
                stats_y = bottom - 91 * scale
                if total_feedback:
                    accuracy = round(on_time * 100 / total_feedback)
                    stat_text = f'Geri bildirim  %{accuracy} zamanında · {total_feedback} yanıt'
                    self.label(x + inner, stats_y, stat_text, 8 * scale,
                               LIVE_GREEN if accuracy >= 70 else AMBER, bold=True, tag=tag)
                    if ch > 420:
                        bar_x, bar_y = x + inner, stats_y + 17 * scale
                        bar_w = cw - 2 * inner
                        c.create_rectangle(bar_x, bar_y, bar_x + bar_w, bar_y + 5 * scale,
                                           fill='#363636', outline='', tags=tag)
                        c.create_rectangle(bar_x, bar_y, bar_x + bar_w * accuracy / 100,
                                           bar_y + 5 * scale, fill=LIVE_GREEN if accuracy >= 70 else AMBER,
                                           outline='', tags=tag)
                else:
                    self.label(x + inner, stats_y, 'Henüz öğrenci bildirimi yok', 8 * scale, MUTED, tag=tag)
                status, color = self.status(route)
                c.create_line(x + inner, bottom - 65 * scale, x + cw - inner, bottom - 65 * scale, fill=LINE, tags=tag)
                self.label(x + inner, bottom - 52 * scale, '●', 9 * scale, color, tag=tag)
                self.label(x + inner + 15 * scale, bottom - 52 * scale, status, 8 * scale, color, width=cw - 2 * inner - 20 * scale, tag=tag)
                self.label(x + inner, bottom - 22 * scale, 'Tüm sefer saatleri  →', 9 * scale, ACCENT, tag=tag)
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
        self.label(pad, h - 34, '~ işaretli saatler tarife ve durak sırasından hesaplanır; canlı konum değildir.', 8, MUTED, width=w - 2 * pad - 140)
        self.button(w - pad - 120, h - 51, 120, '⚙  Ayarlar', self.open_admin_login)

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
        self.page = 'board'
        self.selected = code
        self.day = day_index()
        self.draw()

    def draw_ring_row(self, w, h, pad, routes, error=''):
        """Draw compact, square campus-ring cards above the IETT board."""
        title_y = 150
        self.label(pad, title_y, 'OKAN KAMPÜS RİNGİ', 9, TEXT, bold=True)
        ring_status = 'karta dokun: tüm saatler'
        if self.board and self.board.get('ring_updated_at'):
            stamp = datetime.fromtimestamp(self.board['ring_updated_at'], ISTANBUL).strftime('%H:%M')
            ring_status = ('Önbellek · ' if self.board.get('ring_cached') else 'Siteden · ') + stamp + ' · 12 saatte bir · tüm saatler'
        self.label(w - pad, title_y, ring_status,
                   8, MUTED, anchor='ne')
        top = title_y + 21
        gap = max(5, min(10, w * .007))
        count = max(1, len(routes))
        cell_w = (w - 2 * pad - gap * (count - 1)) / count
        size = min(cell_w, 104, max(70, h * .145))
        bottom = top + size
        if not routes:
            self.label(w / 2, top + size / 2, 'Ring tarifeleri yükleniyor…' if not error else 'Ring tarifesi şu an alınamadı',
                       10, MUTED, 'center')
            return bottom
        now = datetime.now(ISTANBUL)
        for index, route in enumerate(routes):
            x = pad + index * (cell_w + gap)
            tag = 'ring_' + str(index)
            self.canvas.create_rectangle(x, top, x + cell_w, bottom, fill=CARD, outline=LINE, width=1, tags=tag)
            name_size = max(7, min(10, size * .095))
            max_chars = max(8, int((cell_w - 12) / (name_size * .62)))
            name_lines = []
            for part in route['name'].split(' / '):
                name_lines.append(part if len(part) <= max_chars else part[:max_chars - 1].rstrip() + '…')
            name = '\n'.join(name_lines[:2])
            self.label(x + cell_w / 2, top + 5, name, name_size, TEXT,
                       'n', width=cell_w - 8, bold=True, tag=tag)
            directions = route.get('directions', [])
            going = next((d for d in directions if d['side'] == 'to_campus'), None)
            coming = next((d for d in directions if d['side'] == 'from_campus'), None)
            first = next_departure(going, now) if going else None
            second = next_departure(coming, now) if coming else None
            base = top + size * .48
            for line, label, item in ((0, '→', first), (1, '←', second)):
                y = base + line * size * .23
                self.label(x + 7, y, label, 9, MUTED, tag=tag)
                time_text = item['time'] if item else '—'
                self.label(x + 21, y, time_text, max(9, min(15, size * .145)), LIVE_GREEN if item else MUTED,
                           bold=True, tag=tag)
                if item:
                    when = (f"{item['minutes']} dk" if item['days_ahead'] == 0 else item['day_name'])
                    self.label(x + cell_w - 6, y + 2, when, max(7, min(9, size * .085)), MUTED, 'ne', tag=tag)
            self.canvas.tag_bind(tag, '<Button-1>', lambda _, key=route['key']: self.open_ring_detail(key))
            self.canvas.tag_bind(tag, '<Enter>', lambda _: self.canvas.configure(cursor='hand2'))
            self.canvas.tag_bind(tag, '<Leave>', lambda _: self.canvas.configure(cursor=''))
        return bottom

    def open_ring_detail(self, key):
        self.selected_ring = key
        self.page = 'ring_detail'
        self.draw()

    def draw_ring_detail(self, w, h, pad):
        routes = self.board.get('ring_routes', []) if self.board else []
        route = next((r for r in routes if r['key'] == self.selected_ring), None)
        self.button(pad, 98, 100, '← Ana sayfa', self.leave_ring_detail, active=True)
        if not route:
            self.label(pad, 165, 'Ring tarifesi bulunamadı.', 14, MUTED)
            return
        self.label(pad, 155, route['name'] + ' ring tarifesi', 19, TEXT, bold=True)
        updated = self.board.get('ring_updated_at') if self.board else None
        if updated:
            self.label(pad, 185, 'Okan Üniversitesi · son tarife kontrolü ' +
                       datetime.fromtimestamp(updated, ISTANBUL).strftime('%d.%m.%Y %H:%M'), 9, MUTED)
        self.label(pad, 207, 'Bu, yayımlanan kalkış tarifesidir; canlı araç konumu ve anlık iptal bilgisi içermez.',
                   9, AMBER, width=w - 2 * pad)
        directions = route.get('directions', [])
        count = max(1, len(directions))
        gap = 22
        bw = (w - 2 * pad - gap * (count - 1)) / count
        for ix, direction in enumerate(directions):
            x = pad + ix * (bw + gap)
            arrow = '  →  ' if direction['side'] == 'to_campus' else '  ←  '
            title = direction['title'].replace(' - ', arrow)
            title_id = self.label(x, 245, title, 11, TEXT, bold=True, width=bw)
            title_bounds = self.canvas.bbox(title_id)
            schedules = direction.get('schedules', [])
            row_y = max(279, title_bounds[3] + 14 if title_bounds else 279)
            if not schedules:
                self.label(x, row_y, 'Tarife bulunamadı.', 10, MUTED)
            for schedule in schedules:
                self.label(x, row_y, schedule['day'], 9, MUTED)
                row_y += 22
                cols = max(3, int(bw / 82))
                cell_w = bw / cols
                for j, departure in enumerate(schedule['times']):
                    col, row = j % cols, j // cols
                    xx, yy = x + col * cell_w, row_y + row * 38
                    self.canvas.create_rectangle(xx, yy, xx + cell_w - 6, yy + 31, fill=CARD, outline=LINE)
                    self.label(xx + (cell_w - 6) / 2, yy + 15, departure, 10, TEXT, 'center')
                row_y += max(38, math.ceil(len(schedule['times']) / cols) * 38 + 8)
        self.button(w - pad - 120, h - 51, 120, '⚙  Ayarlar', self.open_admin_login)

    def leave_ring_detail(self):
        self.page = 'board'
        self.selected_ring = None
        self.draw()

    def close_detail(self):
        self.selected = None
        self.page = 'board'
        self.draw()

    def open_feedback(self):
        routes = (self.board or {}).get('routes', [])
        self.feedback_route = None
        self.feedback_message = ''
        self.feedback_snapshot = None
        self.feedback_step = 1
        self.feedback_text_widget.delete('1.0', 'end')
        self.keyboard_open = False
        self.keyboard_target = None
        self.page = 'feedback'
        self.draw()

    def feedback_back(self):
        self.keyboard_open = False
        self.keyboard_target = None
        self.page = 'board'
        self.draw()

    def choose_feedback_route(self, code):
        self.feedback_route = code
        self.feedback_message = ''
        self.feedback_text_widget.delete('1.0', 'end')
        self.capture_feedback_snapshot()
        self.feedback_step = 2
        self.keyboard_target = 'feedback'
        self.keyboard_shift = False
        self.keyboard_open = True
        self.draw()

    def start_another_feedback(self):
        self.feedback_route = None
        self.feedback_snapshot = None
        self.feedback_message = ''
        self.feedback_step = 1
        self.keyboard_open = False
        self.keyboard_target = None
        self.feedback_text_widget.delete('1.0', 'end')
        self.draw()


    def capture_feedback_snapshot(self):
        route = self.current_feedback_route()
        entries = upcoming(route) if route else []
        arrival = entries[0] if entries else {}
        self.feedback_snapshot = {
            'time': arrival.get('time', ''),
            'kind': ('canli' if arrival.get('live') else 'hesaplanan' if arrival.get('estimated') else 'tarife') if arrival else 'tahmin_yok',
        }

    def current_feedback_route(self):
        return next((r for r in (self.board or {}).get('routes', [])
                     if r['code'] == self.feedback_route), None)

    def save_feedback(self, outcome):
        route = self.current_feedback_route()
        if not route:
            self.feedback_message = 'Önce bir hat seçin.'
            self.draw()
            return
        snapshot = self.feedback_snapshot or {'time': '', 'kind': 'tahmin_yok'}
        row = {
            'kayit_zamani': datetime.now(ISTANBUL).isoformat(timespec='seconds'),
            'hat': route['code'],
            'hat_adi': route['name'],
            'tahmini_saat': snapshot['time'],
            'tahmin_turu': snapshot['kind'],
            'geri_bildirim': outcome,
            'mesaj': self.feedback_text_widget.get('1.0', 'end-1c').strip(),
        }
        try:
            rows = self.read_feedback()
            rows.append(row)
            self.write_feedback_rows(rows)
            self.feedback_message = (
                'Harika! Sistemimizi geliştirmemize yardımcı olduğunuz için teşekkür ederiz.'
                if outcome == 'zamaninda' else
                'Özür dileriz. Sistemimizi daha iyi yapmamıza yardımcı olduğunuz için teşekkür ederiz.'
            )
            logging.info('Geri bildirim kaydedildi: %s %s', route['code'], outcome)
        except OSError:
            logging.exception('Geri bildirim dosyaya yazılamadı')
            self.feedback_message = 'Dosyaya kaydedilemedi. Uygulama izinlerini kontrol edin.'
        self.keyboard_open = False
        self.keyboard_target = None
        self.draw()

    def write_feedback_rows(self, rows):
        path = self.log_dir / 'geri_bildirim.csv'
        temp_path = path.with_suffix('.tmp')
        fields = ('kayit_zamani', 'hat', 'hat_adi', 'tahmini_saat', 'tahmin_turu', 'geri_bildirim', 'mesaj')
        with temp_path.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(path)
        self.feedback_cache_mtime = None

    def read_feedback(self):
        path = self.log_dir / 'geri_bildirim.csv'
        try:
            modified = path.stat().st_mtime_ns
            if modified == self.feedback_cache_mtime:
                return self.feedback_cache_rows
            with path.open('r', newline='', encoding='utf-8-sig') as f:
                self.feedback_cache_rows = list(csv.DictReader(f))
                self.feedback_cache_mtime = modified
                return self.feedback_cache_rows
        except FileNotFoundError:
            self.feedback_cache_mtime = None
            self.feedback_cache_rows = []
            return []
        except OSError:
            logging.exception('Geri bildirim dosyası okunamadı')
            return []

    def draw_feedback(self, w, h, pad):
        self.label(pad, 104, 'Geri bildiriminiz önemli', 14, TEXT, bold=True)
        self.button(w - pad - 205, 98, 95, 'Kayıtlar', self.open_feedback_log)
        self.button(w - pad - 100, 98, 100, 'Ana ekran', self.feedback_back)
        routes = (self.board or {}).get('routes', [])
        if self.feedback_step == 1:
            self.label(pad, 146, 'Hangi hat için geri bildirim vermek istiyorsunuz?', 11, MUTED)
            gap = 10
            count = max(1, len(routes))
            cell_w = min(180, (w - 2 * pad - gap * (count - 1)) / count)
            for i, route in enumerate(routes):
                self.button(pad + i * (cell_w + gap), 190, cell_w, route['code'] + '  ›',
                            lambda code=route['code']: self.choose_feedback_route(code), prominent=True)
            if not routes:
                self.label(pad, 200, 'Hat bilgisi henüz yüklenmedi.', 11, AMBER)
        elif self.feedback_message:
            self.label(w / 2, 230, self.feedback_message, 14, TEXT, anchor='center',
                       width=w - 2 * pad, bold=True)
            self.button(w / 2 - 120, 284, 240, 'Ana sayfaya dön', self.feedback_back, prominent=True)
        else:
            route = self.current_feedback_route()
            if route:
                entries = upcoming(route)
                arrival = entries[0] if entries else None
                self.label(pad, 151, route['code'] + ' · ' + route['name'], 13, TEXT, bold=True, width=w - 2 * pad)
                shown = arrival['time'] if arrival else 'Şu an tahmin yok'
                if arrival and arrival.get('estimated'):
                    shown = '~' + shown + ' · hesaplanan'
                elif arrival and arrival.get('live'):
                    shown += ' · canlı İETT verisi'
                elif arrival:
                    shown += ' · tarife'
                self.label(pad, 183, 'Ekrandaki sıradaki saat: ' + shown, 11, MUTED)
            if self.keyboard_open and self.keyboard_target == 'feedback':
                self.label(pad, 213, 'Notunuzu yazın · Türkçe karakterler desteklenir', 10, MUTED)
                key_h = max(27, min(38, int(h * .05)))
                key_gap = max(3, int(key_h * .12))
                keyboard_top = h - (5 * key_h + 4 * key_gap + 16 + 12)
                text_y = 235
                text_h = min(170, max(48, keyboard_top - text_y - 14))
                self.feedback_text_widget.place(x=pad, y=text_y, width=w - 2 * pad, height=text_h)
                return
            button_y = max(246, min(300, h * .39))
            self.label(pad, button_y - 40, 'Otobüs tahmin edilen saatte geldi mi?', 12, TEXT, bold=True)
            labels = [('Evet, zamanında geldi', 'zamaninda'),
                      ('Hayır, geç geldi', 'gec'),
                      ('Hiç gelmedi / iptal', 'gelmedi_iptal')]
            gap = 12
            button_w = min(260, (w - 2 * pad - gap * 2) / 3)
            start_x = (w - (button_w * 3 + gap * 2)) / 2
            for i, (label, outcome) in enumerate(labels):
                self.button(start_x + i * (button_w + gap), button_y, button_w, label,
                            lambda value=outcome: self.save_feedback(value), prominent=True)
            message_y = button_y + 62
            self.label(pad, message_y, 'İsterseniz kısa bir not da ekleyin', 10, MUTED)
            entry_y = message_y + 23
            entry_h = min(84, max(58, int(h * .11)))
            self.feedback_text_widget.place(x=pad, y=entry_y, width=w - 2 * pad, height=entry_h)
        self.label(pad, h - 32, 'Geri bildirimler bu bilgisayarda yerel olarak tutulur.', 8, MUTED)

    def open_feedback_log(self):
        self.page = 'feedback_log'
        self.draw()

    def draw_feedback_log(self, w, h, pad):
        self.label(pad, 104, 'Geri bildirim kayıtları', 14, TEXT, bold=True)
        self.button(w - pad - 100, 98, 100, 'Geri', lambda: self.set_page('feedback'))
        rows = self.read_feedback()
        if not rows:
            self.label(pad, 160, 'Henüz geri bildirim kaydı yok.', 10, MUTED)
        else:
            visible = rows[-max(1, int((h - 190) / 34)):][::-1]
            col1, col2, col3 = pad, pad + w * .30, pad + w * .43
            col4 = pad + w * .57
            self.label(col1, 143, 'Zaman', 9, MUTED)
            self.label(col2, 143, 'Hat', 9, MUTED)
            self.label(col3, 143, 'Tahmin', 9, MUTED)
            self.label(col4, 143, 'Sonuç', 9, MUTED)
            for i, row in enumerate(visible):
                y = 174 + i * 34
                self.canvas.create_line(pad, y + 25, w - pad, y + 25, fill=LINE)
                stamp = row.get('kayit_zamani', '').replace('T', ' ')[:16]
                self.label(col1, y, stamp, 9, TEXT)
                self.label(col2, y, row.get('hat', ''), 9, TEXT)
                self.label(col3, y, row.get('tahmini_saat') or '—', 9, TEXT)
                self.label(col4, y, row.get('geri_bildirim', ''), 9, TEXT)
        self.label(pad, h - 32, 'Dosya: ' + str(self.log_dir / 'geri_bildirim.csv'), 8, MUTED, width=w - 2 * pad)

    def open_admin_login(self):
        self.admin_password = ''
        self.admin_message = ''
        self.keyboard_target = 'admin'
        self.keyboard_shift = True
        self.keyboard_open = True
        self.page = 'admin_login'
        self.draw()
        self.canvas.focus_set()

    def draw_admin_login(self, w, h, pad):
        self.label(pad, 104, 'Yönetici girişi', 15, TEXT, bold=True)
        hint = self.admin_message or 'Geri bildirim kayıtları için şifreyi girin.'
        self.label(pad, 145, hint, 10, AMBER if self.admin_message else MUTED)
        box_w = min(420, w - 2 * pad)
        x, y = (w - box_w) / 2, min(260, max(171, h * .31))
        self.canvas.create_rectangle(x, y, x + box_w, y + 54, fill=CARD, outline=LINE, width=1,
                                     tags='password_entry')
        shown = '● ' * len(self.admin_password) if self.admin_password else 'Şifreyi yazın…'
        self.label(x + 18, y + 27, shown, 13, TEXT if self.admin_password else MUTED, anchor='w', tag='password_entry')
        self.canvas.tag_bind('password_entry', '<Button-1>', self.focus_admin_password)
        self.button(w / 2 - 85, y + 64, 170, 'Giriş yap', self.submit_admin_password)
        self.button(pad, h - 52, 110, 'Ana sayfa', self.leave_admin)

    def focus_admin_password(self, _event=None):
        self.canvas.focus_set()
        self.keyboard_target = 'admin'
        self.keyboard_shift = True
        self.keyboard_open = True
        self.draw()

    def submit_admin_password(self):
        if self.admin_password == 'YEB':
            self.admin_password = ''
            self.admin_message = ''
            self.admin_page_index = 0
            self.keyboard_open = False
            self.keyboard_target = None
            self.page = 'admin'
        else:
            self.admin_password = ''
            self.admin_message = 'Şifre yanlış. Yeniden deneyin.'
        self.draw()

    def draw_admin(self, w, h, pad):
        rows = self.read_feedback()
        self.label(pad, 104, 'Yönetici paneli', 15, TEXT, bold=True)
        summary = self.admin_message or f'{len(rows)} geri bildirim kaydı · Bu bilgisayarda saklanıyor'
        self.label(pad, 131, summary, 9, AMBER if self.admin_message else MUTED)
        self.button(w - pad - 110, 98, 110, 'Çıkış', self.leave_admin)
        if not rows:
            self.label(w / 2, h * .43, 'Henüz geri bildirim kaydı yok.', 13, MUTED, anchor='center')
            self.label(pad, h - 32, str(self.log_dir / 'geri_bildirim.csv'), 8, MUTED)
            return

        per_page = max(1, int((h - 250) / 56))
        page_count = max(1, (len(rows) + per_page - 1) // per_page)
        self.admin_page_index = min(self.admin_page_index, page_count - 1)
        end = len(rows) - self.admin_page_index * per_page
        start = max(0, end - per_page)
        visible = [(i, rows[i]) for i in range(end - 1, start - 1, -1)]
        self.label(pad, 163, 'TARİH / SAAT', 8, MUTED)
        self.label(pad + 190, 163, 'HAT · EKRANDAKİ TAHMİN · YANIT', 8, MUTED)
        for row_index, (source_index, row) in enumerate(visible):
            y = 188 + row_index * 56
            self.canvas.create_rectangle(pad, y, w - pad, y + 48, fill=CARD, outline=LINE)
            stamp = row.get('kayit_zamani', '').replace('T', ' ')[:16]
            self.label(pad + 10, y + 8, stamp, 9, TEXT)
            outcome = {'zamaninda': 'Zamanında geldi', 'gec': 'Geç geldi',
                       'gelmedi_iptal': 'Gelmedi / iptal'}.get(row.get('geri_bildirim'), row.get('geri_bildirim', ''))
            kind = {'canli': 'canlı', 'hesaplanan': 'hesaplanan', 'tarife': 'tarife',
                    'tahmin_yok': 'tahmin yok'}.get(row.get('tahmin_turu'), '')
            detail = f"{row.get('hat', '')}  ·  {row.get('tahmini_saat') or '—'} ({kind})  ·  {outcome}"
            self.label(pad + 190, y + 8, detail, 9, TEXT, width=w - 2 * pad - 400)
            self.button(w - pad - 180, y + 3, 78, 'Mesaj',
                        lambda idx=source_index: self.open_admin_detail(idx))
            self.button(w - pad - 90, y + 8, 78, 'Sil',
                        lambda idx=source_index: self.delete_feedback(idx))
        nav_y = h - 70
        if self.admin_page_index > 0:
            self.button(pad, nav_y, 110, '‹ Daha yeni', lambda: self.change_admin_page(-1))
        self.label(w / 2, nav_y + 16, f'Sayfa {self.admin_page_index + 1} / {page_count}', 9, MUTED, anchor='center')
        if start > 0:
            self.button(w - pad - 120, nav_y, 120, 'Daha eski ›', lambda: self.change_admin_page(1))
        self.label(pad, h - 27, 'Dosya: ' + str(self.log_dir / 'geri_bildirim.csv'), 8, MUTED,
                   width=w - 2 * pad)

    def change_admin_page(self, amount):
        self.admin_page_index = max(0, self.admin_page_index + amount)
        self.draw()

    def open_admin_detail(self, index):
        self.admin_feedback_index = index
        self.admin_message_loaded_index = None
        self.page = 'admin_detail'
        self.draw()

    def draw_admin_detail(self, w, h, pad):
        rows = self.read_feedback()
        index = self.admin_feedback_index
        if index is None or index < 0 or index >= len(rows):
            self.page = 'admin'
            self.draw()
            return
        row = rows[index]
        outcome = {'zamaninda': 'Zamanında geldi', 'gec': 'Geç geldi',
                   'gelmedi_iptal': 'Gelmedi / iptal'}.get(row.get('geri_bildirim'), row.get('geri_bildirim', ''))
        kind = {'canli': 'Canlı İETT tahmini', 'hesaplanan': 'Tarifeden hesaplandı',
                'tarife': 'Tarife', 'tahmin_yok': 'Tahmin yok'}.get(row.get('tahmin_turu'), '')
        self.label(pad, 104, 'Geri bildirim mesajı', 15, TEXT, bold=True)
        self.button(w - pad - 110, 98, 110, '‹ Kayıtlar', lambda: self.set_page('admin'))
        self.label(pad, 151, f"{row.get('hat', '')}  ·  {row.get('tahmini_saat') or 'Saat bilgisi yok'}  ·  {kind}",
                   11, TEXT, bold=True, width=w - 2 * pad - 20)
        self.label(pad, 180, f"Yanıt: {outcome}    ·    {row.get('kayit_zamani', '').replace('T', ' ')[:16]}",
                   9, MUTED, width=w - 2 * pad - 20)
        self.label(pad, 224, 'Kullanıcının notu', 10, MUTED)
        if self.admin_message_loaded_index != index:
            self.admin_message_widget.configure(state='normal')
            self.admin_message_widget.delete('1.0', 'end')
            self.admin_message_widget.insert('1.0', row.get('mesaj') or 'Kullanıcı mesaj eklememiş.')
            self.admin_message_widget.configure(state='disabled')
            self.admin_message_loaded_index = index
        text_y = 252
        text_h = max(100, h - text_y - 90)
        self.admin_message_widget.place(x=pad, y=text_y, width=w - 2 * pad - 18, height=text_h)
        self.admin_message_scroll.place(x=w - pad - 16, y=text_y, width=16, height=text_h)
        self.button(pad, h - 64, 90, 'Sil', lambda: self.delete_feedback(index))

    def delete_feedback(self, index):
        rows = self.read_feedback()
        if index < 0 or index >= len(rows):
            return
        row = rows[index]
        if not messagebox.askyesno('Geri bildirimi sil',
                                   f"{row.get('hat', '')} hattının bu geri bildirim kaydını silmek istiyor musunuz?",
                                   parent=self.root):
            return
        del rows[index]
        path = self.log_dir / 'geri_bildirim.csv'
        temp_path = path.with_suffix('.tmp')
        try:
            self.write_feedback_rows(rows)
            self.admin_message = ''
            if self.page == 'admin_detail':
                self.page = 'admin'
                self.admin_feedback_index = None
                self.admin_message_loaded_index = None
        except OSError:
            logging.exception('Geri bildirim kaydı silinemedi')
            self.admin_message = 'Kayıt silinemedi; dosya kullanımda veya erişilemiyor.'
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        self.draw()

    def leave_admin(self):
        self.admin_password = ''
        self.admin_message = ''
        self.keyboard_open = False
        self.keyboard_target = None
        self.page = 'board'
        self.draw()

    def set_page(self, page):
        self.page = page
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
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as pool:
                iett_future = pool.submit(self.client.board)
                ring_future = pool.submit(self.ring_client.board)
                data, error, ring = None, '', None
                try:
                    data = iett_future.result()
                except Exception as exc:
                    logging.exception('İETT bağlantısı')
                    error = str(exc)
                try:
                    ring = ring_future.result()
                except Exception as exc:
                    logging.exception('Okan ring tarifesi')
                    if data is None:
                        data = {'routes': [], 'errors': [], 'updated_at': time.time()}
                    data['ring_error'] = str(exc)
                if ring:
                    if data is None:
                        data = {'routes': [], 'errors': [], 'updated_at': time.time()}
                    data['ring_routes'] = ring['routes']
                    data['ring_updated_at'] = ring['updated_at']
                    data['ring_cached'] = ring.get('cached', False)
                    data['ring_error'] = ''
                self.results.put((data, error, ring))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            result = self.results.get_nowait()
            data, error = result[0], result[1]
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
        self.activity()
        if self.keyboard_open:
            self.keyboard_open = False
            self.draw()
        elif self.page in ('admin_login', 'admin', 'admin_detail'):
            self.leave_admin()
        elif self.page == 'feedback_log':
            self.set_page('feedback')
        elif self.page == 'feedback':
            self.feedback_back()
        elif self.page == 'ring_detail':
            self.leave_ring_detail()
        elif self.selected:
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
        if self.idle_job:
            self.root.after_cancel(self.idle_job)
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
    app = App(root, kiosk=args.kiosk, log_dir=log_dir)
    if args.smoke_test:
        root.after(8000, app.close)
    root.mainloop()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
