"""Groq (OpenAI uyumlu) sohbet istemcisi: görsel + konuşma geçmişi, akışlı yanıt."""
import base64
import json
import urllib.request

from gi.repository import GdkPixbuf

SYSTEM_PROMPT = ('Sen kullanıcının ekranındaki içeriği açıklayan kısa ve net bir asistansın. '
                 'Her zaman Türkçe yanıt ver. Gereksiz giriş cümlesi kurma. '
                 'Devam sorularında önceki konuşmayı ve ilk görüntüyü bağlam olarak kullan. '
                 'Biçimlendirmeyi sade tut: gerekirse **kalın**, `kod`, kısa madde listeleri ve kod blokları '
                 'kullan; başlık, tablo ve emoji kullanma. Formülleri düz metinle yaz.')


def image_part(pb):
    w, h = pb.get_width(), pb.get_height()
    m = max(w, h)
    if m > 1280:
        pb = pb.scale_simple(int(w * 1280 / m), int(h * 1280 / m), GdkPixbuf.InterpType.BILINEAR)
    ok, buf = pb.save_to_bufferv('jpeg', ['quality'], ['85'])
    if not ok:
        return None
    return {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(buf).decode()}}


def groq_stream(cfg, messages, on_chunk):
    """Groq chat completions (OpenAI uyumlu) — konuşma geçmişiyle akışlı yanıt."""
    body = {
        'model': cfg['groq_model'],
        'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}]
                    + [{'role': m['role'], 'content': m['content']} for m in messages],
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
