#!/usr/bin/env python3
"""
Magic Cursor — sistem genelinde (X11 / GNOME) bağlamsal imleç.

  Fareyi hızlıca sağa-sola salla (veya Super+G) → Magic mod açılır, ekran okunur
  Bir şeyin üzerine gel → tarih, adres, e-posta, telefon, link, fiyat, renk, metin
                          için öneriler çıkar
  Sol tıkla basılı tutup daire çiz → o alanı seç, yapay zekâya sor
  Normal tıklama / tekerlek / ✕ → mod kapanır (tıklama alttaki uygulamaya iletilir)

Kullanım:
  magic_cursor.py            arka planda çalıştır
  magic_cursor.py toggle     aç / kapat
  magic_cursor.py quit       kapat

Yapay zekâ (Groq): ~/.config/magic-cursor/config.json içine
  {"groq_api_key": "gsk_..."}   yazın ya da GROQ_API_KEY ortam değişkenini kullanın.
"""

import base64
import ctypes
import datetime
import json
import math
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402
import cairo  # noqa: E402

SOCK = os.path.join(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir()), 'magic-cursor.sock')
CONFIG_PATH = os.path.expanduser('~/.config/magic-cursor/config.json')
WIGGLE = os.environ.get('MAGIC_CURSOR_WIGGLE', '1') != '0'
IDLE_TIMEOUT = 30.0
PALETTE = [(0.259, 0.522, 0.957), (0.608, 0.447, 0.796), (0.851, 0.396, 0.439), (0.976, 0.671, 0.0)]


def log(*a):
    print('[magic-cursor]', *a, file=sys.stderr, flush=True)


def load_config():
    cfg = {}
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        pass
    except Exception as e:
        log('config okunamadı:', e)
    if not cfg.get('groq_api_key'):
        cfg['groq_api_key'] = os.environ.get('GROQ_API_KEY', '')
    cfg.setdefault('groq_model', os.environ.get('MAGIC_CURSOR_MODEL', 'qwen/qwen3.8-27b'))
    return cfg


# ════════════════════════════ Varlık tanıma ════════════════════════════
L = r"[^\W\d_]"
LU = r"[A-ZÇĞİÖŞÜ]"
MONTHS = {
    'ocak': 0, 'şubat': 1, 'subat': 1, 'mart': 2, 'nisan': 3, 'mayıs': 4, 'mayis': 4, 'haziran': 5,
    'temmuz': 6, 'ağustos': 7, 'agustos': 7, 'eylül': 8, 'eylul': 8, 'ekim': 9, 'kasım': 10, 'kasim': 10,
    'aralık': 11, 'aralik': 11,
    'january': 0, 'february': 1, 'march': 2, 'april': 3, 'may': 4, 'june': 5, 'july': 6,
    'august': 7, 'september': 8, 'october': 9, 'november': 10, 'december': 11,
}
MONTH_RE = '|'.join(sorted(MONTHS, key=len, reverse=True))
TIME = r"(?:(?:,|\s)+(?:saat\s*|at\s*)?(\d{1,2})[:.](\d{2})(?!\d))?"
CURRENCY = {'$': 'USD', '€': 'EUR', '£': 'GBP', '₺': 'TL', 'TL': 'TL', 'USD': 'USD', 'EUR': 'EUR', 'GBP': 'GBP'}
TR_MONTH_NAMES = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
TR_DAYS = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']


def tr_lower(s):
    return s.replace('İ', 'i').replace('I', 'ı').lower()


def month_index(s):
    return MONTHS.get(tr_lower(s), MONTHS.get(s.lower()))


def make_date(d, m, y, hh, mm):
    if m is None or not (0 <= m <= 11) or not (1 <= d <= 31):
        return None
    now = datetime.datetime.now()
    year = int(y) if y else now.year
    has_time = hh is not None and int(hh) < 24 and int(mm) < 60
    try:
        dt = datetime.datetime(year, m + 1, d, int(hh) if has_time else 0, int(mm) if has_time else 0)
        if not y and dt.date() < now.date():
            dt = dt.replace(year=year + 1)
    except ValueError:
        return None
    return {'date': dt, 'has_time': has_time}


