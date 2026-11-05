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

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
