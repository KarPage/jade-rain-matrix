#!/usr/bin/env bash
# Install Jade Rain for the current user. Does not render, and does not
# enable the theme-change hook unless --hook is passed. Never uses sudo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENABLE_HOOK=0
ENABLE_BAR=0
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    --hook) ENABLE_HOOK=1 ;;
    --bar) ENABLE_BAR=1 ;;
    --yes) ASSUME_YES=1 ;;
    *)
      echo "Usage: ./install.sh [--hook] [--bar] [--yes]" >&2
      exit 1
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required. Omarchy ships it; otherwise install the ffmpeg package." >&2
  exit 1
fi

if ! python3 - <<'PY'
import importlib.util
import sys
missing = [name for name in ("numpy", "PIL") if importlib.util.find_spec(name) is None]
if missing:
    sys.exit("missing python modules: " + " ".join(missing))
PY
then
  echo "Install the Python modules, then run ./install.sh again:" >&2
  echo "  omarchy pkg add python-numpy python-pillow" >&2
  exit 1
fi

font_ok=0
for font in \
  /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc \
  /usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc \
  /usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc \
  /usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc
do
  if [[ -f $font ]]; then
    font_ok=1
  fi
done
if [[ $font_ok -eq 0 ]] && command -v fc-match >/dev/null 2>&1; then
  matched="$(fc-match -f '%{file}' ':family=Noto Sans CJK JP' || true)"
  if [[ -f $matched ]]; then
    case "$matched" in
      *[Cc][Jj][Kk]*|*[Nn]oto*) font_ok=1 ;;
    esac
  fi
fi
if [[ $font_ok -eq 0 ]]; then
  echo "Noto Sans CJK is required for the katakana streams." >&2
  echo "  omarchy pkg add noto-fonts-cjk" >&2
  exit 1
fi

config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}"
new_config="$config_root/jade-rain-matrix"
old_config="$config_root/jade-rain"
# Read an existing ~/.config/jade-rain when the new directory has no files.
# Never delete the old directory, and do not create an empty twin beside it.
if [[ -f $new_config/config.toml || -f $new_config/words.txt || -f $new_config/source.txt ]]; then
  config_dir="$new_config"
elif [[ -f $old_config/config.toml || -f $old_config/words.txt || -f $old_config/source.txt ]]; then
  config_dir="$old_config"
else
  config_dir="$new_config"
fi
state_dir="$state_root/jade-rain"
bin_dir="${HOME}/.local/bin"
primary="$bin_dir/jade-rain-matrix"
link="$bin_dir/jade-rain"

mkdir -p "$bin_dir" "$config_dir" "$state_dir"
ln -sfn "$ROOT/bin/jade-rain-matrix" "$primary"
ln -sfn "$ROOT/bin/jade-rain" "$link"

logo="$ROOT/assets/kp-logo-white.png"
if [[ ! -f "$config_dir/config.toml" ]]; then
  cat > "$config_dir/config.toml" <<EOF
# Jade Rain Matrix. One file, named profiles. Colors follow the theme until you set them.
# full: 2880x1800. laptop: 1920x1200. draft: 960x600.

active = "jade"
mode = "live"

[profiles.jade]
preset = "full"
color_preset = "theme"
primary = ""
highlight = ""
background = ""
logo = "${logo}"
logo_size = 250
logo_opacity = 0.33
logo_style = "watermark"
word_scale = 0.86
text_mode = "off"
text_density = 0.35
mix = 0.32
density = 1.0
speed = 1
glyph_set = "katakana"
glyphs = ""
phrases = ""

[profiles.jade.modes.live]

[profiles.jade.modes.still]

[profiles.jade.modes.light]
color_preset = "paper"
primary = "#1b4d38"
highlight = "#0e2e22"
background = "#f3efe4"
density = 0.65
speed = 1
mix = 0.2

[profiles.jade.modes.screensaver]
color_preset = "matrix"
density = 0.85
speed = 1
EOF
  sha256sum "$config_dir/config.toml" | awk '{print $1}' > "$state_dir/installed-config.sha256"
fi

plugins="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins"
mkdir -p "$plugins"
plugin_link="$plugins/io.github.karpage.jade-rain"
if [[ -L $plugin_link || ! -e $plugin_link ]]; then
  ln -sfn "$ROOT" "$plugin_link"
else
  echo "left $plugin_link (it is not a Jade Rain Matrix link)"
fi
# The bar is untouched unless --bar is combined with --yes or an answered prompt.
place_bar=0
if [[ $ENABLE_BAR -eq 1 ]]; then
  if [[ $ASSUME_YES -eq 1 ]]; then
    place_bar=1
  elif [[ -t 0 ]]; then
    read -r -p "Add the Jade Rain Matrix glyph to the Omarchy bar? [y/N] " answer
    case "$answer" in
      y|Y|yes|YES) place_bar=1 ;;
    esac
  else
    echo "The Omarchy bar was not changed. Re-run ./install.sh --bar --yes to add the glyph."
  fi
fi
if [[ $place_bar -eq 1 ]]; then
  if command -v omarchy >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
    timeout 8 omarchy plugin enable io.github.karpage.jade-rain --yes || true
    timeout 8 omarchy bar put io.github.karpage.jade-rain --section left --yes || true
  else
    echo "omarchy is not on PATH. The bar was not changed."
  fi
fi

apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$apps"
desktop="$apps/jade-rain.desktop"
JADE_ROOT="$ROOT" JADE_LINK="$primary" JADE_DESKTOP="$desktop" python3 - <<'PY'
import os
from pathlib import Path
text = Path(os.environ["JADE_ROOT"], "share/jade-rain.desktop").read_text(encoding="utf-8")
text = text.replace("Exec=jade-rain-matrix edit", "Exec=" + os.environ["JADE_LINK"] + " edit")
Path(os.environ["JADE_DESKTOP"]).write_text(text, encoding="utf-8")
PY

if [[ ! -f "$config_dir/words.txt" ]]; then
  cp "$ROOT/share/words.txt" "$config_dir/words.txt"
  sha256sum "$config_dir/words.txt" | awk '{print $1}' > "$state_dir/installed-words.sha256"
fi

if [[ $ENABLE_HOOK -eq 1 ]]; then
  "$link" hook enable
fi

cat <<EOF
Jade Rain Matrix is installed.
  command  $primary
  alias    $link
  config   $config_dir/config.toml
  words    $config_dir/words.txt

Render the loop (this is the slow step):
  jade-rain-matrix render
  jade-rain-matrix render --preset laptop

The theme-change hook is off until you opt in:
  jade-rain-matrix hook enable

Edit colors, phrases, and the logo in a local window:
  jade-rain-matrix edit

The Omarchy bar is left as it is unless you passed --bar and confirmed it:
  ./install.sh --bar --yes

Feed a local text into the rain (nothing is uploaded):
  jade-rain-matrix source book.epub

Screensaver (opt in; any key or click quits):
  jade-rain-matrix screensaver --enable

Suggested binding, in ~/.config/hypr/bindings.lua (not written for you):
  o.bind("SUPER + CTRL + ALT + SPACE", "Jade Rain Matrix", "jade-rain-matrix toggle")
EOF
if [[ $config_dir == "$old_config" ]]; then
  echo "Using the existing config at $old_config. It was not copied or deleted."
fi
