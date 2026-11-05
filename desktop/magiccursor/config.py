"""Sabitler, ayar dosyası ve günlük."""
import json
import os
import sys
import tempfile

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
