#!/usr/bin/env bash
# Install, toggle, and uninstall against a fake home. No desktop session.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

export HOME="$tmp/home"
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_STATE_HOME="$HOME/.local/state"
export PATH="$HOME/.local/bin:$tmp/bin:$PATH"
mkdir -p "$HOME" "$tmp/bin" "$XDG_STATE_HOME/omarchy/current/theme"
omarchy_log="$tmp/omarchy.log"
: > "$omarchy_log"
cat > "$tmp/bin/omarchy" <<EOF
#!/bin/bash
printf '%s\n' "\$*" >> "$omarchy_log"
EOF
chmod +x "$tmp/bin/omarchy"

printf 'tokyo-night\n' > "$XDG_STATE_HOME/omarchy/current/theme.name"
cat > "$XDG_STATE_HOME/omarchy/current/theme/colors.toml" <<'EOF'
accent = "#7aa2f7"
darker_background = "#0e0e14"
background = "#1a1b26"
EOF

bg_log="$tmp/bg.log"
cat > "$tmp/bin/omarchy-theme-bg-set" <<EOF
#!/bin/bash
printf '%s\n' "\$1" >> "$bg_log"
EOF
chmod +x "$tmp/bin/omarchy-theme-bg-set"

"$ROOT/install.sh"
test -L "$HOME/.local/bin/jade-rain"
test -L "$HOME/.local/bin/jade-rain-matrix"
test -f "$XDG_CONFIG_HOME/jade-rain-matrix/config.toml"
test -f "$XDG_CONFIG_HOME/jade-rain-matrix/words.txt"
test ! -e "$XDG_CONFIG_HOME/jade-rain"
grep -q 'logo_size = 250' "$XDG_CONFIG_HOME/jade-rain-matrix/config.toml"
grep -q 'word_scale = 0.86' "$XDG_CONFIG_HOME/jade-rain-matrix/config.toml"
grep -q 'text_mode = "off"' "$XDG_CONFIG_HOME/jade-rain-matrix/config.toml"
grep -q 'Kar Page' "$XDG_CONFIG_HOME/jade-rain-matrix/words.txt"
test -L "$XDG_CONFIG_HOME/omarchy/plugins/io.github.karpage.jade-rain"
test ! -s "$omarchy_log"

# The install link must resolve the package from another directory, with no PYTHONPATH.
mkdir -p "$tmp/elsewhere"
ln -s "$ROOT/bin/jade-rain" "$tmp/elsewhere/jade-rain"
( cd / && env -u PYTHONPATH "$HOME/.local/bin/jade-rain" --version ) | grep -q 'jade-rain'
( cd / && env -u PYTHONPATH "$HOME/.local/bin/jade-rain-matrix" --version ) | grep -q 'jade-rain-matrix'
( cd "$tmp/elsewhere" && env -u PYTHONPATH ./jade-rain --version ) | grep -q 'jade-rain'
test ! -f "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/jade-rain"

# Second install leaves the config alone.
printf '\n# edited\n' >> "$XDG_CONFIG_HOME/jade-rain-matrix/words.txt"
"$ROOT/install.sh"
grep -q 'edited' "$XDG_CONFIG_HOME/jade-rain-matrix/words.txt"
test ! -s "$omarchy_log"

"$HOME/.local/bin/jade-rain" hook enable
test -f "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/jade-rain"
grep -q 'jade-rain-hook v1' "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/jade-rain"
bash -n "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/jade-rain"
"$HOME/.local/bin/jade-rain" hook status | grep -q enabled

folder="$XDG_CONFIG_HOME/omarchy/backgrounds/tokyo-night"
mkdir -p "$folder"
printf 'video\n' > "$folder/jade-rain.mp4"
printf 'still\n' > "$folder/jade-rain.webp"
mkdir -p "$XDG_STATE_HOME/jade-rain"
printf '%s\n%s\n' "$folder/jade-rain.mp4" "$folder/jade-rain.webp" > "$XDG_STATE_HOME/jade-rain/outputs"

