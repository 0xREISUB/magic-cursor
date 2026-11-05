# ✦ Magic Cursor

Linux masaüstü için bağlamsal, yapay zekâ destekli imleç. Fareyi sallayınca açılır, ekranda imlecin altındaki şeyi anlar ve ne yapmak isteyebileceğini önerir.

*A context-aware, AI-assisted pointer for the Linux desktop (X11 / GNOME). Wiggle the mouse, hover anything on screen, get one-click actions or ask an AI about it.*

<p align="center"><img src="docs/screenshot.png" width="480" alt="Seçili bir alan ve yapay zekâ sohbet paneli"></p>

## Özellikler

- **Salla ve aç:** Fareyi hızlıca sağa sola salla ya da <kbd>Super</kbd>+<kbd>G</kbd>'ye bas. Gerçek imleç kısa bir savrulma animasyonu yapar, etrafında hafif bir ışıltı belirir.
- **Her uygulamada çalışır:** Ekran OCR ile okunur (Tesseract), yani tarayıcı, editör, PDF, terminal fark etmez.
- **Akıllı öneriler:** Üzerine geldiğin şeye göre:

  | Algılanan | Eylemler |
  |---|---|
  | 📅 Tarih / saat | Google Takvim'e ekle, `.ics` kaydet |
  | 📍 Adres | Haritada göster, yol tarifi |
  | 📞 Telefon | WhatsApp, ara, kopyala |
  | ✉️ E-posta · 🔗 Link | Yaz / aç, kopyala |
  | 💱 Fiyat | Döviz çevirisi |
  | 🎨 Renk kodu | HEX / RGB kopyala |
  | ✦ Metin | Açıkla (AI), kopyala, ara, çevir, sesli oku, kelimenin anlamı |

- **Daire çizerek seç:** Mod açıkken sol tıkla basılı tutup bir alanın etrafını dolaş. O alanın metni ve görüntüsüyle işlem yapabilir, yapay zekâya sorabilirsin.
- **Devam soruları:** Groq (`qwen/qwen3.8-27b`, görsel destekli) yanıtını panelde akışlı olarak gösterir. Altındaki kutudan konuşmaya devam edebilirsin.
- **Akışını bozmaz:** Normal bir tıklama modu kapatır ve tıklamayı alttaki uygulamaya iletir.

## Gereksinimler

- Linux, **X11 oturumu** (Wayland desteklenmiyor) ve kompozitörlü bir masaüstü (GNOME'da test edildi)
- Python 3.10+ ve PyGObject (GTK 3)
- Tesseract OCR (Türkçe için `tur` dil paketi)
- Ücretsiz bir [Groq API anahtarı](https://console.groq.com/keys) (yalnızca yapay zekâ özellikleri için)

Debian / Ubuntu / Zorin:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
                 tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng \
                 libxtst6 libxfixes3 speech-dispatcher
```

## Kurulum

```bash
git clone https://github.com/0xREISUB/magic-cursor.git
cd magic-cursor/desktop
./install.sh
```

`install.sh` şunları yapar:
- girişte otomatik başlatmayı ekler (`~/.config/autostart/magic-cursor.desktop`),
- <kbd>Super</kbd>+<kbd>G</kbd> kısayolunu tanımlar,
- ayar dosyasını oluşturur,
- programı hemen başlatır.

Ardından Groq anahtarını `~/.config/magic-cursor/config.json` dosyasına ekle:

```json
{
  "groq_api_key": "gsk_...",
  "groq_model": "qwen/qwen3.8-27b"
}
```

Anahtarı ekledikten sonra programı yeniden başlat: `python3 magic_cursor.py quit && python3 magic_cursor.py &`

Kaldırmak için `./uninstall.sh` çalıştır. Ayar dosyan silinmez.

## Kullanım

| Ne yaparsın | Ne olur |
|---|---|
| Fareyi salla / <kbd>Super</kbd>+<kbd>G</kbd> | Magic mod açılır veya kapanır |
| Bir şeyin üzerine gel | Vurgulanır, ~0.3 sn sonra öneri paneli çıkar |
| Sol tıkla basılı tut + daire çiz | Alan seçilir |
| ✨ Açıkla / Yapay zekâya sor | Groq yanıtı gelir, altına devam sorusu yazabilirsin |
| Normal tıklama, tekerlek, ✕ | Mod kapanır, tıklama uygulamaya iletilir |
| <kbd>Esc</kbd> (panel odaktayken) | Paneli kapatır |

Komut satırından:

```bash
python3 desktop/magic_cursor.py          # arka planda çalıştır
python3 desktop/magic_cursor.py toggle   # aç / kapat
python3 desktop/magic_cursor.py quit     # kapat
```

Ortam değişkenleri: `GROQ_API_KEY`, `MAGIC_CURSOR_MODEL`, `MAGIC_CURSOR_WIGGLE=0` (sallamayı kapatır).

## Nasıl çalışır?

1. Mod açılınca ekranın bir görüntüsü alınır ve Tesseract ile arka planda, düşük öncelikle okunur.
2. Tesseract'ın kitap odaklı paragraf gruplaması yerine kelimeler ekrana uygun şekilde yeniden gruplanır. Önce satırlara (sütun ve panel boşlukları satırı böler), sonra hizalı ve aynı yazı boyutundaki satırlardan bloklara.
3. Her blokta tarih, adres, telefon, fiyat gibi kalıplar düzenli ifadelerle aranır.
4. Vurgulama, panel ve ışıltı küçük, ayrı pencerelerdir. Ekranı kaplayan tek şey, sürüklemeyi yakalamak için kullanılan şeffaf bir giriş katmanıdır. Bu katmanda panelin ve durum çubuğunun yerinde delik vardır.
5. Normal tıklamalar XTest ile alttaki uygulamaya yeniden gönderilir. Açılış animasyonunda gerçek imleç XFixes ile kısa süre gizlenir ve yerine sistemin imleç görüntüsü döndürülerek çizilir.

## Bilinen sınırlamalar

- Yalnızca X11'de çalışır. Wayland, uygulamaların ekranı okumasına ve global fare takibine izin vermez.
- Koyu temalı kod editörlerinde OCR bazı kelimeleri (özellikle alt çizgili olanları) kaçırabilir.
- Mod açıkken uygulamalarda sürükle-bırak yapılamaz, çünkü sol tıkla sürükleme alan seçimidir. Bir tıklama normal kullanıma döndürür.
- Ekran görüntüsü mod açıldığı anda alınır. Mod açıkken ekran değişirse yeniden açmak gerekir.

## Web sürümü

[`web/`](web/) klasöründe, herhangi bir web sayfasına tek satırla eklenebilen bir JavaScript sürümü var:

```html
<script src="magic-cursor.js"></script>
```

Demo için `web/index.html` dosyasını tarayıcıda aç.

## Lisans

[MIT](LICENSE)
