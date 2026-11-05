"""Tesseract ile ekran okuma ve ekrana uygun bölümlendirme (satır → blok)."""
import os
import subprocess
import tempfile

from gi.repository import GdkPixbuf

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