def _url(m):
    v = re.sub(r"[.,;:!?]+$", '', m.group(0))
    return {'text': v, 'url': v if v.lower().startswith('http') else 'https://' + v}


def _price(m):
    cur = re.search(r"TL|USD|EUR|GBP|[$€£₺]", m.group(0)).group(0)
    return {'amount': re.sub(r"[^\d.,]", '', m.group(0)), 'currency': CURRENCY[cur]}


ADDRESS = (
    rf"(?:{LU}[\w]*\.?\s){{1,4}}"
    r"(?:Mahallesi|Mah\.|Caddesi|Cad\.|Sokak|Soka[gğ][ıi]|Sok\.|Sk\.|Bulvar[ıi]|Blv\.|Street|St\.|Avenue|Ave\.|Road|Rd\.)"
    rf"(?:,?\s*(?:No|Kat|Daire)\s*:?\s*\d+{L}?(?:/\d+)?)*"
    rf"(?:,\s*{L}+(?:\s{LU}{L}*)?(?:\s*/\s*{L}+)?){{0,3}}"
)

DETECTORS = [
    ('url', re.compile(r"\bhttps?://[^\s<>\"')]+|\bwww\.[^\s<>\"')]+", re.I), _url),
    ('email', re.compile(rf"[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.{L}{{2,}}"), None),
    ('address', re.compile(ADDRESS), None),
    ('date', re.compile(rf"\b(\d{{1,2}})\s+({MONTH_RE})(?!{L})(?:\s+(\d{{4}}))?{TIME}", re.I),
     lambda m: make_date(int(m[1]), month_index(m[2]), m[3], m[4], m[5])),
    ('date', re.compile(rf"\b(\d{{1,2}})[./](\d{{1,2}})[./](\d{{4}}){TIME}"),
     lambda m: make_date(int(m[1]), int(m[2]) - 1, m[3], m[4], m[5])),
    ('date', re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?"),
     lambda m: make_date(int(m[3]), int(m[2]) - 1, m[1], m[4], m[5])),
    ('phone', re.compile(r"(?:\+90[\s-]?|\b0)?\(?[2-5]\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"
                         r"|\+\d{1,3}(?:[\s-]?\(?\d{2,4}\)?){2,4}"), None),
    ('price', re.compile(r"(?:[$€£₺]\s?\d[\d.,]*|\d[\d.,]*\s?(?:TL|₺|USD|EUR|GBP|\$|€|£)(?![^\W\d_]))"), _price),
    ('color', re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?!\w)"), None),
]


def find_entities(text):
    found = []
    for prio, (typ, rx, build) in enumerate(DETECTORS):
        for m in rx.finditer(text):
            if not m.group(0).strip():
                continue
            data = build(m) if build else {}
            if data is None:
                continue
            raw = data.get('text', m.group(0).rstrip())
            found.append({'type': typ, 'start': m.start(), 'end': m.start() + len(raw), 'text': raw, 'data': data, 'prio': prio})
    found.sort(key=lambda e: (e['start'], e['prio'], -e['end']))
    out = []
    for e in found:
        if not any(e['start'] < o['end'] and o['start'] < e['end'] for o in out):
            out.append(e)
    return out


def looks_turkish(t):
    return bool(re.search(r"[çğışöüÇĞİŞÖÜ]", t) or re.search(r"\b(ve|bir|bu|için|icin|ile|olarak|çok|daha)\b", t, re.I))


def clip(t, n=60):
    t = ' '.join(t.split())
    return t if len(t) <= n else t[:n - 1].rstrip() + '…'


def fmt_date(info):
    d = info['date']
    s = f"{d.day} {TR_MONTH_NAMES[d.month - 1]} {d.year} {TR_DAYS[d.weekday()]}"
    return s + (f" {d.hour:02d}:{d.minute:02d}" if info['has_time'] else '')


# ════════════════════════════ OCR ════════════════════════════
def ocr_langs():
    try:
        out = subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True, timeout=10).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    langs = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]
    pick = [lang for lang in ('tur', 'eng') if lang in langs]
    return '+'.join(pick) or (langs[0] if langs else None)


class Word:
    __slots__ = ('text', 'x', 'y', 'w', 'h', 'line', 'start', 'end')

    def __init__(self, text, x, y, w, h):
        self.text, self.x, self.y, self.w, self.h = text, x, y, w, h
        self.line = self.start = self.end = 0


