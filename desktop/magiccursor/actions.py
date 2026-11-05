"""Önerilerdeki eylemler: tarayıcıda aç, takvim, harita, çeviri, sesli okuma…"""
import datetime
import os
import subprocess
import time
import urllib.parse

from gi.repository import GLib

from .entities import looks_turkish

def xdg_open(target):
    subprocess.Popen(['xdg-open', target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def google(q):
    xdg_open('https://www.google.com/search?q=' + urllib.parse.quote(q))


def translate(t):
    tl = 'en' if looks_turkish(t) else 'tr'
    xdg_open(f'https://translate.google.com/?sl=auto&tl={tl}&text={urllib.parse.quote(t)}&op=translate')


def speak(t):
    subprocess.run(['spd-say', '-C'], stderr=subprocess.DEVNULL)
    subprocess.Popen(['spd-say', '-l', 'tr' if looks_turkish(t) else 'en', t],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def event_range(info):
    d = info['date']
    if info['has_time']:
        return d.strftime('%Y%m%dT%H%M%S'), (d + datetime.timedelta(hours=1)).strftime('%Y%m%dT%H%M%S')
    return d.strftime('%Y%m%d'), (d + datetime.timedelta(days=1)).strftime('%Y%m%d')


def local_tz():
    try:
        return os.path.realpath('/etc/localtime').split('zoneinfo/')[1]
    except Exception:
        return 'Europe/Istanbul'


def calendar_url(info, title, details):
    s, e = event_range(info)
    q = urllib.parse.urlencode({'action': 'TEMPLATE', 'text': title, 'dates': f'{s}/{e}',
                                'details': details, 'ctz': local_tz()})
    return 'https://calendar.google.com/calendar/render?' + q


def save_ics(info, title, details):
    s, e = event_range(info)
    dt = (lambda v: f':{v}') if info['has_time'] else (lambda v: f';VALUE=DATE:{v}')

    def esc(v):
        return v.replace('\\', '\\\\').replace(',', '\\,').replace(';', '\\;').replace('\n', '\\n')
    ics = '\r\n'.join([
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//MagicCursor//TR', 'BEGIN:VEVENT',
        f'UID:{int(time.time() * 1000)}@magic-cursor', 'DTSTAMP:' + datetime.datetime.now().strftime('%Y%m%dT%H%M%S'),
        'DTSTART' + dt(s), 'DTEND' + dt(e), 'SUMMARY:' + esc(title), 'DESCRIPTION:' + esc(details),
        'END:VEVENT', 'END:VCALENDAR', ''])
    folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or os.path.expanduser('~')
    path = os.path.join(folder, f"etkinlik-{info['date'].strftime('%Y%m%d-%H%M')}.ics")
    with open(path, 'w') as f:
        f.write(ics)
    return path


def hex_to_rgb(h):
    s = h[1:]
    if len(s) == 3:
        s = ''.join(c * 2 for c in s)
    n = int(s, 16)
    return f'rgb({(n >> 16) & 255}, {(n >> 8) & 255}, {n & 255})'


TYPE_META = {
    'date': ('📅', 'Tarih'), 'email': ('✉️', 'E-posta'), 'phone': ('📞', 'Telefon'),
    'address': ('📍', 'Adres'), 'url': ('🔗', 'Bağlantı'), 'price': ('💱', 'Fiyat'),
    'color': ('🎨', 'Renk'), 'text': ('✦', 'Metin'), 'region': ('◎', 'Seçili alan'),
}


class Chip:
    def __init__(self, icon, label, run, primary=False, stay=False):
        self.icon, self.label, self.run, self.primary, self.stay = icon, label, run, primary, stay
