#!/usr/bin/env bash
set -euo pipefail

APP_NAME="AMDL"
VERSION="1.2.0"
PKG_DIR="release_linux/${APP_NAME}-${VERSION}-linux-x86_64"

rm -rf build dist release_linux installer_out_linux
mkdir -p "$PKG_DIR" installer_out_linux

ICON_ARGS=()
if [ -f "icon.ico" ]; then
    ICON_ARGS+=(--add-data "icon.ico:.")
fi

# 1. Сборка автономного Linux-приложения
python3 -m PyInstaller --noconfirm --onedir --noconsole \
    --name "$APP_NAME" \
    "${ICON_ARGS[@]}" \
    --collect-all customtkinter \
    main.py

cp -r "dist/${APP_NAME}/"* "$PKG_DIR/"

# Копируем internal без Windows-файлов, логов и личных настроек
if [ -d "internal" ]; then
    mkdir -p "$PKG_DIR/internal"
    cp -r internal/. "$PKG_DIR/internal/"
    rm -rf "$PKG_DIR/internal/"*windows* \
           "$PKG_DIR/internal/logs" \
           "$PKG_DIR/internal/user_settings.json" \
           "$PKG_DIR/internal/"*.exe \
           "$PKG_DIR/internal/"*.log
fi

# 2. Скрипт установки для конечного пользователя (~/.local/share/AMDL + ярлык в меню)
cat << 'EOF' > "$PKG_DIR/install.sh"
#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/AMDL"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR"
cp -r "$SCRIPT_DIR/"* "$INSTALL_DIR/"
rm -f "$INSTALL_DIR/install.sh" "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/AMDL"

if [ -d "$INSTALL_DIR/internal" ]; then
    find "$INSTALL_DIR/internal" -maxdepth 2 -type f ! -name "*.*" -exec chmod +x {} +
fi

ln -sf "$INSTALL_DIR/AMDL" "$BIN_DIR/amdl"

cat << DESKTOP > "$DESKTOP_DIR/amdl.desktop"
[Desktop Entry]
Type=Application
Name=AMDL
Comment=Apple Music Downloader GUI
Exec=$INSTALL_DIR/AMDL
Path=$INSTALL_DIR
Terminal=false
Categories=AudioVideo;Audio;
DESKTOP

chmod +x "$DESKTOP_DIR/amdl.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo "AMDL установлен в $INSTALL_DIR"
echo "Музыка будет сохраняться в: $(xdg-user-dir MUSIC 2>/dev/null || echo "$HOME/Music")/AMDL_music"
EOF

# 3. Скрипт удаления
cat << 'EOF' > "$PKG_DIR/uninstall.sh"
#!/usr/bin/env bash
set -euo pipefail
rm -rf "$HOME/.local/share/AMDL" "$HOME/.local/bin/amdl" "$HOME/.local/share/applications/amdl.desktop"
echo "AMDL удалён."
EOF

chmod +x "$PKG_DIR/install.sh" "$PKG_DIR/uninstall.sh"

# 4. Упаковка в дистрибутив .tar.gz
tar -czf "installer_out_linux/${APP_NAME}-${VERSION}-linux-x86_64.tar.gz" -C release_linux "${APP_NAME}-${VERSION}-linux-x86_64"
echo "Готово: installer_out_linux/${APP_NAME}-${VERSION}-linux-x86_64.tar.gz"