class Para:
    def __init__(self, lines):
        self.words, parts, pos = [], [], 0
        for li, line in enumerate(lines):
            for w in line:
                if parts:
                    parts.append(' ')
                    pos += 1
                w.start, w.end, w.line = pos, pos + len(w.text), li
                parts.append(w.text)
                pos += len(w.text)
                self.words.append(w)
        self.text = ''.join(parts)


def run_ocr(pixbuf, langs, scale=1):
    """Pixbuf üzerinde tesseract çalıştırır; düşük öncelikle (sistemi kastırmasın)."""
    if scale != 1:
        pixbuf = pixbuf.scale_simple(pixbuf.get_width() * scale, pixbuf.get_height() * scale, GdkPixbuf.InterpType.BILINEAR)
    fd, path = tempfile.mkstemp(suffix='.png', prefix='magic-cursor-')
    os.close(fd)
    try:
        pixbuf.savev(path, 'png', ['compression'], ['1'])
        env = dict(os.environ, OMP_THREAD_LIMIT='2')
        res = subprocess.run(['nice', '-n', '15', 'tesseract', path, 'stdout', '-l', langs, '--psm', '3', 'tsv'],
                             capture_output=True, text=True, timeout=60, env=env)
    finally:
        os.unlink(path)
    words = []
    for row in res.stdout.splitlines()[1:]:
        c = row.split('\t')
        if len(c) < 12 or c[0] != '5':
            continue
        t = c[11].strip()
        try:
            conf = float(c[10])
        except ValueError:
            continue
        if not t or conf < 20:
            continue
        x, y, w, h = (int(int(v) / scale) for v in c[6:10])
        if h < 4 or w < 2:
            continue
        words.append(Word(t, x, y, w, h))
    return layout(words)


