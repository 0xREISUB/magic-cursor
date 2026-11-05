"""Ön plandaki pencere oyun veya tam ekran mı? Öyleyse sallamayla açılmayı engelle."""
import os
import re
import subprocess

# Süreç zincirinde bunlardan biri varsa pencere bir oyundur (comm adları 15 karakterle sınırlı).
GAME_PROCS = (
    'reaper',            # Steam oyun başlatıcısı
    'pressure-vessel',   # Steam Linux Runtime
    'srt-bwrap',
    'gamescope',
    'wine', 'wineserver', 'wine64', 'wine-preloader', 'wine64-preloade',
    'proton',
    'lutris-wrapper',
    'legendary', 'gogdl', 'nile',  # Heroic arka uçları
    'umu-run',
)
GAME_CLASS = re.compile(r'^steam_app_|\.exe$|^gamescope|^retroarch|^minecraft|^dolphin-emu|^pcsx2|^rpcs3|'
                        r'^ryujinx|^yuzu|^citra|^ppsspp|^duckstation|^cemu', re.I)


def _xprop(args):
    try:
        return subprocess.run(['xprop'] + args, capture_output=True, text=True, timeout=1).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ''


def _ancestry(pid, depth=20):
    """pid'den yukarı doğru süreç adları (comm ve exe adı)."""
    names = []
    for _ in range(depth):
        if pid <= 1:
            break
        try:
            with open(f'/proc/{pid}/comm') as f:
                names.append(f.read().strip())
            with open(f'/proc/{pid}/stat') as f:
                # comm parantez içinde boşluk içerebilir → son ')' sonrası alanlar
                pid = int(f.read().rsplit(')', 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return names


def active_window_info():
    """(wm_class, fullscreen, pid) — bilgi alınamazsa None."""
    out = _xprop(['-root', '_NET_ACTIVE_WINDOW'])
    m = re.search(r'window id # (0x[0-9a-f]+)', out)
    if not m or int(m.group(1), 16) == 0:
        return None
    props = _xprop(['-id', m.group(1), '_NET_WM_STATE', 'WM_CLASS', '_NET_WM_PID'])
    wm_class = ' '.join(re.findall(r'"([^"]*)"', props.split('WM_CLASS', 1)[1].splitlines()[0])) \
        if 'WM_CLASS(' in props else ''
    fullscreen = '_NET_WM_STATE_FULLSCREEN' in props
    pm = re.search(r'_NET_WM_PID\(CARDINAL\) = (\d+)', props)
    return wm_class, fullscreen, int(pm.group(1)) if pm else 0


def blocked_reason(cfg):
    """Sallamayla açılmayı engelleyen bir durum varsa nedenini döndürür, yoksa None."""
    info = active_window_info()
    if not info:
        return None
    wm_class, fullscreen, pid = info
    extra = [s.lower() for s in cfg.get('blocked_apps', [])]
    if fullscreen and cfg.get('block_fullscreen', True):
        return f'tam ekran pencere ({wm_class or "?"})'
    for part in wm_class.split():
        if GAME_CLASS.search(part):
            return f'oyun penceresi ({part})'
    procs = _ancestry(pid) if pid else []
    for name in procs:
        low = name.lower()
        if low.endswith('.exe') or any(low == g or low.startswith(g) for g in GAME_PROCS):
            return f'oyun süreci ({name})'
    haystack = (wm_class + ' ' + ' '.join(procs)).lower()
    for app in extra:
        if app and app in haystack:
            return f'engellenen uygulama ({app})'
    return None


if __name__ == '__main__':  # hızlı test: python3 -m magiccursor.games
    print('aktif pencere:', active_window_info())
    print('engel:', blocked_reason({}) or 'yok')
    if os.environ.get('MC_DEBUG_PID'):
        print(_ancestry(int(os.environ['MC_DEBUG_PID'])))
