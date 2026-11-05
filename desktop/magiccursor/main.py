"""Komut satırı giriş noktası."""
import os
import signal
import sys

from gi.repository import GLib, Gtk

from . import __doc__ as USAGE
from .app import MagicCursor
from .config import SOCK, log
from .ipc import send, serve

def main():
    cmd = ' '.join(sys.argv[1:]) or 'run'
    if cmd in ('-h', '--help', 'help'):
        print(USAGE)
        return
    if send('ping'):
        if cmd == 'run':
            print('Magic Cursor zaten çalışıyor.')
        else:
            send(cmd)
        return
    if cmd not in ('run', 'toggle', 'on', 'region'):
        print('Magic Cursor çalışmıyor.')
        return
    if os.environ.get('XDG_SESSION_TYPE') == 'wayland':
        print('Magic Cursor X11 oturumu gerektirir (Wayland desteklenmiyor).', file=sys.stderr)
        sys.exit(1)
    app = MagicCursor()
    serve(app)
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda *a: (app.command('quit'), False)[1])
    if cmd != 'run':
        GLib.timeout_add(300, lambda: (app.command(cmd), False)[1])
    log('çalışıyor — fareyi salla veya kısayolu kullan')
    try:
        Gtk.main()
    finally:
        try:
            os.unlink(SOCK)
        except OSError:
            pass
