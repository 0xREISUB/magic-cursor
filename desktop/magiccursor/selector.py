"""Daire çizerek alan seçimi için şeffaf giriş katmanı."""
import cairo
from gi.repository import Gdk, Gtk

from .config import PALETTE
from .widgets import clear_window

class RegionSelector:
    """Magic mod açıkken ekranın üstündeki şeffaf giriş katmanı.
    Basılı tutup sürükle → alan seçimi. Normal tıklama / tekerlek → mod kapanır ve olay
    XTest ile alttaki uygulamaya aynen iletilir. Panel ve durum çubuğunun yerinde delik vardır."""

    def __init__(self, app):
        self.app = app
        self.path = []
        self.drawing = False
        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_app_paintable(True)
        vis = self.win.get_screen().get_rgba_visual()
        if vis:
            self.win.set_visual(vis)
        self.win.move(0, 0)
        self.win.resize(app.W, app.H)
        self.win.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK |
                            Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.SCROLL_MASK)
        self.win.connect('draw', self.draw)
        self.win.connect('button-press-event', self.on_press)
        self.win.connect('motion-notify-event', self.on_motion)
        self.win.connect('button-release-event', self.on_release)
        self.win.connect('scroll-event', self.on_scroll)

    def visible(self):
        return self.win.get_visible()

    def arm(self):
        self.path, self.drawing = [], False
        self.win.show()
        self.update_holes()

    def disarm(self):
        self.path, self.drawing = [], False
        self.win.hide()

    def update_holes(self):
        if not self.visible():
            return
        reg = cairo.Region(cairo.RectangleInt(0, 0, self.app.W, self.app.H))
        for g in (self.app.panel_geom, self.app.pill_geom):
            if g:
                reg.subtract(cairo.RectangleInt(*(int(v) for v in g)))
        self.win.input_shape_combine_region(reg)

    def on_press(self, _w, ev):
        if ev.type != Gdk.EventType.BUTTON_PRESS:
            return True  # çift tık olaylarını yok say
        if ev.button == 1:
            self.path = [(ev.x_root, ev.y_root)]
            self.drawing = True
        else:
            self.app.passthrough(ev.button)
        return True

    def on_motion(self, _w, ev):
        if self.drawing and self.path:
            x0, y0 = self.path[-1]
            x1, y1 = ev.x_root, ev.y_root
            self.path.append((x1, y1))
            self.win.queue_draw_area(int(min(x0, x1)) - 6, int(min(y0, y1)) - 6,
                                     int(abs(x1 - x0)) + 12, int(abs(y1 - y0)) + 12)
        return True

    def on_release(self, _w, ev):
        if ev.button != 1 or not self.drawing:
            return True
        path = self.path
        self.path, self.drawing = [], False
        self.win.queue_draw()
        xs, ys = [p[0] for p in path], [p[1] for p in path]
        box = (min(xs), min(ys), max(xs), max(ys))
        if box[2] - box[0] < 15 and box[3] - box[1] < 15:
            self.app.passthrough(1)  # normal tıklama → uygulamaya ilet
        else:
            self.app.select_region(box)
        return True

    def on_scroll(self, _w, ev):
        btn = {Gdk.ScrollDirection.UP: 4, Gdk.ScrollDirection.DOWN: 5,
               Gdk.ScrollDirection.LEFT: 6, Gdk.ScrollDirection.RIGHT: 7}.get(ev.direction)
        if btn:
            self.app.passthrough(btn)
        return True

    def draw(self, w, cr):
        clear_window(w, cr)
        if len(self.path) > 1:
            cr.set_line_width(3)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            g = cairo.LinearGradient(0, 0, self.app.W, self.app.H)
            for i, c in enumerate(PALETTE):
                g.add_color_stop_rgb(i / 3, *c)
            cr.set_source(g)
            cr.move_to(*self.path[0])
            for p in self.path[1:]:
                cr.line_to(*p)
            cr.stroke()
        return True