def _height(words):
    hs = sorted(w.h for w in words)
    return hs[len(hs) // 2]


def layout(words):
    """Tesseract'ın kitap odaklı paragraf gruplaması yerine ekrana uygun bölümlendirme:
    1) aynı hizadaki ve aralarında küçük boşluk olan kelimeler → satır parçası
       (sütun / panel boşlukları satırı böler)
    2) alt alta, yakın, aynı yazı boyutunda ve yatayda hizalı satırlar → blok."""
    if not words:
        return []
    # OCR hayaletlerini ayıkla: çok uzun ama dar kutular (alt çizgili kodda satırları birleştirir)
    med = _height(words)
    words = [w for w in words if not (w.h > 1.8 * med and w.w / max(1, len(w.text)) < 0.4 * w.h)]
    lines = []  # [[words]]
    for w in sorted(words, key=lambda v: v.x):
        best, best_gap = None, None
        for ln in lines:
            last = ln[0][-1]
            ov = min(last.y + last.h, w.y + w.h) - max(last.y, w.y)
            if ov < 0.55 * min(last.h, w.h):
                continue
            hmax = max(last.h, w.h)
            if max(last.h, w.h) > 1.8 * min(last.h, w.h) and min(last.h, w.h) > 8:
                continue  # farklı yazı boyutu
            gap = w.x - (last.x + last.w)
            if gap > 1.15 * hmax and (last.text.isdigit() or w.text.isdigit()):
                continue  # satır numarası sütunu gibi
            # 2.2×: OCR'ın okuyamadığı ok/simgeleri köprüler; sütun boşlukları bundan geniş
            if -0.5 * hmax <= gap <= 2.2 * hmax and (best_gap is None or gap < best_gap):
                best, best_gap = ln, gap
        if best:
            best[0].append(w)
        else:
            lines.append([[w]])
    lines = [(ws, bbox(ws), _height(ws)) for (ws,) in lines]

    blocks = []  # [lines, x0, x1, last_bottom, h]
    for ws, (x0, y0, x1, y1), h in sorted(lines, key=lambda ln: ln[1][1]):
        best, best_gap = None, None
        for b in blocks:
            bx0, by0, bx1, by1 = b[1][-1][1]
            bh = b[2]
            gap = y0 - by1
            if not (-0.3 * bh <= gap <= 0.9 * max(bh, h)):
                continue
            if max(bh, h) > 1.3 * min(bh, h):
                continue
            left_aligned = abs(x0 - bx0) <= 2.5 * h
            overlap = min(x1, bx1) - max(x0, bx0)
            if not (left_aligned or overlap > 0.6 * min(x1 - x0, bx1 - bx0)):
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = b, gap
        if best:
            best[0].append(ws)
            best[1].append((ws, (x0, y0, x1, y1)))
        else:
            blocks.append([[ws], [(ws, (x0, y0, x1, y1))], h])

    # Başka bir bloğun içine düşen küçük blokları (ör. aksanlı harf yüzünden ayrılan kelimeler) birleştir
    def area(r):
        return max(0, r[2] - r[0]) * max(0, r[3] - r[1])
    groups = sorted(([w for ws in b[0] for w in ws] for b in blocks), key=lambda g: -area(bbox(g)))
    merged = []
    for g in groups:
        r = bbox(g)
        for m in merged:
            c = bbox(m)
            inter = (max(r[0], c[0]), max(r[1], c[1]), min(r[2], c[2]), min(r[3], c[3]))
            if area(inter) >= 0.7 * max(1, area(r)):
                m.extend(g)
                break
        else:
            merged.append(list(g))

    out = []
    for g in merged:  # blok içindeki kelimeleri yeniden satırlara diz
        g.sort(key=lambda w: w.y + w.h / 2)
        rows = []
        for w in g:
            cy = w.y + w.h / 2
            if rows and abs(cy - rows[-1][0]) <= 0.45 * max(w.h, rows[-1][1]):
                rows[-1][2].append(w)
            else:
                rows.append([cy, w.h, [w]])
        out.append(Para([sorted(r[2], key=lambda v: v.x) for r in rows]))
    out.sort(key=lambda p: (bbox(p.words)[1], bbox(p.words)[0]))
    return out


def bbox(words):
    return (min(w.x for w in words), min(w.y for w in words),
            max(w.x + w.w for w in words), max(w.y + w.h for w in words))


def in_rect(x, y, r, pad=0):
    return r[0] - pad <= x <= r[2] + pad and r[1] - pad <= y <= r[3] + pad


class Target:
    def __init__(self, typ, rect, text='', entity=None, context='', word='', image=None):
        self.type, self.rect, self.text, self.entity = typ, rect, text, entity
        self.context, self.word, self.image = context, word, image

    def key(self):
        return (self.type, self.rect)


# ════════════════════════════ Eylemler ════════════════════════════
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


# ════════════════════════════ Groq ════════════════════════════
SYSTEM_PROMPT = ('Sen kullanıcının ekranındaki içeriği açıklayan kısa ve net bir asistansın. '
                 'Her zaman Türkçe yanıt ver. Gereksiz giriş cümlesi kurma. '
                 'Devam sorularında önceki konuşmayı ve ilk görüntüyü bağlam olarak kullan.')


def image_part(pb):
    w, h = pb.get_width(), pb.get_height()
    m = max(w, h)
    if m > 1280:
        pb = pb.scale_simple(int(w * 1280 / m), int(h * 1280 / m), GdkPixbuf.InterpType.BILINEAR)
    ok, buf = pb.save_to_bufferv('jpeg', ['quality'], ['85'])
    if not ok:
        return None
    return {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(buf).decode()}}


def md_markup(t):
    """Yanıttaki basit markdown'ı Pango biçimine çevir (**kalın**, `kod`, başlık, madde)."""
    s = GLib.markup_escape_text(t)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'`([^`\n]+)`', r'<tt>\1</tt>', s)
    s = re.sub(r'(?m)^#{1,6}\s*(.+)$', r'<b>\1</b>', s)
    s = re.sub(r'(?m)^\s*[-*]\s+', '• ', s)
    return s


