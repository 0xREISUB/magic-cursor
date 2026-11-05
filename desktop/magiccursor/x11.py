"""Doğrudan X11 çağrıları: imleci gizle/göster (XFixes) ve tıklama ilet (XTest)."""
import ctypes

from .config import log

class XCursor:
    """Gerçek sistem imlecini XFixes ile geçici olarak gizler (süreç kapanırsa X otomatik geri getirir)."""

    def __init__(self):
        self.dpy = None
        self.hidden = False
        try:
            self.x11 = ctypes.CDLL('libX11.so.6')
            self.xf = ctypes.CDLL('libXfixes.so.3')
            self.x11.XOpenDisplay.restype = ctypes.c_void_p
            self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self.x11.XDefaultRootWindow.restype = ctypes.c_ulong
            self.x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            self.x11.XFlush.argtypes = [ctypes.c_void_p]
            for fn in (self.xf.XFixesHideCursor, self.xf.XFixesShowCursor):
                fn.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            self.dpy = self.x11.XOpenDisplay(None)
            self.root = self.x11.XDefaultRootWindow(self.dpy) if self.dpy else 0
        except OSError as e:
            log('XFixes yok, imleç animasyonu kapalı:', e)

    def hide(self):
        if self.dpy and not self.hidden:
            self.xf.XFixesHideCursor(self.dpy, self.root)
            self.x11.XFlush(self.dpy)
            self.hidden = True

    def fake_click(self, button):
        """Tıklamayı/tekerleği imlecin bulunduğu yere sentetik olarak gönder."""
        if not self.dpy:
            return False
        try:
            if not hasattr(self, 'xtst'):
                self.xtst = ctypes.CDLL('libXtst.so.6')
                self.xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
            self.xtst.XTestFakeButtonEvent(self.dpy, button, 1, 0)
            self.xtst.XTestFakeButtonEvent(self.dpy, button, 0, 0)
            self.x11.XFlush(self.dpy)
            return True
        except OSError as e:
            log('XTest yok, tıklama iletilemedi:', e)
            return False

    def show(self):
        if self.dpy and self.hidden:
            self.xf.XFixesShowCursor(self.dpy, self.root)
            self.x11.XFlush(self.dpy)
            self.hidden = False
