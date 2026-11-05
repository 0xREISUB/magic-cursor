"""Öneri paneli: hedefe göre çipler, panel penceresi ve basit eylemler."""
import datetime
import os
import re
import time
import urllib.parse

from gi.repository import Gdk, GLib, Gtk

from .actions import TYPE_LABEL, Chip, calendar_url, google, hex_to_rgb, save_ics, speak, xdg_open
from .entities import clip, find_entities, fmt_date, looks_turkish
from .widgets import panel_window, prefers_dark


class PanelMixin:
    def chips_for(self, t):
        if t.type == 'region':
            chips = []
            for e in find_entities(t.text)[:3]:
                acts = self.entity_chips(e, t.text)
                if acts:
                    c = acts[0]
                    c.label = f'{c.label} · {clip(e["text"], 20)}'
                    c.primary = True
                    chips.append(c)
            chips.append(Chip('starred-symbolic', 'Yapay zekâya sor', lambda: self.ask_ai(t), primary=True, stay=True))
            if t.text:
                chips += self.text_chips(t.text)
            if t.image:
                chips.append(Chip('image-x-generic-symbolic', 'Görüntüyü kopyala', lambda: self.copy_image(t.image), stay=True))
                chips.append(Chip('document-save-symbolic', 'Kaydet', lambda: self.save_image(t.image), stay=True))
            chips.append(Chip('window-close-symbolic', 'Seçimi kapat', self.release_region, stay=True))
            return chips
        if t.type == 'text':
            chips = self.text_chips(t.text)
            chips.insert(1, Chip('starred-symbolic', 'Açıkla', lambda: self.ask_ai(t), primary=True, stay=True))
            w = re.sub(r"^\W+|\W+$", '', t.word)
            if len(w) > 2:
                q = f'{w} ne demek' if looks_turkish(t.text) else f'{w} meaning'
                chips.insert(3, Chip('accessories-dictionary-symbolic', f'“{clip(w, 16)}” ne demek?', lambda: google(q)))
            return chips
        chips = self.entity_chips(t.entity, t.context)
        if chips:
            chips[0].primary = True
        return chips

    def text_chips(self, text):
        return [
            Chip('edit-copy-symbolic', 'Kopyala', lambda: self.copy(text), stay=True),
            Chip('system-search-symbolic', 'Ara', lambda: google(text)),
            Chip('preferences-desktop-locale-symbolic', 'İngilizceye çevir' if looks_turkish(text) else 'Türkçeye çevir',
                 lambda: self.ai_translate(text), stay=True),
            Chip('audio-volume-high-symbolic', 'Sesli oku', lambda: speak(text), stay=True),
        ]

    def entity_chips(self, e, context):
        t, typ = e['text'], e['type']
        if typ == 'date':
            title = clip(context.replace(t, ' '), 70) or 'Etkinlik'
            info = e['data']
            return [Chip('x-office-calendar-symbolic', 'Google Takvim’e ekle', lambda: xdg_open(calendar_url(info, title, context))),
                    Chip('document-save-symbolic', '.ics kaydet ve aç', lambda: xdg_open(save_ics(info, title, context))),
                    Chip('edit-copy-symbolic', 'Kopyala', lambda: self.copy(fmt_date(info)), stay=True)]
        if typ == 'email':
            return [Chip('mail-send-symbolic', 'E-posta yaz', lambda: xdg_open('mailto:' + t)),
                    Chip('edit-copy-symbolic', 'Adresi kopyala', lambda: self.copy(t), stay=True)]
        if typ == 'phone':
            digits = re.sub(r'\D', '', t)
            wa = '90' + digits[1:] if digits.startswith('0') else digits
            return [Chip('mail-unread-symbolic', 'WhatsApp', lambda: xdg_open('https://wa.me/' + wa)),
                    Chip('call-start-symbolic', 'Ara', lambda: xdg_open('tel:' + re.sub(r'[^\d+]', '', t))),
                    Chip('edit-copy-symbolic', 'Kopyala', lambda: self.copy(t), stay=True)]
        if typ == 'address':
            q = urllib.parse.quote(t)
            return [Chip('mark-location-symbolic', 'Haritada göster', lambda: xdg_open('https://www.google.com/maps/search/?api=1&query=' + q)),
                    Chip('find-location-symbolic', 'Yol tarifi', lambda: xdg_open('https://www.google.com/maps/dir/?api=1&destination=' + q)),
                    Chip('edit-copy-symbolic', 'Kopyala', lambda: self.copy(t), stay=True)]
        if typ == 'url':
            u = e['data']['url']
            return [Chip('web-browser-symbolic', 'Aç', lambda: xdg_open(u)), Chip('edit-copy-symbolic', 'Bağlantıyı kopyala', lambda: self.copy(u), stay=True)]
        if typ == 'price':
            a, c = e['data']['amount'], e['data']['currency']
            to = 'USD' if c == 'TL' else 'TL'
            return [Chip('accessories-calculator-symbolic', f'{to}’ye çevir', lambda: google(f'{a} {c} kaç {to}')),
                    Chip('edit-copy-symbolic', 'Kopyala', lambda: self.copy(t), stay=True)]
        if typ == 'color':
            return [Chip('edit-copy-symbolic', 'HEX kopyala', lambda: self.copy(t), stay=True),
                    Chip('color-select-symbolic', 'RGB kopyala', lambda: self.copy(hex_to_rgb(t)), stay=True)]
        return []

    def open_panel(self, t):
        self.close_panel()
        chips = self.chips_for(t)
        if not chips:
            return
        label = TYPE_LABEL.get(t.type, TYPE_LABEL['text'])
        if t.type == 'region':
            preview = f'{len(t.text)} karakter' if t.text else 'görüntü'
        elif t.type == 'date':
            preview = fmt_date(t.entity['data'])
        else:
            preview = t.text
        win = panel_window(prefers_dark())
        win.connect('key-press-event', self.on_panel_key)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class('mc-card')

        head = Gtk.Box(spacing=6)
        if t.type == 'color':
            rgba = Gdk.RGBA()
            if rgba.parse(t.text):
                sw = Gtk.DrawingArea()
                sw.set_size_request(12, 12)
                sw.connect('draw', lambda _w, cr: (cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1), cr.paint()))
                head.pack_start(sw, False, False, 0)
        kind = Gtk.Label(label=label.upper(), xalign=0)
        kind.get_style_context().add_class('mc-kind')
        head.pack_start(kind, False, False, 0)
        hl = Gtk.Label(label=clip(preview, 60), xalign=0)
        hl.set_ellipsize(3)
        hl.set_max_width_chars(56)
        hl.get_style_context().add_class('mc-head')
        head.pack_start(hl, True, True, 0)
        card.pack_start(head, False, False, 0)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(4 if len(chips) > 3 else len(chips))
        flow.set_min_children_per_line(min(2, len(chips)))
        flow.set_row_spacing(6)
        flow.set_column_spacing(6)
        for c in chips:
            b = Gtk.Button()
            inner = Gtk.Box(spacing=6)
            if c.icon:
                inner.pack_start(Gtk.Image.new_from_icon_name(c.icon, Gtk.IconSize.MENU), False, False, 0)
            inner.pack_start(Gtk.Label(label=c.label), False, False, 0)
            b.add(inner)
            b.set_relief(Gtk.ReliefStyle.NONE)
            ctx = b.get_style_context()
            ctx.add_class('mc-chip')
            if c.primary:
                ctx.add_class('primary')
            b.connect('clicked', lambda _b, c=c: self.run_chip(c))
            child = Gtk.FlowBoxChild()
            child.set_can_focus(False)
            child.add(b)
            flow.add(child)
        card.pack_start(flow, False, False, 0)

        # yapay zekâ sohbeti: kaydırılabilir mesajlar + devam sorusu kutusu
        self.chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.chat_scroll = Gtk.ScrolledWindow()
        self.chat_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.chat_scroll.set_propagate_natural_height(True)
        self.chat_scroll.set_max_content_height(340)
        self.chat_scroll.add(self.chat_box)
        self.chat_scroll.get_style_context().add_class('mc-chat')
        self.chat_scroll.set_no_show_all(True)
        card.pack_start(self.chat_scroll, False, False, 0)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text('Devam sorusu sor… (Enter)')
        self.entry.get_style_context().add_class('mc-entry')
        self.entry.set_no_show_all(True)
        self.entry.connect('activate', self.on_followup)
        self.entry.connect('button-press-event', lambda *_: (self.focus_panel(), False)[1])
        self.entry.connect('changed', lambda *_: setattr(self, 'last_activity', time.time()))
        card.pack_start(self.entry, False, False, 0)
        self.chat_msgs = []
        self.chat_busy = False

        win.add(card)
        card.show_all()
        self.panel_win = win
        self.panel_target = t
        self.place_panel()
        win.show_all()

    def place_panel(self):
        win, t = self.panel_win, self.panel_target
        if not win:
            return
        _, nat = win.get_preferred_size()
        pw, ph = nat.width, nat.height
        x0, y0, x1, y1 = t.rect
        y = y1 + 2
        if y + ph > self.H and y0 - 2 - ph > 0:
            y = y0 - 2 - ph
        px = self.last_xy[0] if self.last_xy[0] >= 0 else x0
        anchor = x0 - 10 if t.type == 'region' else min(max(px - 40, x0 - 10), x1)
        x = max(0, min(anchor, self.W - pw))
        y = max(0, min(y, self.H - ph))
        win.resize(pw, ph)
        win.move(int(x), int(y))
        self.panel_geom = (int(x), int(y), pw, ph)
        self.highlight.set_cutout(self.panel_geom)
        self.selector.update_holes()

    def close_panel(self):
        if self.panel_win:
            self.panel_win.destroy()
            self.panel_geom = None
            self.highlight.set_cutout(None)
            self.selector.update_holes()
        self.panel_win = None
        self.panel_target = None
        self.panel_pinned = False
        self.chat_box = self.chat_scroll = self.entry = None
        self.chat_msgs = []
        self.chat_busy = False

    def run_chip(self, c):
        self.last_activity = time.time()
        if c.stay:
            c.run()
        else:
            self.deactivate()
            GLib.timeout_add(50, lambda: (c.run(), False)[1])

    def copy(self, text):
        self.clipboard.set_text(text, -1)
        self.clipboard.store()
        self.flash('✓ Kopyalandı')

    def copy_image(self, pixbuf):
        self.clipboard.set_image(pixbuf)
        self.clipboard.store()
        self.flash('✓ Görüntü kopyalandı')

    def save_image(self, pixbuf):
        folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) or os.path.expanduser('~')
        path = os.path.join(folder, 'magic-cursor-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.png')
        pixbuf.savev(path, 'png', [], [])
        self.flash('✓ Kaydedildi: ' + os.path.basename(path))
