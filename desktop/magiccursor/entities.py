"""Metindeki tarih, adres, e-posta, telefon, link, fiyat ve renkleri bulur."""
import datetime
import re

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
