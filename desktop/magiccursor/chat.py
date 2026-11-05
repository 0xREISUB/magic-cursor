"""Panel içindeki Groq sohbeti: ilk açıklama ve devam soruları."""
import threading
import time
import urllib.error

from gi.repository import Gdk, GLib, Gtk

from .config import CONFIG_PATH, log
from .groq import groq_stream, image_part, md_markup


class ChatMixin:
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
