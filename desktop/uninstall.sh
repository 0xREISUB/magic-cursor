#!/usr/bin/env bash
# Magic Cursor'ı kaldırır (ayar dosyası ~/.config/magic-cursor korunur)
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$DIR/magic_cursor.py" quit >/dev/null 2>&1
rm -f ~/.config/autostart/magic-cursor.desktop

BASE=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
list=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)
for id in magic-cursor magic-cursor-region; do
  path="$BASE/$id/"
  gsettings reset-recursively "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$path" 2>/dev/null
  list=$(echo "$list" | sed -e "s#, '$path'##" -e "s#'$path', ##" -e "s#'$path'##")
done
[[ "$list" == "[]" ]] && list="@as []"
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$list"
echo "✓ Magic Cursor kaldırıldı."