def groq_stream(cfg, messages, on_chunk):
    """Groq chat completions (OpenAI uyumlu) — konuşma geçmişiyle akışlı yanıt."""
    body = {
        'model': cfg['groq_model'],
        'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}] + messages,
        'stream': True,
        'temperature': 0.3,
        'max_completion_tokens': 400,
        'reasoning_effort': 'none',
    }
    req = urllib.request.Request(
        'https://api.groq.com/openai/v1/chat/completions', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cfg['groq_api_key'],
                 'User-Agent': 'magic-cursor/2.0'})
    in_think = False
    with urllib.request.urlopen(req, timeout=60) as r:
        for raw in r:
            line = raw.decode('utf-8', 'replace').strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            j = json.loads(data)
            if not j.get('choices'):
                continue
            chunk = j['choices'][0].get('delta', {}).get('content') or ''
            # olası <think> bloklarını ayıkla
            if '<think>' in chunk:
                in_think = True
                chunk = chunk.split('<think>')[0]
            if in_think:
                if '</think>' in chunk:
                    in_think = False
                    chunk = chunk.split('</think>', 1)[1]
                else:
                    continue
            if chunk:
                on_chunk(chunk)


# ════════════════════════════ Arayüz parçaları ════════════════════════════
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


def _clear(_w, cr):
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
    w.connect('draw', _clear)
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
    w.connect('draw', _clear)
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
        _clear(w, cr)
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
        self.win.show()
        if swing and self.app.xcursor.dpy:
            self.swinging = True
            self.app.xcursor.hide()
        self.win.queue_draw()

    def stop(self):
        if self.swinging:
            self.swinging = False
            self.app.xcursor.show()
        self.win.hide()

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
        _clear(w, cr)
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
        _clear(w, cr)
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


