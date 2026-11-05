"""Ortak arayüz parçaları: CSS, şeffaf pencereler ve vurgulama çerçevesi."""
import cairo
from gi.repository import Gdk, Gio, Gtk

from .config import PALETTE

CSS = b"""
window.mc { background-color: transparent; }
.mc-card { border-radius: 14px; padding: 10px 12px; margin: 10px;
           box-shadow: 0 4px 18px rgba(0,0,0,0.22); }
.mc-light .mc-card { background-color: #ffffff; color: #1f1f1f; border: 1px solid rgba(155,114,203,0.35); }
.mc-dark  .mc-card { background-color: #202124; color: #e8eaed; border: 1px solid rgba(155,114,203,0.45); }
.mc-head { font-size: 9pt; opacity: 0.75; }
.mc-chat { margin-top: 4px; padding-top: 8px; border-top: 1px solid rgba(128,128,128,0.25); }
.mc-a    { font-size: 10pt; }
.mc-q    { font-size: 9.5pt; font-weight: bold; color: #9b72cb; margin-top: 4px; }
entry.mc-entry { border-radius: 999px; padding: 4px 12px; min-height: 28px; font-size: 10pt; box-shadow: none; }
.mc-light entry.mc-entry { background-color: rgba(0,0,0,0.04); border: 1px solid rgba(155,114,203,0.4); color: #1f1f1f; }
.mc-dark  entry.mc-entry { background-color: rgba(255,255,255,0.06); border: 1px solid rgba(155,114,203,0.5); color: #e8eaed; }
button.mc-chip { border-radius: 999px; padding: 3px 11px; min-height: 26px; font-size: 9.5pt;
                 background-image: none; box-shadow: none; text-shadow: none; }
.mc-light button.mc-chip { background-color: rgba(0,0,0,0.045); border: 1px solid rgba(0,0,0,0.08); color: #1f1f1f; }
.mc-dark  button.mc-chip { background-color: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.1); color: #e8eaed; }
.mc-light button.mc-chip:hover { background-color: rgba(66,133,244,0.14); }
.mc-dark  button.mc-chip:hover { background-color: rgba(138,180,248,0.2); }
button.mc-chip.primary { background-image: linear-gradient(135deg, rgba(66,133,244,0.22), rgba(155,114,203,0.22), rgba(217,101,112,0.18)); }
.mc-pill { border-radius: 999px; padding: 4px 6px 4px 14px; margin: 8px; box-shadow: 0 3px 12px rgba(0,0,0,0.2); }
.mc-light .mc-pill { background-color: #ffffff; color: #1f1f1f; border: 1px solid rgba(155,114,203,0.35); }
.mc-dark  .mc-pill { background-color: #202124; color: #e8eaed; border: 1px solid rgba(155,114,203,0.45); }
.mc-star { color: #9b72cb; font-weight: bold; }
.mc-pill button { border-radius: 999px; padding: 2px 10px; min-height: 22px; font-size: 9pt; background-image: none; box-shadow: none; }
"""


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

    def show(self, rect):
        p = self.PAD
        x0, y0, x1, y1 = rect
        w, h = int(x1 - x0 + p * 2), int(y1 - y0 + p * 2)
        self.win.resize(max(w, 4), max(h, 4))
        self.win.move(int(x0 - p), int(y0 - p))
        self.win.show()
        self.win.queue_draw()

    def hide(self):
        self.win.hide()

    def draw(self, w, cr):
        clear_window(w, cr)
        W, H = w.get_allocated_width(), w.get_allocated_height()
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
