/*!
 * Magic Cursor — Googlebook "Magic Pointer" tarzı bağlamsal imleç.
 * Tek dosya, bağımlılık yok. Sayfaya <script src="magic-cursor.js"></script> ile ekleyin.
 *
 *  - Fareyi hızlıca sağa-sola sallayın (veya Alt+G) → Magic mod açılır
 *  - Bir şeyin üzerine gelin → tarih, adres, e-posta, telefon, fiyat, renk, link,
 *    görsel ve metinler tanınır, ilgili eylemler gösterilir
 *  - Basılı tutup bir alanın etrafına daire çizin → o alandaki her şey seçilir
 *  - Esc / Alt+G / sağ alttaki düğme → kapatır
 */
(() => {
  'use strict';
  if (window.MagicCursor) return;

  const PALETTE = ['#4285f4', '#9b72cb', '#d96570', '#f9ab00'];
  const Z = 2147483000;

  // ───────────────────────── Varlık (entity) tanıma ─────────────────────────
  const MONTHS = {
    ocak: 0, şubat: 1, subat: 1, mart: 2, nisan: 3, mayıs: 4, mayis: 4, haziran: 5,
    temmuz: 6, ağustos: 7, agustos: 7, eylül: 8, eylul: 8, ekim: 9, kasım: 10, kasim: 10,
    aralık: 11, aralik: 11,
    january: 0, february: 1, march: 2, april: 3, may: 4, june: 5, july: 6,
    august: 7, september: 8, october: 9, november: 10, december: 11,
  };
  const MONTH_RE = Object.keys(MONTHS).sort((a, b) => b.length - a.length).join('|');
  const TIME = String.raw`(?:(?:,|\s)+(?:saat\s*|at\s*)?(\d{1,2})[:.](\d{2})(?!\d))?`;

  const monthIndex = (s) => {
    const k1 = s.toLocaleLowerCase('tr');
    const k2 = s.toLowerCase();
    return MONTHS[k1] ?? MONTHS[k2];
  };

  function makeDate(d, m, y, hh, mm) {
    if (m == null || m < 0 || m > 11 || d < 1 || d > 31) return null;
    const now = new Date();
    let year = y ? +y : now.getFullYear();
    const hasTime = hh != null && +hh < 24 && +mm < 60;
    const date = new Date(year, m, d, hasTime ? +hh : 0, hasTime ? +mm : 0);
    if (!y && date < new Date(now.getFullYear(), now.getMonth(), now.getDate())) {
      date.setFullYear(year + 1);
    }
    return { date, hasTime };
  }

  const CURRENCY = { '$': 'USD', '€': 'EUR', '£': 'GBP', '₺': 'TL', TL: 'TL', USD: 'USD', EUR: 'EUR', GBP: 'GBP' };

  const DETECTORS = [
    {
      type: 'url',
      re: /\bhttps?:\/\/[^\s<>"')]+|\bwww\.[^\s<>"')]+/giu,
      build: (m) => {
        const v = m[0].replace(/[.,;:!?]+$/, '');
        return { text: v, url: v.startsWith('http') ? v : 'https://' + v };
      },
    },
    { type: 'email', re: /[\p{L}\d._%+-]+@[\p{L}\d.-]+\.\p{L}{2,}/gu },
    {
      type: 'address',
      re: /(?:\p{Lu}[\p{L}\d]*\.?\s){1,4}(?:Mahallesi|Mah\.|Caddesi|Cad\.|Sokak|Sokağı|Sok\.|Sk\.|Bulvarı|Blv\.|Street|St\.|Avenue|Ave\.|Road|Rd\.)(?:,?\s*(?:No|Kat|Daire)\s*:?\s*\d+\p{L}?(?:\/\d+)?)*(?:,\s*\p{Lu}\p{L}*(?:\s\p{Lu}\p{L}*)?(?:\s*\/\s*\p{Lu}\p{L}*)?){0,3}/gu,
    },
    {
      type: 'date',
      re: new RegExp(String.raw`\b(\d{1,2})\s+(${MONTH_RE})(?!\p{L})(?:\s+(\d{4}))?` + TIME, 'giu'),
      build: (m) => makeDate(+m[1], monthIndex(m[2]), m[3], m[4], m[5]),
    },
    {
      type: 'date',
      re: new RegExp(String.raw`\b(\d{1,2})[./](\d{1,2})[./](\d{4})` + TIME, 'gu'),
      build: (m) => makeDate(+m[1], +m[2] - 1, m[3], m[4], m[5]),
    },
    {
      type: 'date',
      re: /\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/gu,
      build: (m) => makeDate(+m[3], +m[2] - 1, m[1], m[4], m[5]),
    },
    {
      type: 'phone',
      re: /(?:\+90[\s-]?|\b0)?\(?[2-5]\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b|\+\d{1,3}(?:[\s-]?\(?\d{2,4}\)?){2,4}/g,
    },
    {
      type: 'price',
      re: /(?:[$€£₺]\s?\d[\d.,]*|\d[\d.,]*\s?(?:TL|₺|USD|EUR|GBP|\$|€|£)(?!\p{L}))/gu,
      build: (m) => {
        const cur = m[0].match(/TL|USD|EUR|GBP|[$€£₺]/)[0];
        const amount = m[0].replace(/[^\d.,]/g, '');
        return { amount, currency: CURRENCY[cur] };
      },
    },
    { type: 'color', re: /#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F\w])/g },
  ];

  function findEntities(text) {
    const found = [];
    DETECTORS.forEach((d, prio) => {
      d.re.lastIndex = 0;
      let m;
      while ((m = d.re.exec(text))) {
        if (!m[0]) { d.re.lastIndex++; continue; }
        const data = d.build ? d.build(m) : {};
        if (!data) continue;
        const raw = data.text ?? m[0].trimEnd();
        found.push({ type: d.type, start: m.index, end: m.index + raw.length, text: raw, data, prio });
      }
    });
    found.sort((a, b) => a.start - b.start || a.prio - b.prio || b.end - a.end);
    const out = [];
    for (const e of found) {
      if (out.some((o) => e.start < o.end && o.start < e.end)) continue;
      out.push(e);
    }
    return out;
  }

  const isWordChar = (c) => /[\p{L}\p{N}'’-]/u.test(c);
  function sentenceBounds(text, i) {
    let s = i;
    while (s > 0 && !(/[.!?…]/.test(text[s - 2] || '') && /\s/.test(text[s - 1]))) s--;
    let e = i;
    while (e < text.length && !(/[.!?…]/.test(text[e]) && (e + 1 >= text.length || /\s/.test(text[e + 1])))) e++;
    e = Math.min(text.length, e + 1);
    while (s < e && /\s/.test(text[s])) s++;
    while (e > s && /\s/.test(text[e - 1])) e--;
    return [s, e];
  }

  const looksTurkish = (t) => /[çğışöüÇĞİŞÖÜ]/.test(t) || /\b(ve|bir|bu|için|ile|olarak|çok|daha)\b/i.test(t);
  const clip = (t, n = 60) => (t.length > n ? t.slice(0, n - 1).trimEnd() + '…' : t);
  const enc = encodeURIComponent;

  // ───────────────────────── Eylemler ─────────────────────────
  function toast(msg) {
    const el = document.createElement('div');
    el.className = 'mc-toast mc-ui';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add('mc-out'), 1600);
    setTimeout(() => el.remove(), 2000);
  }

  async function copy(text, label = 'Kopyalandı') {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    toast('✓ ' + label);
  }

  const open = (url) => window.open(url, '_blank', 'noopener');
  const search = (q) => open('https://www.google.com/search?q=' + enc(q));
  const translate = (t) =>
    open(`https://translate.google.com/?sl=auto&tl=${looksTurkish(t) ? 'en' : 'tr'}&text=${enc(t)}&op=translate`);

  function speak(text) {
    if (!('speechSynthesis' in window)) return toast('Tarayıcı sesli okumayı desteklemiyor');
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = looksTurkish(text) ? 'tr-TR' : 'en-US';
    speechSynthesis.speak(u);
    toast('🔊 Okunuyor…');
  }

  const pad = (n) => String(n).padStart(2, '0');
  const fmtDate = (d, time) =>
    `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
    (time ? `T${pad(d.getHours())}${pad(d.getMinutes())}00` : '');

  function eventRange({ date, hasTime }) {
    const end = new Date(date);
    if (hasTime) end.setHours(end.getHours() + 1);
    else end.setDate(end.getDate() + 1);
    return [fmtDate(date, hasTime), fmtDate(end, hasTime)];
  }

  function calendarUrl(info, title, details) {
    const [s, e] = eventRange(info);
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${enc(title)}&dates=${s}/${e}&ctz=${enc(tz)}&details=${enc(details)}`;
  }

  function downloadIcs(info, title, details) {
    const [s, e] = eventRange(info);
    const dt = (v) => (info.hasTime ? `:${v}` : `;VALUE=DATE:${v}`);
    const ics = [
      'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//MagicCursor//TR', 'BEGIN:VEVENT',
      `UID:${Date.now()}@magic-cursor`, `DTSTAMP:${fmtDate(new Date(), true)}`,
      `DTSTART${dt(s)}`, `DTEND${dt(e)}`,
      `SUMMARY:${title.replace(/[,;]/g, '\\$&')}`, `DESCRIPTION:${details.replace(/[,;]/g, '\\$&').replace(/\n/g, '\\n')}`,
      'END:VEVENT', 'END:VCALENDAR',
    ].join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([ics], { type: 'text/calendar' }));
    a.download = 'etkinlik.ics';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast('✓ etkinlik.ics indirildi');
  }

  const TYPE_META = {
    date: ['📅', 'Tarih'], email: ['✉️', 'E-posta'], phone: ['📞', 'Telefon'],
    address: ['📍', 'Adres'], url: ['🔗', 'Bağlantı'], price: ['💱', 'Fiyat'],
    color: ['🎨', 'Renk'], image: ['🖼️', 'Görsel'], text: ['✦', 'Metin'],
    word: ['✦', 'Kelime'], region: ['◎', 'Seçili alan'],
  };

  function entityActions(e, context) {
    const t = e.text;
    switch (e.type) {
      case 'date': {
        const title = clip(context.replace(e.text, '').replace(/\s+/g, ' ').trim(), 70) || 'Etkinlik';
        const when = e.data.date.toLocaleString('tr-TR', {
          day: 'numeric', month: 'long', year: 'numeric',
          ...(e.data.hasTime ? { hour: '2-digit', minute: '2-digit' } : {}),
        });
        return [
          { icon: '📅', label: 'Google Takvim’e ekle', run: () => open(calendarUrl(e.data, title, context)) },
          { icon: '⬇️', label: '.ics indir', run: () => downloadIcs(e.data, title, context) },
          { icon: '📋', label: 'Kopyala', run: () => copy(when) },
        ];
      }
      case 'email':
        return [
          { icon: '✉️', label: 'E-posta yaz', run: () => open('mailto:' + t) },
          { icon: '📋', label: 'Adresi kopyala', run: () => copy(t) },
        ];
      case 'phone':
        return [
          { icon: '📞', label: 'Ara', run: () => (location.href = 'tel:' + t.replace(/[^\d+]/g, '')) },
          { icon: '💬', label: 'WhatsApp', run: () => open('https://wa.me/' + t.replace(/\D/g, '').replace(/^0/, '90')) },
          { icon: '📋', label: 'Kopyala', run: () => copy(t) },
        ];
      case 'address':
        return [
          { icon: '🗺️', label: 'Haritada göster', run: () => open('https://www.google.com/maps/search/?api=1&query=' + enc(t)) },
          { icon: '🧭', label: 'Yol tarifi', run: () => open('https://www.google.com/maps/dir/?api=1&destination=' + enc(t)) },
          { icon: '📋', label: 'Kopyala', run: () => copy(t) },
        ];
      case 'url':
        return [
          { icon: '↗️', label: 'Aç', run: () => open(e.data.url) },
          { icon: '📋', label: 'Bağlantıyı kopyala', run: () => copy(e.data.url) },
        ];
      case 'price': {
        const { amount, currency } = e.data;
        const target = currency === 'TL' ? 'USD' : 'TL';
        return [
          { icon: '💱', label: `${target}’ye çevir`, run: () => search(`${amount} ${currency} kaç ${target}`) },
          { icon: '📋', label: 'Kopyala', run: () => copy(t) },
        ];
      }
      case 'color':
        return [
          { icon: '📋', label: 'HEX kopyala', run: () => copy(t) },
          { icon: '🎨', label: 'RGB kopyala', run: () => copy(hexToRgb(t)) },
        ];
      default:
        return [];
    }
  }

  function hexToRgb(h) {
    let s = h.slice(1);
    if (s.length === 3) s = [...s].map((c) => c + c).join('');
    const n = parseInt(s, 16);
    return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
  }

  const textActions = (t) => [
    { icon: '📋', label: 'Kopyala', run: () => copy(t) },
    { icon: '🔍', label: 'Ara', run: () => search(t) },
    { icon: '🌐', label: looksTurkish(t) ? 'İngilizceye çevir' : 'Türkçeye çevir', run: () => translate(t) },
    { icon: '🔊', label: 'Sesli oku', run: () => speak(t) },
  ];

  function imageActions(img) {
    const src = img.currentSrc || img.src;
    const isRemote = /^https?:/.test(src);
    const acts = [
      { icon: '↗️', label: 'Yeni sekmede aç', run: () => open(src) },
      {
        icon: '⬇️', label: 'İndir', run: () => {
          const a = document.createElement('a');
          a.href = src; a.download = (img.alt || 'gorsel').replace(/\s+/g, '-'); a.click();
        },
      },
    ];
    if (isRemote) acts.unshift({ icon: '🔎', label: 'Google Lens ile ara', run: () => open('https://lens.google.com/uploadbyurl?url=' + enc(src)) });
    if (img.alt) acts.push({ icon: '📋', label: 'Açıklamayı kopyala', run: () => copy(img.alt) });
    return acts;
  }

  // ───────────────────────── Stil ─────────────────────────
  const CSS = `
  @property --mc-angle { syntax: '<angle>'; inherits: false; initial-value: 0deg; }
  .mc-ui { --mc-bg: rgba(255,255,255,.86); --mc-fg: #1f1f1f; --mc-muted: #5f6368; --mc-line: rgba(0,0,0,.08);
           --mc-chip: rgba(0,0,0,.04); --mc-chip-hover: rgba(66,133,244,.12);
           font-family: "Google Sans", Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  @media (prefers-color-scheme: dark) {
    .mc-ui { --mc-bg: rgba(32,33,36,.88); --mc-fg: #e8eaed; --mc-muted: #9aa0a6; --mc-line: rgba(255,255,255,.1);
             --mc-chip: rgba(255,255,255,.06); --mc-chip-hover: rgba(138,180,248,.18); }
  }
  html.mc-active, html.mc-active * { cursor: none !important; user-select: none !important; -webkit-user-select: none !important; }
  #mc-canvas { position: fixed; inset: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: ${Z + 10}; }
  .mc-hl { position: fixed; pointer-events: none; z-index: ${Z}; border-radius: 8px;
           background: rgba(66,133,244,.07); transition: all .14s cubic-bezier(.2,.8,.2,1);
           box-shadow: 0 0 18px rgba(155,114,203,.35); animation: mc-pop .18s ease-out; }
  .mc-hl::before { content: ''; position: absolute; inset: -2px; border-radius: inherit; padding: 2px;
           background: conic-gradient(from var(--mc-angle), ${PALETTE.join(',')}, ${PALETTE[0]});
           -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
           -webkit-mask-composite: xor; mask-composite: exclude; animation: mc-spin 2.4s linear infinite; }
  @keyframes mc-spin { to { --mc-angle: 360deg; } }
  @keyframes mc-pop { from { opacity: 0; transform: scale(.96); } }
  .mc-panel { position: fixed; z-index: ${Z + 5}; max-width: min(380px, calc(100vw - 24px)); padding: 10px;
           background: var(--mc-bg); color: var(--mc-fg); border-radius: 16px;
           border: 1px solid var(--mc-line); backdrop-filter: blur(16px) saturate(1.4); -webkit-backdrop-filter: blur(16px) saturate(1.4);
           box-shadow: 0 12px 40px rgba(0,0,0,.18), 0 0 0 1px rgba(155,114,203,.12);
           animation: mc-panel-in .22s cubic-bezier(.2,.9,.3,1.2); transform-origin: top left; }
  .mc-panel.mc-above { transform-origin: bottom left; }
  @keyframes mc-panel-in { from { opacity: 0; transform: translateY(-4px) scale(.94); } }
  .mc-head { display: flex; align-items: center; gap: 8px; padding: 2px 4px 8px; font-size: 12px; color: var(--mc-muted); }
  .mc-head b { color: var(--mc-fg); font-weight: 600; }
  .mc-head .mc-prev { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .mc-swatch { width: 14px; height: 14px; border-radius: 4px; border: 1px solid var(--mc-line); flex: none; }
  .mc-chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .mc-chip { all: unset; display: inline-flex; align-items: center; gap: 6px; padding: 7px 12px; border-radius: 999px;
           font-size: 13px; line-height: 1; color: var(--mc-fg); background: var(--mc-chip); border: 1px solid var(--mc-line);
           transition: background .12s, transform .12s; animation: mc-chip-in .25s backwards; }
  .mc-chip:hover, .mc-chip:focus-visible { background: var(--mc-chip-hover); transform: translateY(-1px); }
  .mc-chip.mc-primary { background: linear-gradient(135deg, rgba(66,133,244,.16), rgba(155,114,203,.16), rgba(217,101,112,.14)); }
  @keyframes mc-chip-in { from { opacity: 0; transform: translateY(4px); } }
  .mc-toast { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: ${Z + 20};
           padding: 10px 16px; border-radius: 999px; background: #202124; color: #fff; font-size: 13px;
           box-shadow: 0 6px 24px rgba(0,0,0,.25); transition: opacity .3s, transform .3s; animation: mc-panel-in .2s; }
  .mc-toast.mc-out { opacity: 0; transform: translateX(-50%) translateY(8px); }
  .mc-toggle { all: unset; position: fixed; right: 18px; bottom: 18px; z-index: ${Z + 4}; display: flex; align-items: center; gap: 8px;
           padding: 9px 14px; border-radius: 999px; font-size: 13px; color: var(--mc-fg); background: var(--mc-bg);
           border: 1px solid var(--mc-line); box-shadow: 0 4px 18px rgba(0,0,0,.12); backdrop-filter: blur(12px);
           cursor: pointer; transition: box-shadow .2s; }
  .mc-toggle .mc-star { font-size: 15px; background: linear-gradient(135deg, ${PALETTE.join(',')}); -webkit-background-clip: text; background-clip: text; color: transparent; }
  .mc-toggle small { color: var(--mc-muted); }
  html.mc-active .mc-toggle { box-shadow: 0 0 0 2px rgba(155,114,203,.5), 0 0 24px rgba(155,114,203,.45); }
  `;

  // ───────────────────────── Durum ─────────────────────────
  let active = false;
  let canvas, ctx, dpr = 1, raf = 0;
  const ptr = { x: -100, y: -100, inside: false, lastMove: 0 };
  const trail = [];
  const particles = [];
  const rings = [];
  let orbR = 9;
  let drawing = null; // [{x,y}]
  let target = null; // {kind:'range'|'element'|'region', ...}
  let panel = null, panelTimer = 0, hideTimer = 0, idleTimer = 0;
  const hls = [];
  let toggleBtn;

  function setup() {
    const style = document.createElement('style');
    style.id = 'mc-style';
    style.textContent = CSS;
    document.head.appendChild(style);

    canvas = document.createElement('canvas');
    canvas.id = 'mc-canvas';
    canvas.className = 'mc-ui';
    document.body.appendChild(canvas);
    ctx = canvas.getContext('2d');
    resize();

    toggleBtn = document.createElement('button');
    toggleBtn.className = 'mc-toggle mc-ui';
    toggleBtn.innerHTML = '<span class="mc-star">✦</span><span>Magic Pointer</span><small>salla · Alt+G</small>';
    toggleBtn.addEventListener('click', (e) => { e.stopPropagation(); toggle(); });
    document.body.appendChild(toggleBtn);

    addEventListener('resize', resize);
    addEventListener('pointermove', onMove, { passive: true });
    addEventListener('pointerdown', onDown, true);
    addEventListener('pointerup', onUp, true);
    addEventListener('keydown', onKey, true);
    addEventListener('scroll', onScroll, true);
    document.documentElement.addEventListener('pointerleave', () => { ptr.inside = false; kick(); });
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = innerWidth * dpr;
    canvas.height = innerHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  const isOurUI = (el) => el && el.closest && el.closest('.mc-panel, .mc-toggle, .mc-toast');

  // ───────────────────────── Aç / kapat ─────────────────────────
  function activate() {
    if (active) return;
    active = true;
    document.documentElement.classList.add('mc-active');
    burst(ptr.x, ptr.y, 46);
    rings.push({ x: ptr.x, y: ptr.y, t0: performance.now() });
    toast('✦ Magic Pointer açık — bir şeyin üzerine gel ya da etrafına daire çiz');
    bumpIdle();
    kick();
    if (ptr.inside) updateTarget();
  }

  function deactivate() {
    if (!active) return;
    active = false;
    drawing = null;
    document.documentElement.classList.remove('mc-active');
    clearTarget();
    clearTimeout(idleTimer);
    kick();
  }

  const toggle = () => (active ? deactivate() : activate());

  function bumpIdle() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { if (!panel && !drawing) deactivate(); }, 20000);
  }

  // ───────────────────────── Sallama algılama ─────────────────────────
  const wig = { lastX: null, dir: 0, acc: 0, flips: [] };
  function detectWiggle(x, t) {
    if (wig.lastX === null) { wig.lastX = x; return; }
    const dx = x - wig.lastX;
    wig.lastX = x;
    const d = Math.sign(dx);
    if (!d) return;
    if (d === wig.dir) wig.acc += Math.abs(dx);
    else {
      if (wig.acc > 28) wig.flips.push(t);
      wig.dir = d;
      wig.acc = Math.abs(dx);
    }
    while (wig.flips.length && t - wig.flips[0] > 750) wig.flips.shift();
    if (wig.flips.length >= 4) {
      wig.flips.length = 0;
      if (!active) activate();
      else burst(x, ptr.y, 24);
    }
  }

  // ───────────────────────── Olaylar ─────────────────────────
  let moveQueued = false;
  function onMove(e) {
    if (e.pointerType === 'touch') return;
    ptr.x = e.clientX; ptr.y = e.clientY; ptr.inside = true; ptr.lastMove = performance.now();
    detectWiggle(e.clientX, e.timeStamp || performance.now());
    if (!active) return;
    bumpIdle();
    trail.push({ x: ptr.x, y: ptr.y, t: ptr.lastMove });
    if (Math.random() < 0.35) spark(ptr.x, ptr.y);
    if (drawing) { drawing.push({ x: ptr.x, y: ptr.y }); kick(); return; }
    kick();
    if (!moveQueued) {
      moveQueued = true;
      requestAnimationFrame(() => { moveQueued = false; updateTarget(e.target); });
    }
  }

  function onDown(e) {
    if (!active || e.button !== 0 || e.pointerType === 'touch') return;
    if (isOurUI(e.target)) return;
    e.preventDefault();
    drawing = [{ x: e.clientX, y: e.clientY }];
  }

  function onUp(e) {
    if (!drawing) return;
    const path = drawing;
    drawing = null;
    const xs = path.map((p) => p.x), ys = path.map((p) => p.y);
    const box = { left: Math.min(...xs), top: Math.min(...ys), right: Math.max(...xs), bottom: Math.max(...ys) };
    if (box.right - box.left < 30 && box.bottom - box.top < 30) return; // normal tıklama
    // daire çizimi sonrası tetiklenen tıklamayı yut
    const swallow = (ev) => { ev.preventDefault(); ev.stopPropagation(); };
    addEventListener('click', swallow, { capture: true, once: true });
    setTimeout(() => removeEventListener('click', swallow, true), 0);
    selectRegion(box, path);
  }

  function onKey(e) {
    if (e.altKey && e.code === 'KeyG') { e.preventDefault(); toggle(); return; }
    if (e.key === 'Escape' && active) {
      if (panel || target) clearTarget();
      else deactivate();
    }
  }

  function onScroll() {
    if (!target) return;
    if (target.kind === 'region') return clearTarget();
    renderTarget(false);
  }

  // ───────────────────────── Hedef bulma ─────────────────────────
  function caretAt(x, y) {
    if (document.caretPositionFromPoint) {
      const p = document.caretPositionFromPoint(x, y);
      return p && { node: p.offsetNode, offset: p.offset };
    }
    if (document.caretRangeFromPoint) {
      const r = document.caretRangeFromPoint(x, y);
      return r && { node: r.startContainer, offset: r.startOffset };
    }
    return null;
  }

  function rangeHas(range, x, y, padPx = 3) {
    for (const r of range.getClientRects()) {
      if (x >= r.left - padPx && x <= r.right + padPx && y >= r.top - padPx && y <= r.bottom + padPx) return true;
    }
    return false;
  }

  function mkRange(node, s, e) {
    const r = document.createRange();
    r.setStart(node, s);
    r.setEnd(node, e);
    return r;
  }

  function hitTest(x, y, el) {
    el = el && el.nodeType === 1 ? el : document.elementFromPoint(x, y);
    if (!el || isOurUI(el) || el === canvas) return null;

    const img = el.closest('img, svg image, picture img');
    if (img && img.tagName === 'IMG') return { kind: 'element', el: img, type: 'image' };

    const c = caretAt(x, y);
    if (c && c.node && c.node.nodeType === 3 && !isOurUI(c.node.parentElement)) {
      const node = c.node, text = node.data;
      for (const ent of findEntities(text)) {
        if (c.offset < ent.start - 1 || c.offset > ent.end + 1) continue;
        const range = mkRange(node, ent.start, ent.end);
        if (rangeHas(range, x, y)) {
          const [ss, se] = sentenceBounds(text, ent.start);
          return { kind: 'range', node, start: ent.start, end: ent.end, range, type: ent.type, entity: ent, context: text.slice(ss, se) };
        }
      }
      const link = node.parentElement.closest('a[href]');
      if (link && rangeHas(mkRange(node, 0, text.length), x, y)) {
        return { kind: 'element', el: link, type: 'url', entity: { type: 'url', text: link.textContent.trim(), data: { url: link.href } } };
      }
      // kelimenin üzerinde miyiz? → cümleyi seç
      let ws = Math.min(c.offset, text.length), we = ws;
      while (ws > 0 && isWordChar(text[ws - 1])) ws--;
      while (we < text.length && isWordChar(text[we])) we++;
      if (we > ws && rangeHas(mkRange(node, ws, we), x, y, 2)) {
        const [s, e] = sentenceBounds(text, ws);
        if (e - s > 0) {
          const range = mkRange(node, s, e);
          const word = text.slice(ws, we);
          return { kind: 'range', node, start: s, end: e, range, type: 'text', word, context: text.slice(s, e) };
        }
      }
    }
    return null;
  }

  const sameTarget = (a, b) =>
    a && b && a.kind === b.kind &&
    (a.kind === 'element' ? a.el === b.el : a.kind === 'range' ? a.node === b.node && a.start === b.start && a.end === b.end : false);

  function updateTarget(evTarget) {
    if (!active || drawing) return;
    if (panel && (isOurUI(evTarget) || pointInRect(ptr.x, ptr.y, panel.getBoundingClientRect(), 6))) {
      clearTimeout(hideTimer);
      return;
    }
    if (target && target.kind === 'region') {
      // bölge seçiliyken panel açık kalsın; dışarı uzaklaşırsak kapat
      const r = target.rect;
      if (!pointInRect(ptr.x, ptr.y, { left: r.left - 80, top: r.top - 80, right: r.right + 80, bottom: r.bottom + 80 }, 0)) scheduleHide();
      else clearTimeout(hideTimer);
      return;
    }
    const t = hitTest(ptr.x, ptr.y, evTarget);
    if (sameTarget(t, target)) { clearTimeout(hideTimer); return; }
    if (!t) { if (target) scheduleHide(); return; }
    clearTimeout(hideTimer);
    setTarget(t);
  }

  const pointInRect = (x, y, r, p) => x >= r.left - p && x <= r.right + p && y >= r.top - p && y <= r.bottom + p;

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(clearTarget, 380);
  }

  function setTarget(t) {
    target = t;
    closePanel();
    renderTarget(true);
    clearTimeout(panelTimer);
    panelTimer = setTimeout(() => target === t && openPanel(t), 260);
  }

  function clearTarget() {
    target = null;
    clearTimeout(panelTimer);
    clearTimeout(hideTimer);
    closePanel();
    hls.forEach((h) => h.remove());
    hls.length = 0;
  }

  function targetRects(t) {
    if (t.kind === 'region') return [t.rect];
    const raw = t.kind === 'range' ? [...t.range.getClientRects()] : [t.el.getBoundingClientRect()];
    // aynı satırdaki parçaları birleştir
    const lines = [];
    for (const r of raw) {
      if (r.width < 1 || r.height < 1) continue;
      const l = lines.find((q) => Math.abs(q.top - r.top) < 4 && Math.abs(q.bottom - r.bottom) < 4);
      if (l) { l.left = Math.min(l.left, r.left); l.right = Math.max(l.right, r.right); }
      else lines.push({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
    }
    return lines;
  }

  function renderTarget() {
    if (!target) return;
    const rects = targetRects(target);
    const p = target.kind === 'region' ? 6 : target.kind === 'element' ? 4 : 3;
    while (hls.length < rects.length) {
      const h = document.createElement('div');
      h.className = 'mc-hl mc-ui';
      document.body.appendChild(h);
      hls.push(h);
    }
    while (hls.length > rects.length) hls.pop().remove();
    rects.forEach((r, i) => {
      Object.assign(hls[i].style, {
        left: r.left - p + 'px', top: r.top - p + 'px',
        width: r.right - r.left + p * 2 + 'px', height: r.bottom - r.top + p * 2 + 'px',
        borderRadius: target.kind === 'region' ? '16px' : '8px',
      });
    });
    if (panel) positionPanel(rects);
  }

  // ───────────────────────── Panel ─────────────────────────
  function openPanel(t) {
    closePanel();
    let type = t.type, preview = '', actions = [], swatch = null;

    if (t.kind === 'region') {
      preview = t.text ? `${t.text.length} karakter` : `${t.images.length} görsel`;
      const ents = t.text ? findEntities(t.text).slice(0, 3) : [];
      for (const en of ents) {
        const [first] = entityActions(en, t.text);
        if (first) actions.push({ ...first, label: `${first.label} · ${clip(en.text, 22)}`, primary: true });
      }
      if (t.text) actions.push(...textActions(t.text));
      if (t.images.length) actions.push(...imageActions(t.images[0]).slice(0, 2));
    } else if (t.type === 'image') {
      preview = t.el.alt || 'Görsel';
      actions = imageActions(t.el);
    } else if (t.type === 'text') {
      preview = t.context;
      actions = textActions(t.context);
      if (t.word && t.word.length > 2) {
        actions.splice(2, 0, { icon: '📖', label: `“${clip(t.word, 16)}” ne demek?`, run: () => search(`${t.word} ${looksTurkish(t.context) ? 'ne demek' : 'meaning'}`) });
      }
    } else {
      preview = t.entity.text;
      actions = entityActions(t.entity, t.context || '');
      if (t.type === 'color') swatch = t.entity.text;
      if (t.type === 'date') {
        const d = t.entity.data;
        preview = d.date.toLocaleString('tr-TR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', ...(d.hasTime ? { hour: '2-digit', minute: '2-digit' } : {}) });
      }
      if (actions[0]) actions[0].primary = true;
    }
    if (!actions.length) return;

    const [icon, label] = TYPE_META[type] || TYPE_META.text;
    panel = document.createElement('div');
    panel.className = 'mc-panel mc-ui';
    const head = document.createElement('div');
    head.className = 'mc-head';
    if (swatch) {
      const sw = document.createElement('span');
      sw.className = 'mc-swatch';
      sw.style.background = swatch;
      head.appendChild(sw);
    } else head.append(icon);
    const b = document.createElement('b');
    b.textContent = label;
    const pv = document.createElement('span');
    pv.className = 'mc-prev';
    pv.textContent = clip(preview, 70);
    head.append(b, '·', pv);
    const chips = document.createElement('div');
    chips.className = 'mc-chips';
    actions.forEach((a, i) => {
      const c = document.createElement('button');
      c.className = 'mc-chip' + (a.primary ? ' mc-primary' : '');
      c.style.animationDelay = i * 35 + 'ms';
      c.textContent = `${a.icon} ${a.label}`;
      c.addEventListener('click', (ev) => {
        ev.preventDefault(); ev.stopPropagation();
        const r = c.getBoundingClientRect();
        burst(r.left + r.width / 2, r.top + r.height / 2, 18);
        a.run();
        clearTarget();
      });
      chips.appendChild(c);
    });
    panel.append(head, chips);
    document.body.appendChild(panel);
    positionPanel(targetRects(t));
  }

  function positionPanel(rects) {
    if (!panel || !rects.length) return;
    const u = rects.reduce((a, r) => ({
      left: Math.min(a.left, r.left), top: Math.min(a.top, r.top),
      right: Math.max(a.right, r.right), bottom: Math.max(a.bottom, r.bottom),
    }));
    const pw = panel.offsetWidth, ph = panel.offsetHeight, gap = 12;
    let top = u.bottom + gap;
    let above = false;
    if (top + ph > innerHeight - 8 && u.top - gap - ph > 8) { top = u.top - gap - ph; above = true; }
    const anchorX = target && target.kind !== 'region' ? Math.min(Math.max(ptr.x - 24, u.left), u.right) : u.left;
    const left = Math.max(8, Math.min(anchorX, innerWidth - pw - 8));
    panel.classList.toggle('mc-above', above);
    panel.style.left = left + 'px';
    panel.style.top = Math.max(8, Math.min(top, innerHeight - ph - 8)) + 'px';
  }

  function closePanel() {
    if (panel) { panel.remove(); panel = null; }
  }

  // ───────────────────────── Daire ile seçim ─────────────────────────
  function selectRegion(box) {
    const inter = (r) => r.right > box.left && r.left < box.right && r.bottom > box.top && r.top < box.bottom;
    const parts = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => {
        const p = n.parentElement;
        if (!p || !n.data.trim() || isOurUI(p) || p.closest('script, style, noscript, .mc-ui')) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const r = document.createRange();
    for (let n; (n = walker.nextNode());) {
      r.selectNodeContents(n);
      const rects = [...r.getClientRects()];
      if (!rects.some(inter)) continue;
      // yalnızca alanın içine düşen kelimeleri al
      const words = [];
      const re = /\S+/g;
      let m;
      while ((m = re.exec(n.data))) {
        const wr = mkRange(n, m.index, m.index + m[0].length).getBoundingClientRect();
        const cx = wr.left + wr.width / 2, cy = wr.top + wr.height / 2;
        if (cx >= box.left && cx <= box.right && cy >= box.top && cy <= box.bottom) words.push(m[0]);
      }
      if (words.length) parts.push(words.join(' '));
    }
    const images = [...document.images].filter((img) => !isOurUI(img) && inter(img.getBoundingClientRect()));
    const text = parts.join(' ').replace(/\s+/g, ' ').trim().slice(0, 3000);
    if (!text && !images.length) { toast('Seçilen alanda bir şey bulunamadı'); return; }
    clearTarget();
    target = { kind: 'region', type: 'region', rect: box, text, images };
    renderTarget();
    burst((box.left + box.right) / 2, (box.top + box.bottom) / 2, 30);
    openPanel(target);
  }

  // ───────────────────────── Çizim (canvas) ─────────────────────────
  const rnd = (a, b) => a + Math.random() * (b - a);
  function spark(x, y) {
    particles.push({
      x: x + rnd(-4, 4), y: y + rnd(-4, 4), vx: rnd(-0.6, 0.6), vy: rnd(-0.9, 0.2),
      life: 0, max: rnd(500, 900), size: rnd(1.2, 2.8), color: PALETTE[(Math.random() * PALETTE.length) | 0],
    });
  }
  function burst(x, y, n) {
    if (x < 0) return;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + rnd(-0.2, 0.2), s = rnd(1.5, 4.5);
      particles.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 0, max: rnd(500, 1000), size: rnd(1.5, 3.5), color: PALETTE[i % PALETTE.length] });
    }
    kick();
  }

  function kick() {
    if (!raf) raf = requestAnimationFrame(frame);
  }

  let lastT = performance.now();
  function frame(now) {
    raf = 0;
    const dt = Math.min(48, now - lastT);
    lastT = now;
    ctx.clearRect(0, 0, innerWidth, innerHeight);

    // kuyruk
    while (trail.length && now - trail[0].t > 220) trail.shift();
    if (active && trail.length > 1) {
      ctx.lineCap = 'round';
      for (let i = 1; i < trail.length; i++) {
        const a = trail[i - 1], b = trail[i], k = i / trail.length;
        ctx.strokeStyle = PALETTE[i % PALETTE.length];
        ctx.globalAlpha = k * 0.55;
        ctx.lineWidth = 1 + k * 5;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    // parçacıklar
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.life += dt;
      if (p.life >= p.max) { particles.splice(i, 1); continue; }
      p.x += p.vx * dt / 16; p.y += p.vy * dt / 16;
      p.vx *= 0.96; p.vy = p.vy * 0.96 + 0.02;
      const k = 1 - p.life / p.max;
      ctx.globalAlpha = k;
      ctx.fillStyle = p.color;
      star(p.x, p.y, p.size * (0.6 + k));
    }
    ctx.globalAlpha = 1;

    // aktivasyon halkaları
    for (let i = rings.length - 1; i >= 0; i--) {
      const r = rings[i], k = (now - r.t0) / 600;
      if (k >= 1) { rings.splice(i, 1); continue; }
      ctx.globalAlpha = 1 - k;
      ctx.lineWidth = 3 * (1 - k) + 0.5;
      ctx.strokeStyle = gradient(r.x, r.y, now);
      ctx.beginPath(); ctx.arc(r.x, r.y, 10 + k * 70, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // daire çizimi
    if (drawing && drawing.length > 1) {
      ctx.save();
      ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.lineWidth = 4;
      ctx.shadowBlur = 16; ctx.shadowColor = 'rgba(155,114,203,.8)';
      const g = ctx.createLinearGradient(drawing[0].x - 100, drawing[0].y - 100, drawing[0].x + 100, drawing[0].y + 100);
      PALETTE.forEach((c, i) => g.addColorStop(i / (PALETTE.length - 1), c));
      ctx.strokeStyle = g;
      ctx.beginPath();
      ctx.moveTo(drawing[0].x, drawing[0].y);
      for (const p of drawing) ctx.lineTo(p.x, p.y);
      ctx.stroke();
      ctx.restore();
    }

    // imleç küresi
    if (active && ptr.inside) {
      const hovering = !!target && !drawing;
      orbR += ((hovering ? 13 : 8) - orbR) * 0.25;
      const pulse = 1 + Math.sin(now / 220) * 0.08;
      const { x, y } = ptr;
      ctx.save();
      ctx.shadowBlur = 22; ctx.shadowColor = 'rgba(155,114,203,.85)';
      ctx.strokeStyle = ctx.fillStyle = gradient(x, y, now);
      ctx.beginPath(); ctx.arc(x, y, orbR * pulse, 0, Math.PI * 2);
      if (hovering) { ctx.lineWidth = 3; ctx.stroke(); } else ctx.fill();
      ctx.shadowBlur = 0;
      ctx.fillStyle = 'rgba(255,255,255,.95)';
      ctx.beginPath(); ctx.arc(x, y, hovering ? 2.5 : orbR * 0.32, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    }

    if (active || particles.length || rings.length || trail.length) kick();
  }

  function gradient(x, y, now) {
    let g;
    if (ctx.createConicGradient) {
      g = ctx.createConicGradient(now / 500, x, y);
      PALETTE.forEach((c, i) => g.addColorStop(i / PALETTE.length, c));
      g.addColorStop(1, PALETTE[0]);
    } else {
      g = ctx.createLinearGradient(x - 12, y - 12, x + 12, y + 12);
      PALETTE.forEach((c, i) => g.addColorStop(i / (PALETTE.length - 1), c));
    }
    return g;
  }

  function star(x, y, r) {
    ctx.beginPath();
    ctx.moveTo(x, y - r * 2);
    ctx.quadraticCurveTo(x, y, x + r * 2, y);
    ctx.quadraticCurveTo(x, y, x, y + r * 2);
    ctx.quadraticCurveTo(x, y, x - r * 2, y);
    ctx.quadraticCurveTo(x, y, x, y - r * 2);
    ctx.fill();
  }

  // ───────────────────────── Başlat ─────────────────────────
  window.MagicCursor = { activate, deactivate, toggle, isActive: () => active, findEntities };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup);
  else setup();
})();