"$HOME/.local/bin/jade-rain" toggle
grep -q 'jade-rain.webp' "$bg_log"
"$HOME/.local/bin/jade-rain" toggle
grep -q 'jade-rain.mp4' "$bg_log"
"$HOME/.local/bin/jade-rain" live
test "$(tail -n 1 "$bg_log")" = "$folder/jade-rain.mp4"

# Missing wallpaper fails without calling the setter for a new path.
rm -f "$folder/jade-rain.mp4" "$folder/jade-rain.webp"
if "$HOME/.local/bin/jade-rain" still; then
  echo "still should fail when the file is missing" >&2
  exit 1
fi

# Restore files so uninstall has something to delete, then keep the edited words.
printf 'video\n' > "$folder/jade-rain.mp4"
printf 'still\n' > "$folder/jade-rain.webp"
printf 'local book\n' > "$XDG_CONFIG_HOME/jade-rain-matrix/source.txt"
"$ROOT/uninstall.sh"
test ! -e "$XDG_CONFIG_HOME/jade-rain-matrix/source.txt"
test ! -e "$HOME/.local/bin/jade-rain"
test ! -e "$HOME/.local/bin/jade-rain-matrix"
test ! -e "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/jade-rain"
test ! -e "$XDG_CONFIG_HOME/omarchy/plugins/io.github.karpage.jade-rain"
test ! -e "$folder/jade-rain.mp4"
test ! -e "$folder/jade-rain.webp"
test -f "$XDG_CONFIG_HOME/jade-rain-matrix/words.txt"
grep -q 'edited' "$XDG_CONFIG_HOME/jade-rain-matrix/words.txt"
test ! -s "$omarchy_log"

"$ROOT/uninstall.sh" --purge
test ! -e "$XDG_CONFIG_HOME/jade-rain-matrix"

# A fresh install's unmodified config is removed without --purge.
"$ROOT/install.sh" --hook
test -f "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/jade-rain"
"$ROOT/uninstall.sh"
test ! -e "$XDG_CONFIG_HOME/jade-rain-matrix/config.toml"
test ! -e "$XDG_CONFIG_HOME/jade-rain-matrix/words.txt"
test ! -e "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/jade-rain"
test ! -e "$HOME/.local/bin/jade-rain"
test ! -e "$HOME/.local/bin/jade-rain-matrix"

# An older config is used as-is and survives uninstall, including --purge.
mkdir -p "$XDG_CONFIG_HOME/jade-rain"
printf 'logo = "/keep.png"\n' > "$XDG_CONFIG_HOME/jade-rain/config.toml"
printf 'keep-me\n' > "$XDG_CONFIG_HOME/jade-rain/words.txt"
"$ROOT/install.sh"
test ! -e "$XDG_CONFIG_HOME/jade-rain-matrix"
grep -q '/keep.png' "$XDG_CONFIG_HOME/jade-rain/config.toml"
grep -q 'keep-me' "$XDG_CONFIG_HOME/jade-rain/words.txt"
"$ROOT/uninstall.sh" --purge
grep -q '/keep.png' "$XDG_CONFIG_HOME/jade-rain/config.toml"
grep -q 'keep-me' "$XDG_CONFIG_HOME/jade-rain/words.txt"
test ! -e "$HOME/.local/bin/jade-rain"

# The bar changes only with an explicit --bar --yes.
: > "$omarchy_log"
"$ROOT/install.sh" --bar </dev/null
test ! -s "$omarchy_log"
"$ROOT/install.sh" --bar --yes
grep -q 'plugin enable io.github.karpage.jade-rain --yes' "$omarchy_log"
grep -q 'bar put io.github.karpage.jade-rain --section left --yes' "$omarchy_log"
"$ROOT/install.sh" --bar --yes
"$ROOT/uninstall.sh"
"$ROOT/uninstall.sh" --yes
test ! -e "$HOME/.local/bin/jade-rain-matrix"

echo "install/uninstall ok"
