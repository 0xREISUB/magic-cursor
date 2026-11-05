"""İmleç etrafındaki ışıltı ve açılıştaki savrulma animasyonu."""
import math
import time

import cairo
from gi.repository import Gdk, Gio, Gtk

from .config import PALETTE, log
from .widgets import clear_window

# Bibata tarzı ok (uç 0,0'da)
ARROW = [(0, 0), (0, 17), (4.2, 13.2), (7.2, 19.6), (10.2, 18.3), (7.3, 12.2), (12.6, 12.2)]


class CursorGlow:
    """İmlecin etrafında yumuşak ışıltı; açılışta alttan tutulmuş gibi savrulan ok animasyonu."""
    S = 120
    SWING = 0.6  # saniye

    def __init__(self, app):
        self.app = app
        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_app_paintable(True)
        vis = self.win.get_screen().get_rgba_visual()
        if vis:
            self.win.set_visual(vis)
        self.win.resize(self.S, self.S)
        self.win.connect('draw', self.draw)
        self.win.connect('realize', lambda w: w.input_shape_combine_region(cairo.Region()))
        self.t0 = 0.0
        self.running = self.suppressed = False
        self.swinging = False
        self.frame = 0
        try:
            size = Gio.Settings.new('org.gnome.desktop.interface').get_int('cursor-size')
        except Exception:
            size = 24
        self.scale = max(0.8, size / 24)
        # Sistemin gerçek imleç görüntüsü (ör. Bibata Modern Ice) — animasyonda bu döndürülür
        self.cur_surf, self.cur_hot = None, (0, 0)
        try:
            cur = Gdk.Cursor.new_from_name(app.display, 'default')
            surf, xh, yh = cur.get_surface()
            if surf is not None:
                self.cur_surf, self.cur_hot = surf, (xh, yh)
        except Exception as e:
            log('imleç görüntüsü alınamadı, varsayılan ok çizilecek:', e)

    def start(self, x, y, swing=True):
        self.follow(x, y)
        self.t0 = time.time()
        self.running, self.suppressed = True, False
        self.win.show()
        if swing and self.app.xcursor.dpy:
            self.swinging = True
            self.app.xcursor.hide()
        self.win.queue_draw()

    def stop(self):
        if self.swinging:
            self.swinging = False
            self.app.xcursor.show()
        self.running = False
        self.win.hide()

    def suppress(self, on):
        """Panel veya durum çubuğunun üzerindeyken ışıltıyı gizle (onların üstüne çizilmesin)."""
        if on == self.suppressed or not self.running or self.swinging:
            return
        self.suppressed = on
        self.win.hide() if on else self.win.show()

    def follow(self, x, y):
        self.win.move(int(x - self.S / 2), int(y - self.S / 2))

    def tick(self):
        self.frame += 1
        if self.swinging:
            if time.time() - self.t0 > self.SWING:
                self.swinging = False
                self.app.xcursor.show()
            self.win.queue_draw()
        elif self.frame % 3 == 0:  # ışıltı için ~20 fps yeterli
            self.win.queue_draw()

    def draw(self, w, cr):
        clear_window(w, cr)
        c = self.S / 2
        t = time.time()
        s = self.scale
        fade = min(1.0, (t - self.t0) / 0.35)
        pulse = 0.9 + 0.1 * math.sin(t * 2.6)
        # dört renkli, yavaşça dönen yumuşak ışıltı (okun gövdesi etrafında)
        bx, by = c + 5 * s, c + 9 * s
        for i, col in enumerate(PALETTE):
            a = t * 1.4 + i * math.pi / 2
            gx, gy = bx + math.cos(a) * 7 * s, by + math.sin(a) * 7 * s
            r = 24 * s * pulse
            g = cairo.RadialGradient(gx, gy, 0, gx, gy, r)
            g.add_color_stop_rgba(0, *col, 0.30 * fade)
            g.add_color_stop_rgba(1, *col, 0)
            cr.set_source(g)
            cr.arc(gx, gy, r, 0, math.tau)
            cr.fill()
        if self.swinging:
            el = t - self.t0
            # sönümlü salınım: alt uç sabit, üst uç savrulur
            ang = math.radians(28) * math.exp(-el * 6.5) * math.sin(el * 19)
            if self.cur_surf is not None:
                xh, yh = self.cur_hot
                cw, ch = self.cur_surf.get_width(), self.cur_surf.get_height()
                px, py = cw * 0.42, ch * 0.92  # pivot: imlecin alt ucu
                cr.save()
                cr.translate(c - xh + px, c - yh + py)
                cr.rotate(ang)
                cr.translate(-px, -py)
                cr.set_source_surface(self.cur_surf, 0, 0)
                cr.get_source().set_filter(cairo.FILTER_GOOD)
                cr.paint()
                cr.restore()
                return True
            px, py = 6 * s, 18.5 * s  # pivot: okun alt ucu
            cr.save()
            cr.translate(c + px, c + py)
            cr.rotate(ang)
            cr.translate(-px, -py)
            cr.move_to(ARROW[0][0] * s, ARROW[0][1] * s)
            for ax, ay in ARROW[1:]:
                cr.line_to(ax * s, ay * s)
            cr.close_path()
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.set_source_rgb(1, 1, 1)
            cr.fill_preserve()
            cr.set_source_rgb(0.07, 0.07, 0.08)
            cr.set_line_width(1.3 * s)
            cr.stroke()
            cr.restore()
        return True
