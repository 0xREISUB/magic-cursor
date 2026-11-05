"""Yapay zekâ yanıtındaki markdown'ı Gtk.Label için Pango biçimine çevirir.

Desteklenenler: kod blokları (```), `satır içi kod`, **kalın**, *italik*, ~~üstü çizili~~,
başlıklar, madde ve numaralı listeler (iç içe), > alıntı, [bağlantı](url), --- çizgi,
tablolar ve basit LaTeX ($x^2$, \\(\\frac{a}{b}\\)). Akış sırasında henüz kapanmamış
işaretler (ör. yarım kalmış **) görünmez.
"""
import re

from gi.repository import GLib

MONO = 'font_family="monospace"'
MUTED = 'alpha="70%"'

LATEX = {
    r'\times': '×', r'\cdot': '·', r'\pm': '±', r'\leq': '≤', r'\geq': '≥', r'\neq': '≠', r'\approx': '≈',
    r'\infty': '∞', r'\to': '→', r'\rightarrow': '→', r'\Rightarrow': '⇒', r'\sum': 'Σ', r'\prod': 'Π',
    r'\int': '∫', r'\partial': '∂', r'\nabla': '∇', r'\in': '∈', r'\sqrt': '√', r'\lambda': 'λ',
    r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ', r'\Delta': 'Δ', r'\epsilon': 'ε',
    r'\theta': 'θ', r'\mu': 'μ', r'\pi': 'π', r'\sigma': 'σ', r'\Sigma': 'Σ', r'\phi': 'φ', r'\omega': 'ω',
    r'\Omega': 'Ω', r'\ldots': '…', r'\dots': '…', r'\quad': '  ', r'\,': ' ', r'\;': ' ', r'\!': '',
}


def esc(s):
    return GLib.markup_escape_text(s)


def _math(src):
    """Basit LaTeX → okunur metin (Pango işaretli)."""
    s = src.strip()
    s = re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}',
               lambda m: '/'.join(g if re.fullmatch(r'[\w.]+', g) else f'({g})' for g in m.groups()), s)
    s = re.sub(r'\\sqrt\{([^{}]*)\}', r'√(\1)', s)
    s = re.sub(r'\\(?:text|mathrm|mathbf|operatorname)\{([^{}]*)\}', r'\1', s)
    s = re.sub(r'\\(?:left|right|displaystyle)', '', s)
    for k in sorted(LATEX, key=len, reverse=True):
        s = s.replace(k, LATEX[k])
    s = esc(s)
    s = re.sub(r'\^\{([^{}]*)\}', r'<sup>\1</sup>', s)
    s = re.sub(r'\^(\w)', r'<sup>\1</sup>', s)
    s = re.sub(r'_\{([^{}]*)\}', r'<sub>\1</sub>', s)
    s = re.sub(r'_(\w)', r'<sub>\1</sub>', s)
    return f'<i>{s.replace("{", "").replace("}", "")}</i>'


def _inline(text):
    """Satır içi biçimler; kod ve formül parçalarına dokunmadan."""
    out = []
    # kod ve formül parçalarını ayır: `kod`, $$..$$, $..$, \(..\), \[..\]
    pattern = re.compile(r'(`[^`\n]+`|\$\$.+?\$\$|\$[^$\n]+?\$|\\\(.+?\\\)|\\\[.+?\\\])')
    for i, part in enumerate(pattern.split(text)):
        if i % 2 == 1:
            if part.startswith('`'):
                out.append(f'<span {MONO}>{esc(part[1:-1])}</span>')
            else:
                inner = part.strip('$') if part.startswith('$') else part[2:-2]
                out.append(_math(inner))
            continue
        s = esc(part)
        s = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', s)
        s = re.sub(r'\*\*(?=\S)(.+?)(?<=\S)\*\*', r'<b>\1</b>', s)
        s = re.sub(r'__(?=\S)(.+?)(?<=\S)__', r'<b>\1</b>', s)
        s = re.sub(r'(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])', r'<i>\1</i>', s)
        s = re.sub(r'(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])', r'<i>\1</i>', s)
        s = re.sub(r'~~(?=\S)(.+?)(?<=\S)~~', r'<s>\1</s>', s)
        s = s.replace('**', '').replace('~~', '')  # kapanmamış işaretler (akış sırasında)
        out.append(s)
    return ''.join(out)


def _table(rows):
    """Markdown tablosu → hizalı, eş aralıklı metin."""
    cells = [[c.strip() for c in r.strip().strip('|').split('|')] for r in rows
             if not re.fullmatch(r'\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*', r)]
    if not cells:
        return ''
    n = max(len(r) for r in cells)
    cells = [r + [''] * (n - len(r)) for r in cells]
    plain = [[re.sub(r'\*\*|`', '', c) for c in r] for r in cells]
    widths = [max(len(r[i]) for r in plain) for i in range(n)]
    lines = []
    for ri, r in enumerate(plain):
        line = '  '.join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip()
        lines.append(f'<b>{esc(line)}</b>' if ri == 0 else esc(line))
    return f'<span {MONO}>' + '\n'.join(lines) + '</span>'


def to_pango(md):
    lines = md.replace('\r', '').split('\n')
    out, code, table = [], None, []

    def flush_table():
        if table:
            out.append(_table(table))
            table.clear()

    for line in lines:
        fence = re.match(r'^\s*```', line)
        if code is not None:
            if fence:
                out.append(f'<span {MONO}>' + esc('\n'.join(code)) + '</span>')
                code = None
            else:
                code.append(line)
            continue
        if fence:
            flush_table()
            code = []
            continue
        if re.match(r'^\s*\|.*\|\s*$', line):
            table.append(line)
            continue
        flush_table()

        if re.fullmatch(r'\s*([-*_])(\s*\1){2,}\s*', line):
            out.append(f'<span {MUTED}>────────────</span>')
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            out.append(f'<b>{_inline(m.group(2))}</b>')
            continue
        m = re.match(r'^\s*\$\$(.+)\$\$\s*$', line)
        if m:
            out.append('   ' + _math(m.group(1)))
            continue
        m = re.match(r'^(\s*)[-*+]\s+(.*)$', line)
        if m:
            depth = len(m.group(1).replace('\t', '    ')) // 2
            bullet = '•' if depth == 0 else '◦'
            out.append('   ' * depth + f'{bullet} ' + _inline(m.group(2)))
            continue
        m = re.match(r'^(\s*)(\d+)[.)]\s+(.*)$', line)
        if m:
            depth = len(m.group(1).replace('\t', '    ')) // 2
            out.append('   ' * depth + f'{m.group(2)}. ' + _inline(m.group(3)))
            continue
        m = re.match(r'^\s*>\s?(.*)$', line)
        if m:
            out.append(f'<span {MUTED}><i>│ {_inline(m.group(1))}</i></span>')
            continue
        out.append(_inline(line))

    flush_table()
    if code is not None:  # akış sırasında henüz kapanmamış kod bloğu
        out.append(f'<span {MONO}>' + esc('\n'.join(code)) + '</span>')
    text = '\n'.join(out)
    return re.sub(r'\n{3,}', '\n\n', text).strip()
