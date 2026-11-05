"""Ortak arayüz parçaları: CSS, şeffaf pencereler ve vurgulama çerçevesi."""
import cairo
from gi.repository import Gdk, Gio, Gtk

from .config import PALETTE

CSS = """
window.mc { background-color: transparent; }

/* kart */
.mc-card { border-radius: 12px; padding: 12px; margin: 10px; box-shadow: 0 6px 22px rgba(0,0,0,0.30); }
.mc-light .mc-card { background-color: #ffffff; color: #1f2328; border: 1px solid rgba(0,0,0,0.12); }
.mc-dark  .mc-card { background-color: #1e1f22; color: #e4e4e6; border: 1px solid rgba(255,255,255,0.09); }
.mc-kind { font-size: 8pt; font-weight: bold; opacity: 0.5; }
.mc-head { font-size: 9pt; opacity: 0.7; }

/* eylem düğmeleri */
button.mc-chip { border-radius: 8px; padding: 4px 10px; min-height: 26px; font-size: 9pt;
                 background-image: none; box-shadow: none; text-shadow: none; }
button.mc-chip image { opacity: 0.7; }
.mc-light button.mc-chip { background-color: transparent; border: 1px solid rgba(0,0,0,0.12); color: #1f2328; }
.mc-dark  button.mc-chip { background-color: transparent; border: 1px solid rgba(255,255,255,0.10); color: #e4e4e6; }
.mc-light button.mc-chip:hover { background-color: rgba(0,0,0,0.05); }
.mc-dark  button.mc-chip:hover { background-color: rgba(255,255,255,0.07); }
.mc-light button.mc-chip.primary { background-color: rgba(0,0,0,0.06); border-color: rgba(0,0,0,0.20); }
.mc-dark  button.mc-chip.primary { background-color: rgba(255,255,255,0.09); border-color: rgba(255,255,255,0.18); }

/* sohbet */
.mc-chat { margin-top: 2px; padding-top: 10px; border-top: 1px solid rgba(128,128,128,0.22); }
.mc-a    { font-size: 10pt; }
.mc-q    { font-size: 8.5pt; font-weight: bold; opacity: 0.5; margin-top: 6px; }
entry.mc-entry { border-radius: 8px; padding: 5px 10px; min-height: 30px; font-size: 10pt; box-shadow: none; }
.mc-light entry.mc-entry { background-color: rgba(0,0,0,0.03); border: 1px solid rgba(0,0,0,0.15); color: #1f2328; }
.mc-dark  entry.mc-entry { background-color: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.12); color: #e4e4e6; }

/* üst durum çubuğu */
.mc-pill { border-radius: 10px; padding: 3px 6px 3px 12px; margin: 8px; box-shadow: 0 3px 12px rgba(0,0,0,0.25); }
.mc-light .mc-pill { background-color: #ffffff; color: #1f2328; border: 1px solid rgba(0,0,0,0.12); }
.mc-dark  .mc-pill { background-color: #1e1f22; color: #e4e4e6; border: 1px solid rgba(255,255,255,0.09); }
.mc-star { opacity: 0.55; }
.mc-pill button { border-radius: 6px; padding: 2px 8px; min-height: 22px; font-size: 9pt; background-image: none; box-shadow: none; }
""".encode()


def prefers_dark():
    try:
        s = Gio.Settings.new('org.gnome.desktop.interface')
        return s.get_string('color-scheme') == 'prefer-dark' or 'dark' in s.get_string('gtk-theme').lower()
    except Exception:
        return False


def clear_window(_w, cr):
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    return False


def popup(dark):
    w = Gtk.Window(type=Gtk.WindowType.POPUP)
    w.set_app_paintable(True)
    vis = w.get_screen().get_rgba_visual()
    if vis:
        w.set_visual(vis)
    ctx = w.get_style_context()
    ctx.add_class('mc')
    ctx.add_class('mc-dark' if dark else 'mc-light')
    w.connect('draw', clear_window)
    return w


def panel_window(dark):
    """Klavye alabilen ama hover'da odağı çalmayan, çerçevesiz üst pencere."""
    w = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    w.set_decorated(False)
    w.set_resizable(False)
    w.set_keep_above(True)
    w.set_skip_taskbar_hint(True)
    w.set_skip_pager_hint(True)
    w.set_type_hint(Gdk.WindowTypeHint.UTILITY)
    w.set_accept_focus(False)
    w.set_focus_on_map(False)
    w.set_app_paintable(True)
    vis = w.get_screen().get_rgba_visual()
    if vis:
        w.set_visual(vis)
    ctx = w.get_style_context()
    ctx.add_class('mc')
    ctx.add_class('mc-dark' if dark else 'mc-light')
    w.connect('draw', clear_window)
    return w


class Highlight:
    """Hedefin etrafında tıklamaları engellemeyen ince, statik bir çerçeve."""
    PAD = 4

    def __init__(self):
        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_app_paintable(True)
        vis = self.win.get_screen().get_rgba_visual()
        if vis:
            self.win.set_visual(vis)
        self.win.connect('draw', self.draw)
        self.win.connect('realize', lambda w: w.input_shape_combine_region(cairo.Region()))
        self.origin, self.size, self.cutout = (0, 0), (4, 4), None

    def show(self, rect):
        p = self.PAD
        x0, y0, x1, y1 = rect
        w, h = max(int(x1 - x0 + p * 2), 4), max(int(y1 - y0 + p * 2), 4)
        self.origin, self.size = (int(x0 - p), int(y0 - p)), (w, h)
        self.win.resize(w, h)
        self.win.move(*self.origin)
        self.win.show()
        self.apply_cutout()
        self.win.queue_draw()

    def set_cutout(self, geom, margin=8):
        """Panelin kartının kapladığı alanı (x, y, w, h; ekran koordinatı) çerçeve çiziminden hariç tut,
        böylece seçim çerçevesi panelin üstüne çizilmez. geom=None bunu kaldırır."""
        self.cutout = None if geom is None else (geom[0] + margin, geom[1] + margin,
                                                  geom[2] - 2 * margin, geom[3] - 2 * margin)
        self.apply_cutout()

    def apply_cutout(self):
        self.win.queue_draw()

    def hide(self):
        self.win.hide()

    def draw(self, w, cr):
        clear_window(w, cr)
        W, H = w.get_allocated_width(), w.get_allocated_height()
        if self.cutout:  # panelin kapladığı yere hiç çizme → orası şeffaf kalır, panel görünür
            x, y, cw, ch = self.cutout
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.rectangle(0, 0, W, H)
            cr.rectangle(x - self.origin[0], y - self.origin[1], max(cw, 0), max(ch, 0))
            cr.clip()
            cr.set_fill_rule(cairo.FILL_RULE_WINDING)
        r = min(8, W / 2, H / 2)
        x, y, ww, hh = 1, 1, W - 2, H - 2
        cr.new_sub_path()
        cr.arc(x + ww - r, y + r, r, -1.5708, 0)
        cr.arc(x + ww - r, y + hh - r, r, 0, 1.5708)
        cr.arc(x + r, y + hh - r, r, 1.5708, 3.1416)
        cr.arc(x + r, y + r, r, 3.1416, 4.7124)
        cr.close_path()
        cr.set_source_rgba(*PALETTE[0], 0.07)
        cr.fill_preserve()
        g = cairo.LinearGradient(0, 0, W, H)
        for i, c in enumerate(PALETTE):
            g.add_color_stop_rgb(i / 3, *c)
        cr.set_source(g)
        cr.set_line_width(2)
        cr.stroke()
        return True