# ════════════════════════════ Uygulama ════════════════════════════
class MagicCursor:
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
        self.wig = {'last': None, 'dir': 0, 'acc': 0.0, 'flips': []}

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
            self.detect_wiggle(x, time.monotonic())
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

    def detect_wiggle(self, x, t):
        w = self.wig
        if w['last'] is None:
            w['last'] = x
            return
        dx = x - w['last']
        w['last'] = x
        d = (dx > 0) - (dx < 0)
        if not d:
            return
        if d == w['dir']:
            w['acc'] += abs(dx)
        else:
            if w['acc'] > 40:
                w['flips'].append(t)
            w['dir'], w['acc'] = d, abs(dx)
        w['flips'] = [f for f in w['flips'] if t - f < 0.7]
        if len(w['flips']) >= 4:
            w['flips'].clear()
            self.deactivate() if self.active else self.activate()

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
        self.wig['flips'].clear()

    # ─────────────── Durum çubuğu ───────────────
    def show_pill(self):
        self.pill = popup(prefers_dark())
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.get_style_context().add_class('mc-pill')
        star = Gtk.Label(label='✦')
        star.get_style_context().add_class('mc-star')
        self.pill_label = Gtk.Label(label='Magic Pointer')
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
            self.pill_label.set_text(f'Magic Pointer · {status}')
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

    # ─────────────── Panel ───────────────
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
            chips.append(Chip('✨', 'Yapay zekâya sor', lambda: self.ask_ai(t), primary=True, stay=True))
            if t.text:
                chips += self.text_chips(t.text)
            if t.image:
                chips.append(Chip('🖼️', 'Görüntüyü kopyala', lambda: self.copy_image(t.image), stay=True))
                chips.append(Chip('💾', 'Kaydet', lambda: self.save_image(t.image), stay=True))
            chips.append(Chip('✕', 'Seçimi kapat', self.release_region, stay=True))
            return chips
        if t.type == 'text':
            chips = self.text_chips(t.text)
            chips.insert(1, Chip('✨', 'Açıkla', lambda: self.ask_ai(t), primary=True, stay=True))
            w = re.sub(r"^\W+|\W+$", '', t.word)
            if len(w) > 2:
                q = f'{w} ne demek' if looks_turkish(t.text) else f'{w} meaning'
                chips.insert(3, Chip('📖', f'“{clip(w, 16)}” ne demek?', lambda: google(q)))
            return chips
        chips = self.entity_chips(t.entity, t.context)
        if chips:
            chips[0].primary = True
        return chips

    def text_chips(self, text):
        return [
            Chip('📋', 'Kopyala', lambda: self.copy(text), stay=True),
            Chip('🔍', 'Ara', lambda: google(text)),
            Chip('🌐', 'İngilizceye çevir' if looks_turkish(text) else 'Türkçeye çevir', lambda: translate(text)),
            Chip('🔊', 'Sesli oku', lambda: speak(text), stay=True),
        ]

    def entity_chips(self, e, context):
        t, typ = e['text'], e['type']
        if typ == 'date':
            title = clip(context.replace(t, ' '), 70) or 'Etkinlik'
            info = e['data']
            return [Chip('📅', 'Google Takvim’e ekle', lambda: xdg_open(calendar_url(info, title, context))),
                    Chip('⬇️', '.ics kaydet ve aç', lambda: xdg_open(save_ics(info, title, context))),
                    Chip('📋', 'Kopyala', lambda: self.copy(fmt_date(info)), stay=True)]
        if typ == 'email':
            return [Chip('✉️', 'E-posta yaz', lambda: xdg_open('mailto:' + t)),
                    Chip('📋', 'Adresi kopyala', lambda: self.copy(t), stay=True)]
        if typ == 'phone':
            digits = re.sub(r'\D', '', t)
            wa = '90' + digits[1:] if digits.startswith('0') else digits
            return [Chip('💬', 'WhatsApp', lambda: xdg_open('https://wa.me/' + wa)),
                    Chip('📞', 'Ara', lambda: xdg_open('tel:' + re.sub(r'[^\d+]', '', t))),
                    Chip('📋', 'Kopyala', lambda: self.copy(t), stay=True)]
        if typ == 'address':
            q = urllib.parse.quote(t)
            return [Chip('🗺️', 'Haritada göster', lambda: xdg_open('https://www.google.com/maps/search/?api=1&query=' + q)),
                    Chip('🧭', 'Yol tarifi', lambda: xdg_open('https://www.google.com/maps/dir/?api=1&destination=' + q)),
                    Chip('📋', 'Kopyala', lambda: self.copy(t), stay=True)]
        if typ == 'url':
            u = e['data']['url']
            return [Chip('↗️', 'Aç', lambda: xdg_open(u)), Chip('📋', 'Bağlantıyı kopyala', lambda: self.copy(u), stay=True)]
        if typ == 'price':
            a, c = e['data']['amount'], e['data']['currency']
            to = 'USD' if c == 'TL' else 'TL'
            return [Chip('💱', f'{to}’ye çevir', lambda: google(f'{a} {c} kaç {to}')),
                    Chip('📋', 'Kopyala', lambda: self.copy(t), stay=True)]
        if typ == 'color':
            return [Chip('📋', 'HEX kopyala', lambda: self.copy(t), stay=True),
                    Chip('🎨', 'RGB kopyala', lambda: self.copy(hex_to_rgb(t)), stay=True)]
        return []

    def open_panel(self, t):
        self.close_panel()
        chips = self.chips_for(t)
        if not chips:
            return
        icon, label = TYPE_META.get(t.type, TYPE_META['text'])
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
        hl = Gtk.Label(label=f'{icon}  {label}  ·  {clip(preview, 60)}', xalign=0)
        hl.set_ellipsize(3)
        hl.set_max_width_chars(60)
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
            b = Gtk.Button(label=f'{c.icon} {c.label}')
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
        self.selector.update_holes()

    def close_panel(self):
        if self.panel_win:
            self.panel_win.destroy()
            self.panel_geom = None
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

    # ─────────────── Yapay zekâ (Groq) ───────────────
    def ask_ai(self, t):
        if not self.chat_box or self.chat_busy or self.chat_msgs:
            if self.entry and self.entry.get_visible():
                self.focus_panel()
            return
        self.panel_pinned = True
        if not self.cfg['groq_api_key']:
            self.add_bubble('a', f'Groq API anahtarı yok.\n{CONFIG_PATH} dosyasına\n{{"groq_api_key": "gsk_..."}}\n'
                                 'yazıp Magic Cursor\'ı yeniden başlatın.')
            return
        image = t.image
        if image is None and self.snapshot:
            x0, y0, x1, y1 = t.rect
            x0, y0 = max(0, int(x0) - 60), max(0, int(y0) - 60)
            x1, y1 = min(self.W, int(x1) + 60), min(self.H, int(y1) + 60)
            image = self.snapshot.new_subpixbuf(x0, y0, x1 - x0, y1 - y0).copy()
        if t.type == 'region':
            prompt = ('Görüntü, kullanıcının ekranından seçtiği bir alan. '
                      + (f'OCR metni (hatalı olabilir): """{t.text[:1500]}"""\n' if t.text else '')
                      + 'Burada ne olduğunu en fazla 4 kısa cümleyle açıkla. Faydalıysa bir sonraki adımı öner.')
        else:
            prompt = (f'Kullanıcı ekranda şu metnin üzerinde (OCR, hatalı olabilir): """{t.text[:1500]}"""\n'
                      'Görüntü metnin çevresini gösteriyor. En fazla 3 kısa cümleyle açıkla veya özetle; '
                      'yabancı dildeyse Türkçe anlamını ver.')
        content = [{'type': 'text', 'text': prompt}]
        part = image_part(image) if image is not None else None
        if part:
            content.append(part)
        self.chat_msgs = [{'role': 'user', 'content': content}]
        self.stream_reply()

    def on_followup(self, entry):
        q = entry.get_text().strip()
        if not q or self.chat_busy or not self.chat_msgs:
            return
        entry.set_text('')
        self.add_bubble('q', q)
        self.chat_msgs.append({'role': 'user', 'content': q})
        self.stream_reply()

    def on_panel_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.release_region() if (self.target and self.target.type == 'region') else self.clear_target()
            return True
        return False

    def focus_panel(self):
        """Yazı kutusu için paneli odakla (yalnızca kullanıcı etkileşiminde)."""
        w = self.panel_win
        if w:
            w.set_accept_focus(True)
            w.present_with_time(Gtk.get_current_event_time() or Gdk.CURRENT_TIME)
            if self.entry and self.entry.get_visible():
                self.entry.grab_focus()

    def add_bubble(self, role, text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.set_line_wrap(True)
        lbl.set_line_wrap_mode(2)
        lbl.set_max_width_chars(58)
        lbl.get_style_context().add_class('mc-q' if role == 'q' else 'mc-a')
        self.chat_box.pack_start(lbl, False, False, 0)
        lbl.show()
        self.chat_box.show()
        self.chat_scroll.show()
        self.place_panel()
        self.scroll_chat()
        return lbl

    def scroll_chat(self):
        def go():
            if self.chat_scroll:
                adj = self.chat_scroll.get_vadjustment()
                adj.set_value(adj.get_upper() - adj.get_page_size())
            return False
        GLib.idle_add(go)

    def stream_reply(self):
        lbl = self.add_bubble('a', '✨ düşünüyor…')
        self.chat_busy = True
        self.entry.set_sensitive(False)
        panel = self.panel_win
        msgs = list(self.chat_msgs)
        state = {'text': '', 'error': False}
        t0 = time.time()

        def update(final=False):
            if self.panel_win is not panel:
                return False
            lbl.set_markup(md_markup(state['text'].strip()) or '✨ düşünüyor…')
            self.last_activity = time.time()
            if final:
                self.chat_busy = False
                if state['text'].strip() and not state['error']:
                    self.chat_msgs.append({'role': 'assistant', 'content': state['text'].strip()})
                elif self.chat_msgs and self.chat_msgs[-1]['role'] == 'user' and len(self.chat_msgs) > 1:
                    self.chat_msgs.pop()  # başarısız soruyu geçmişten çıkar
                self.entry.set_sensitive(True)
                self.entry.show()
                self.focus_panel()
            self.place_panel()
            self.scroll_chat()
            return False

        def on_chunk(chunk):
            state['text'] += chunk
            GLib.idle_add(update)

        def work():
            try:
                groq_stream(self.cfg, msgs, on_chunk)
                log(f'Groq yanıtı {time.time() - t0:.2f}s')
            except urllib.error.HTTPError as e:
                detail = e.read().decode('utf-8', 'replace')[:300]
                state['text'], state['error'] = f'⚠️ Groq hatası {e.code}: {detail}', True
                log(state['text'])
            except Exception as e:
                state['text'], state['error'] = f'⚠️ Groq\'a ulaşılamadı: {e}', True
                log(state['text'])
            GLib.idle_add(update, True)
        threading.Thread(target=work, daemon=True).start()


# ════════════════════════════ IPC / giriş ════════════════════════════
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


def main():
    cmd = ' '.join(sys.argv[1:]) or 'run'
    if cmd in ('-h', '--help', 'help'):
        print(__doc__)
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


if __name__ == '__main__':
    main()
