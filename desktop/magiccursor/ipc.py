"""Tek örnek kontrolü ve komut satırından gelen komutlar için Unix soketi."""
import os
import socket
import threading

from gi.repository import GLib

from .config import SOCK

def send(cmd):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(SOCK)
        s.sendall(cmd.encode())
        s.close()
        return True
    except OSError:
        return False


def serve(app):
    try:
        os.unlink(SOCK)
    except FileNotFoundError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK)
    os.chmod(SOCK, 0o600)
    srv.listen(4)

    def loop():
        while True:
            conn, _ = srv.accept()
            try:
                cmd = conn.recv(256).decode().strip()
            finally:
                conn.close()
            if cmd and cmd != 'ping':
                GLib.idle_add(app.command, cmd)
    threading.Thread(target=loop, daemon=True).start()
