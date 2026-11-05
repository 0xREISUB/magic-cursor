#!/usr/bin/env bash
# Magic Cursor kurulumu: girişte otomatik başlat + GNOME kısayolları
#   Super+G  → aç / kapat
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/magic_cursor.py"
chmod +x "$APP"

# 1) Otomatik başlatma
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/magic-cursor.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Magic Cursor
Comment=Bağlamsal imleç
Exec=python3 "$APP"
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF

# 2) Ayar dosyası (Groq anahtarı için)
mkdir -p ~/.config/magic-cursor
if [ ! -f ~/.config/magic-cursor/config.json ]; then
  printf '{\n  "groq_api_key": "",\n  "groq_model": "qwen/qwen3.8-27b"\n}\n' > ~/.config/magic-cursor/config.json
  chmod 600 ~/.config/magic-cursor/config.json
fi

# 3) GNOME kısayolları
BASE=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
SCHEMA=org.gnome.settings-daemon.plugins.media-keys.custom-keybinding
add_binding() {  # id name command binding
  local path="$BASE/$1/"
  local list
  list=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)
  if [[ "$list" != *"$path"* ]]; then
    if [[ "$list" == "@as []" || "$list" == "[]" ]]; then
      list="['$path']"
    else
      list="${list%]}, '$path']"
    fi
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$list"
  fi
  gsettings set "$SCHEMA:$path" name "$2"
  gsettings set "$SCHEMA:$path" command "$3"
  gsettings set "$SCHEMA:$path" binding "$4"
}
add_binding magic-cursor "Magic Cursor" "python3 \"$APP\" toggle" "<Super>g"

# 4) Şimdi başlat
python3 "$APP" quit >/dev/null 2>&1 || true
sleep 0.5
setsid python3 "$APP" >/dev/null 2>&1 < /dev/null &

echo "✓ Magic Cursor kuruldu ve çalışıyor."
echo "  Fareyi salla veya Super+G → aç/kapat · açıkken sol tıkla basılı tutup daire çiz → alan seç"
echo "  Groq anahtarı: ~/.config/magic-cursor/config.json"
if ! tesseract --list-langs 2>/dev/null | grep -qx tur; then
  echo "  İpucu: Türkçe OCR için → sudo apt install tesseract-ocr-tur"
fi
