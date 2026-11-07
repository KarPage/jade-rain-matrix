#!/usr/bin/env bash
# Remove everything Jade Rain Matrix installed.
# Edited config and words are kept unless --purge is passed.
# ~/.config/jade-rain from an older install is never deleted.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PURGE=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --yes) ASSUME_YES=1 ;;
    *)
      echo "Usage: ./uninstall.sh [--purge] [--yes]" >&2
      exit 1
      ;;
  esac
done

config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}"
new_config="$config_root/jade-rain-matrix"
old_config="$config_root/jade-rain"
config_dir=""
if [[ -f $new_config/config.toml || -f $new_config/words.txt || -f $new_config/source.txt ]]; then
  config_dir="$new_config"
elif [[ -f $old_config/config.toml || -f $old_config/words.txt || -f $old_config/source.txt ]]; then
  config_dir="$old_config"
fi
state_dir="$state_root/jade-rain"
hook="$config_root/omarchy/hooks/theme-set.d/jade-rain"

remove_cli() {
  local link="${HOME}/.local/bin/$1"
  local target expected
  if [[ ! -L $link ]]; then
    return
  fi
  target="$(readlink -f "$link" || true)"
  for expected in "$ROOT/bin/jade-rain" "$ROOT/bin/jade-rain-matrix"; do
    if [[ $target == "$(readlink -f "$expected")" ]]; then
      rm -f "$link"
      echo "removed $link"
      return
    fi
  done
  echo "left $link (it does not point at this checkout)"
}
remove_cli jade-rain
remove_cli jade-rain-matrix

if [[ -f $hook ]] && grep -q "jade-rain-hook v1" "$hook"; then
  rm -f "$hook"
  echo "removed $hook"
fi

plugin_link="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/io.github.karpage.jade-rain"
if [[ -L $plugin_link ]]; then
  target="$(readlink -f "$plugin_link" || true)"
  expected="$(readlink -f "$ROOT")"
  if [[ $target == "$expected" ]]; then
    if [[ $ASSUME_YES -eq 1 ]] && command -v omarchy >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
      timeout 8 omarchy plugin disable io.github.karpage.jade-rain --yes || true
    fi
    rm -f "$plugin_link"
    echo "removed $plugin_link"
  fi
fi

desktop="${XDG_DATA_HOME:-$HOME/.local/share}/applications/jade-rain.desktop"
if [[ -f $desktop ]] && grep -q "jade-rain-desktop v1" "$desktop"; then
  rm -f "$desktop"
  echo "removed $desktop"
fi

for saver in \
  "$HOME/.local/bin/omarchy-launch-screensaver" \
  "$HOME/.local/share/omarchy/bin/omarchy-launch-screensaver"
do
  if [[ -f $saver ]] && grep -q "jade-rain-screensaver-hook v1" "$saver"; then
    rm -f "$saver"
    echo "removed $saver"
  fi
done

if [[ -f "$state_dir/outputs" ]]; then
  while IFS= read -r path || [[ -n $path ]]; do
    [[ -n $path ]] || continue
    base="$(basename "$path")"
    case "$base" in
      jade-rain.mp4|jade-rain.webp|jade-rain.png|jade-rain-light.mp4|jade-rain-light.webp|jade-rain-screensaver.mp4|jade-rain-screensaver.webp) ;;
      *) continue ;;
    esac
    case "$path" in
      *"/omarchy/backgrounds/"*) ;;
      *) continue ;;
    esac
    if [[ -f $path ]]; then
      rm -f -- "$path"
      echo "removed $path"
      rmdir "$(dirname "$path")" 2>/dev/null || true
    fi
  done < "$state_dir/outputs"
fi

remove_if_unchanged() {
  local file="$1"
  local hash_file="$2"
  if [[ $PURGE -eq 1 ]]; then
    rm -f "$file"
    return
  fi
  if [[ ! -f $file || ! -f $hash_file ]]; then
    return
  fi
  local now
  now="$(sha256sum "$file" | awk '{print $1}')"
  local then
  then="$(cat "$hash_file")"
  if [[ $now == "$then" ]]; then
    rm -f "$file"
    echo "removed unmodified $file"
  else
    echo "kept edited $file (uninstall.sh --purge removes it)"
  fi
}

if [[ -z $config_dir ]]; then
  :
elif [[ $config_dir == "$old_config" ]]; then
  echo "kept $old_config (an older config is never deleted)"
else
  remove_if_unchanged "$config_dir/config.toml" "$state_dir/installed-config.sha256"
  remove_if_unchanged "$config_dir/words.txt" "$state_dir/installed-words.sha256"
  if [[ -e "$config_dir/source.txt" || -L "$config_dir/source.txt" ]]; then
    rm -f -- "$config_dir/source.txt"
    echo "removed $config_dir/source.txt"
  fi
  if [[ $PURGE -eq 1 ]]; then
    rm -rf "$config_dir"
    echo "removed $config_dir"
  else
    rmdir "$config_dir" 2>/dev/null || true
  fi
fi

rm -rf "$state_dir"
echo "Jade Rain Matrix is uninstalled."
