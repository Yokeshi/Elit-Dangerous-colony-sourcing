#!/usr/bin/env bash
# Asztali indito ikon letrehozasa a Colony Sourcing GUI-hoz.
# Futtatas EGYSZER, abbol a mappabol, ahol a colony_gui.py van:
#     bash install_icon.sh
set -e

# a script sajat mappaja (itt vannak a .py fajlok)
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/colony_gui.py"

if [ ! -f "$APP" ]; then
  echo "HIBA: nem talalom a colony_gui.py-t itt: $DIR"
  echo "Tedd az install_icon.sh-t ugyanabba a mappaba, mint a colony_gui.py-t."
  exit 1
fi

# python3 teljes eleresi utja (megbizhatobb a .desktop fajlban)
PYTHON="$(command -v python3)"

# ikon: ha van icon.png a mappaban, azt hasznaljuk, kulonben egy stock ikont
if [ -f "$DIR/icon.png" ]; then
  ICON="$DIR/icon.png"
else
  ICON="input-gaming"
fi

DESKTOP_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=Colony Sourcing
GenericName=ED kolonizacios beszerzo
Comment=Hianyzo epitkezesi anyagok es legkozelebbi forrasaik
Exec=$PYTHON \"$APP\"
Path=$DIR
Icon=$ICON
Terminal=false
Categories=Game;Utility;"

# 1) Alkalmazas menube
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"
echo "$DESKTOP_CONTENT" > "$APPS/colony-sourcing.desktop"
chmod +x "$APPS/colony-sourcing.desktop"
update-desktop-database "$APPS" 2>/dev/null || true
echo "✓ Hozzaadva az alkalmazas menuhoz (keresd: Colony Sourcing)"

# 2) Asztalra (ha letezik a Desktop/Asztal mappa)
for DESK in "$HOME/Asztal" "$HOME/Desktop" "$(xdg-user-dir DESKTOP 2>/dev/null)"; do
  if [ -n "$DESK" ] && [ -d "$DESK" ]; then
    TARGET="$DESK/colony-sourcing.desktop"
    echo "$DESKTOP_CONTENT" > "$TARGET"
    chmod +x "$TARGET"
    # Cinnamon/GNOME: megbizhatova tesszuk, hogy ne kerdezzen ra
    gio set "$TARGET" metadata::trusted true 2>/dev/null || true
    echo "✓ Ikon az asztalon: $TARGET"
    break
  fi
done

echo
echo "Kesz! Ha az asztali ikon elso kattintasra megsem indul, kattints ra"
echo "jobb gombbal -> 'Inditas engedelyezese' / 'Allow Launching'."
