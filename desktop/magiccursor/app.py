"""Ana uygulama: imleç takibi, sallama algılama, aç/kapat, tarama, hover ve alan seçimi."""
import threading
import time
import traceback

from gi.repository import Gdk, GLib, Gtk

from .chat import ChatMixin
from .config import CONFIG_PATH, IDLE_TIMEOUT, WIGGLE, load_config, log
from .entities import find_entities
from .games import blocked_reason
from .glow import CursorGlow
from .ocr import Target, bbox, in_rect, ocr_langs, run_ocr
from .panel import PanelMixin
from .selector import RegionSelector
from .widgets import CSS, Highlight, popup, prefers_dark
from .wiggle import WiggleDetector
from .x11 import XCursor


class MagicCursor(PanelMixin, ChatMixin):
    def __init__(self):
        self.display = Gdk.Display.get_default()
        self.seat = self.display.get_default_seat()
        self.pointer = self.seat.get_pointer()
        self.root = Gdk.get_default_root_window()
        self.W, self.H = self.root.get_width(), self.root.get_height()
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.cfg = load_config()
        self.langs = ocr_langs()
        if not self.langs:
            log('UYARI: tesseract bulunamadı, metin tanıma kapalı')
        elif 'tur' not in self.langs:
            log('İpucu: Türkçe karakterler için `sudo apt install tesseract-ocr-tur`')
        if not self.cfg['groq_api_key']:
            log(f'Groq anahtarı yok — yapay zekâ için {CONFIG_PATH} dosyasına "groq_api_key" ekleyin')

        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.active = False
        self.snapshot = None
        self.paras, self.entities = [], []
        self.scan_state, self.scan_token = 'idle', 0
        self.target = None
        self.panel_win = None
        self.panel_target = None
        self.panel_pinned = False
        self.chat_box = self.chat_scroll = self.entry = None
        self.chat_msgs = []
        self.chat_busy = False
        self.pending = None   # (target, show_at)
        self.hide_at = 0.0
        self.last_xy = (-1, -1)
        self.last_activity = 0.0
        self.was_pressed = False
        self.wiggle = WiggleDetector(self.cfg.get('wiggle'))

        self.chat_box = self.chat_scroll = self.entry = None
        self.chat_msgs = []
        self.chat_busy = False

        self.xcursor = XCursor()
        self.glow = CursorGlow(self)
        self.panel_geom = self.pill_geom = None
        self.highlight = Highlight()
        self.selector = RegionSelector(self)
        self.pill = None
        self.pill_label = None
        GLib.timeout_add(16, self.poll)

    def command(self, cmd):
        try:
            if cmd == 'toggle':
                self.deactivate() if self.active else self.activate()
            elif cmd == 'on':
                self.activate()
            elif cmd == 'off':
                self.deactivate()
            elif cmd == 'region':
                self.activate()
            elif cmd == 'quit':
                self.deactivate()
                Gtk.main_quit()
            elif cmd.startswith('debug-hover '):
                _, x, y = cmd.split()
                self.last_xy = (float(x), float(y))
                self.handle_pointer(float(x), float(y), time.time())
            elif cmd.startswith('debug-region '):
                self.select_region(tuple(float(v) for v in cmd.split()[1:5]))
            elif cmd == 'debug-ai':
                if self.panel_target:
                    self.ask_ai(self.panel_target)
            elif cmd == 'debug-state':
                log('active', self.active, 'state', self.scan_state, 'entities', [(e.type, e.text, e.rect) for e in self.entities[:8]],
                    'target', self.target and self.target.type, 'panel', bool(self.panel_win),
                    'chat', [(m['role'], str(m['content'])[:200]) for m in self.chat_msgs],
                    'entry', self.entry and self.entry.get_visible(),
                    'focus', self.panel_win and self.panel_win.is_active())
            elif cmd == 'debug-translate':
                if self.panel_target:
                    self.ai_translate(self.panel_target.text)
            elif cmd.startswith('debug-ask '):
                if self.entry:
                    self.entry.set_text(cmd[len('debug-ask '):])
                    self.on_followup(self.entry)
        except Exception:
            traceback.print_exc()
        return False

    # ─────────────── Döngü ───────────────
    def poll(self):
        try:
            _, x, y, mask = self.root.get_device_position(self.pointer)
        except Exception:
            return True
        if WIGGLE and not self.selector.drawing:
            if self.wiggle.feed(x, y, time.monotonic()):
                self.on_wiggle()
        if not self.active:
            return True
        t = time.time()
        pressed = bool(mask & (Gdk.ModifierType.BUTTON1_MASK | Gdk.ModifierType.BUTTON3_MASK))
        if pressed and not self.was_pressed and not self.selector.visible() and not self.over_own(x, y):
            # başka bir yere tıklandı → ekran değişecek, kapat
            self.was_pressed = True
            self.deactivate()
            return True
        self.was_pressed = pressed
        if (x, y) != self.last_xy:
            self.last_xy = (x, y)
            self.last_activity = t
            self.glow.follow(x, y)
            self.handle_pointer(x, y, t)
        self.glow.suppress(self.over_own(x, y))
        self.glow.tick()
        if self.pending and t >= self.pending[1]:
            tgt = self.pending[0]
            self.pending = None
            if tgt is self.target:
                self.open_panel(tgt)
        if self.hide_at and t >= self.hide_at:
            self.hide_at = 0
            self.clear_target()
        if not self.panel_pinned and t - self.last_activity > IDLE_TIMEOUT:
            self.deactivate()
        return True

    def over_own(self, x, y):
        for w in (self.panel_win, self.pill):
            if w and w.get_visible():
                wx, wy = w.get_position()
                ww, wh = w.get_size()
                if wx <= x <= wx + ww and wy <= y <= wy + wh:
                    return True
        return False

    def on_wiggle(self):
        if self.active:
            self.deactivate()
            return
        reason = blocked_reason(self.cfg)
        if reason:
            log('sallama yok sayıldı:', reason)
            return
        self.activate()

    # ─────────────── Aç / kapat ───────────────
    def activate(self):
        if self.active:
            return
        self.snapshot = Gdk.pixbuf_get_from_window(self.root, 0, 0, self.W, self.H)
        self.active = True
        self.last_activity = time.time()
        self.last_xy = (-1, -1)
        self.was_pressed = False
        self.paras, self.entities = [], []
        self.scan_token += 1
        _, px, py, _ = self.root.get_device_position(self.pointer)
        self.selector.arm()
        self.glow.start(px, py)
        self.show_pill()
        if self.langs and self.snapshot:
            self.scan_state = 'scanning'
            self.set_pill_text('okunuyor…')
            threading.Thread(target=self.scan, args=(self.scan_token, self.snapshot), daemon=True).start()
        else:
            self.scan_state = 'ready'
            self.set_pill_text('hazır')

    def deactivate(self):
        if not self.active:
            return
        self.active = False
        self.scan_token += 1
        self.selector.disarm()
        self.glow.stop()
        self.clear_target()
        if self.pill:
            self.pill.destroy()
        self.pill = self.pill_label = None
        self.pill_geom = None
        self.snapshot = None
        self.paras, self.entities = [], []
        self.wiggle.reset(time.monotonic(), cooldown=True)

    # ─────────────── Durum çubuğu ───────────────
    def show_pill(self):
        self.pill = popup(prefers_dark())
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.get_style_context().add_class('mc-pill')
        star = Gtk.Label(label='✦')
        star.get_style_context().add_class('mc-star')
        self.pill_label = Gtk.Label(label='Magic Cursor')
        btn_close = Gtk.Button(label='✕')
        btn_close.set_relief(Gtk.ReliefStyle.NONE)
        btn_close.connect('clicked', lambda *_: self.deactivate())
        for wdg in (star, self.pill_label, btn_close):
            box.pack_start(wdg, False, False, 0)
        self.pill.add(box)
        box.show_all()
        self.place_pill()
        self.pill.show_all()

    def place_pill(self):
        if self.pill:
            _, nat = self.pill.get_preferred_size()
            self.pill.resize(nat.width, nat.height)
            self.pill.move(int((self.W - nat.width) / 2), 4)
            self.pill_geom = (int((self.W - nat.width) / 2), 4, nat.width, nat.height)
            self.selector.update_holes()

    def set_pill_text(self, status):
        if self.pill_label:
            self.pill_label.set_text(f'Magic Cursor · {status}')
            self.place_pill()

    def flash(self, msg):
        """Kısa bildirimi durum çubuğunda göster."""
        if not self.pill_label:
            return
        self.set_pill_text(msg)
        token = self.scan_token

        def restore():
            if self.active and token == self.scan_token and self.scan_state == 'ready':
                self.set_pill_text(self.ready_text())
            return False
        GLib.timeout_add(1600, restore)

    def ready_text(self):
        n = len(self.entities)
        return (f'{n} öğe' if n else 'hazır') + ' · basılı tutup daire çiz'

    # ─────────────── OCR ───────────────
    def scan(self, token, pixbuf):
        t0 = time.time()
        try:
            paras = run_ocr(pixbuf, self.langs)
        except Exception as e:
            log('OCR hatası:', e)
            paras = []
        log(f'OCR {time.time() - t0:.2f}s, {sum(len(p.words) for p in paras)} kelime')
        GLib.idle_add(self.scan_done, token, paras)

    def scan_done(self, token, paras):
        if token != self.scan_token or not self.active:
            return False
        self.paras = paras
        ents = []
        for p in paras:
            for e in find_entities(p.text):
                ws = [w for w in p.words if w.start < e['end'] and e['start'] < w.end]
                if ws:
                    ents.append(Target(e['type'], bbox(ws), text=e['text'], entity=e, context=p.text))
        self.entities = ents
        self.scan_state = 'ready'
        self.set_pill_text(self.ready_text())
        self.last_xy = (-1, -1)  # mevcut konumu yeniden değerlendir
        return False

    def hit_test(self, x, y):
        for t in self.entities:
            if in_rect(x, y, t.rect, 4):
                return t
        for p in self.paras:
            for w in p.words:
                if in_rect(x, y, (w.x, w.y, w.x + w.w, w.y + w.h), 3):
                    words = p.words if len(p.text) <= 350 else [v for v in p.words if v.line == w.line]
                    text = ' '.join(v.text for v in words)
                    if len(text) < 2:
                        return None
                    return Target('text', bbox(words), text=text, context=text, word=w.text)
        return None

    # ─────────────── Hover ───────────────
    def handle_pointer(self, x, y, t):
        if self.selector.drawing:
            return
        if self.panel_win and self.over_own(x, y):
            self.hide_at = 0
            return
        # alan seçiliyken geri kalan her şey pasif: hover ile seçim ezilmez
        if self.panel_pinned or (self.target and self.target.type == 'region'):
            return
        tgt = self.hit_test(x, y) if self.scan_state == 'ready' else None
        if tgt and self.target and tgt.key() == self.target.key():
            self.hide_at = 0
            return
        if tgt is None:
            if self.target and not self.hide_at:
                self.hide_at = t + 0.45
            return
        self.hide_at = 0
        self.close_panel()
        self.target = tgt
        self.highlight.show(tgt.rect)
        self.pending = (tgt, t + 0.3)

    def passthrough(self, button):
        """Katmana gelen tıklama/tekerlek: modu kapat, olayı alttaki uygulamaya ilet."""
        self.deactivate()
        self.display.flush()
        GLib.timeout_add(35, lambda: (self.xcursor.fake_click(button), False)[1])

    def release_region(self):
        """Alan seçimini bırak, normal hover moduna dön."""
        self.clear_target()
        self.last_xy = (-1, -1)

    def clear_target(self):
        self.target = None
        self.pending = None
        self.hide_at = 0
        self.highlight.hide()
        self.close_panel()

    # ─────────────── Alan seçimi ───────────────
    def select_region(self, box):
        if not self.active or not self.snapshot:
            return
        x0, y0 = max(0, int(box[0])), max(0, int(box[1]))
        x1, y1 = min(self.W, int(box[2])), min(self.H, int(box[3]))
        if x1 - x0 < 5 or y1 - y0 < 5:
            return
        image = self.snapshot.new_subpixbuf(x0, y0, x1 - x0, y1 - y0).copy()
        self.clear_target()
        tgt = Target('region', (x0, y0, x1, y1), image=image)
        self.target = tgt
        self.highlight.show(tgt.rect)
        self.set_pill_text('alan okunuyor…')
        token = self.scan_token

        def work():
            text = ''
            if self.langs:
                try:  # seçili alanı 2x büyütüp ayrıca oku → daha doğru
                    text = '\n'.join(p.text for p in run_ocr(image, self.langs, scale=2))
                except Exception as e:
                    log('alan OCR hatası:', e)
            GLib.idle_add(done, text)

        def done(text):
            if token != self.scan_token or self.target is not tgt:
                return False
            tgt.text = tgt.context = text[:3000]
            self.open_panel(tgt)
            self.panel_pinned = True
            self.set_pill_text(self.ready_text() if self.scan_state == 'ready' else 'okunuyor…')
            return False
        threading.Thread(target=work, daemon=True).start()
