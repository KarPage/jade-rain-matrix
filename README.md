Inspired by and based on [bjarneo's Omarchy Matrix theme](https://github.com/bjarneo/omarchy-matrix-theme). Credit: bjarneo (@iamdothash).

That repository has no license. Jade Rain Matrix is original work: none of its files, video, images, or code are included here.

# Jade Rain Matrix

Calm digital rain for an Omarchy desktop. Jade Rain Matrix renders a seamless loop on your machine, in the colors of the active theme, and can set it with `omarchy-theme-bg-set`. Nothing is uploaded.

## Screenshots

Generated frames, not a photo of a desktop. Live and still use the jade field. Light uses dark ink on a paper field. Screensaver uses the matrix green and is not set as the wallpaper.

![Live](screenshots/mode-live.png)

![Still](screenshots/mode-still.png)

![Light](screenshots/mode-light.png)

![Screensaver](screenshots/mode-screensaver.png)

## Install

Omarchy already includes `ffmpeg`, `noto-fonts-cjk`, and `python-gobject`. It does not include NumPy or Pillow. Those two stay, because a pure-Python frame is too slow for this rain. Python 3.11 or newer.

```bash
omarchy pkg add python-numpy python-pillow
./install.sh
```

`install.sh` links `jade-rain-matrix` and the `jade-rain` alias into `~/.local/bin`. On a new machine it creates `~/.config/jade-rain-matrix/config.toml` and `words.txt`. If `~/.config/jade-rain` already has your files and the new directory does not, the install keeps using the old directory. It does not copy it and it does not delete it.

Rendering is a separate step. `./install.sh --hook` also enables the theme-change hook.

The Omarchy bar is not changed. To add the one jade glyph, confirm it:

```bash
./install.sh --bar
./install.sh --bar --yes
```

`--bar` alone asks in a terminal. `--bar --yes` is the non-interactive form. Either way the glyph is `io.github.karpage.jade-rain` in the left section. The plugin id is unchanged so an older bar entry still points at this checkout.

Add a key yourself in `~/.config/hypr/bindings.lua` if you want one. Super+Ctrl+Space is already the background switcher.

```lua
o.bind("SUPER + CTRL + ALT + SPACE", "Jade Rain Matrix", "jade-rain-matrix toggle")
```

`jade-rain` accepts the same subcommands as `jade-rain-matrix`.

## Usage

```bash
jade-rain-matrix render
jade-rain-matrix render --preset laptop
jade-rain-matrix render --preset draft
jade-rain-matrix toggle
jade-rain-matrix live
jade-rain-matrix still
```

| Preset | Size | Rate | Frames | Loop |
| --- | --- | --- | --- | --- |
| `full` (default) | 2880×1800 | 24 fps | 640 | 26.67 s |
| `laptop` | 1920×1200 | 24 fps | 360 | 15 s |
| `draft` | 960×600 | 12 fps | 72 | 6 s |

Live output is `~/.config/omarchy/backgrounds/<theme>/jade-rain.mp4` and `jade-rain.webp`. The loop stores frames 0 through N−1. The next frame matches frame 0.

### Edit

```bash
jade-rain-matrix edit
```

The editor is a page on `127.0.0.1`, opened from that command, from the Jade Rain Matrix item in the application menu, or from the bar glyph after you add it. The page uses the Python standard library and the NumPy and Pillow the renderer already needs. It does not fetch fonts, scripts, or the credit links. A token in the address is required. The server accepts only a `127.0.0.1` or `localhost` Host for its own port, and only a matching Origin when one is sent. Ctrl+S saves. Esc closes About, then the window. Keys 1–4 switch mode when you are not typing in a text field. The preview fills the right side and redraws as the fields change.

### Modes

`mode` in the config is `live`, `still`, `light`, or `screensaver`.

| Mode | What render writes |
| --- | --- |
| `live` | `jade-rain.mp4` and `jade-rain.webp`, then sets the wallpaper |
| `still` | the webp only, and sets it |
| `light` | `jade-rain-light.mp4` and its still. The field stays light. |
| `screensaver` | `jade-rain-screensaver.mp4`. It is not set as the desktop background. |

`toggle`, `live`, and `still` switch the original pair. They do not change `mode` in the config.

```bash
jade-rain-matrix screensaver --enable
jade-rain-matrix screensaver --dry-run
jade-rain-matrix screensaver --disable
```

`--enable` writes `omarchy-launch-screensaver` under `~/.local/bin` and `~/.local/share/omarchy/bin`, and only when Jade Rain Matrix does not find a different file there. mpv plays it fullscreen. Any key, click, or scroll quits. Moving the pointer does not. If the shell calls the system binary by its absolute path, this hook is not the one that runs.

```bash
jade-rain-matrix hook enable
jade-rain-matrix hook disable
jade-rain-matrix hook status
```

The theme hook returns at once. The render continues in the background.

### Source

```bash
jade-rain-matrix source ~/notes.md
jade-rain-matrix source book.epub
jade-rain-matrix source book.pdf
jade-rain-matrix render
```

`.txt` and `.md` are read directly. `.epub` is unzipped locally. `.pdf` needs `pdftotext`. A missing tool prints `omarchy pkg add poppler` and stops. The file has to be 32 MB or smaller. Text is stored in the config directory as `source.txt` and stays on this machine. `text_mode` defaults to `off`, which ignores that file. `mix` adds source phrases beside `words.txt`. `replace` uses the source phrases instead. `jade-rain-matrix source` sets `text_mode` to `mix` when it was `off`.

## Config

The file in use is `~/.config/jade-rain-matrix/config.toml`, or `~/.config/jade-rain/config.toml` when the new directory has no config, words, or source file. Creating the new directory and putting a `config.toml` there switches to it. The old directory is left in place.

Runtime state (the live/still toggle, render lock, and output list) stays in `~/.local/state/jade-rain`.

```toml
active = "jade"
mode = "live"

[profiles.jade]
color_preset = "theme"   # theme, jade, matrix, ink, paper
primary = ""
highlight = ""
background = ""
logo = "/absolute/path/mark.png"
logo_size = 250
logo_opacity = 0.33
logo_style = "watermark"  # watermark or sprite
word_scale = 0.86
phrases = ""
mix = 0.32
density = 1.0
speed = 1                 # 1 to 4 cycles in the same loop
glyph_set = "katakana"    # katakana, latin, digits, custom
glyphs = ""
text_mode = "off"
text_density = 0.35

[profiles.jade.modes.light]
color_preset = "paper"
density = 0.65
speed = 1
```

`logo_size` is the near outline’s height in pixels on an 1800 px frame. The far outline is 84% of that, so 250 becomes 210. `word_scale` `0.86` is about 14% smaller than the earlier `1.0`.

`words.txt` is one phrase per line, at most 24 phrases. A line of two words is a name. An empty file is pure rain. `glyph_set = "custom"` uses `glyphs`, up to 64 characters. A logo may be PNG or SVG. SVG is rasterized with `rsvg-convert` or ImageMagick when one of those is installed, and cached under the state directory.

An older flat file, with `accent` and `text_mode` at the top, still loads. `accent` empty follows the theme.

`jade-rain-matrix paths` prints the theme, files, and hook path. `jade-rain-matrix about` prints the credit.

## Uninstall

```bash
./uninstall.sh
./uninstall.sh --purge
```

This removes the `jade-rain-matrix` and `jade-rain` links when they point at this checkout, the theme hook when it carries the Jade Rain Matrix marker, the menu entry, the screensaver launcher when it carries its marker, `source.txt` in the new config directory, and recorded `jade-rain.mp4`, `jade-rain.webp`, `jade-rain.png`, light, and screensaver files under `omarchy/backgrounds`. Edited config and words in `~/.config/jade-rain-matrix` stay. `--purge` deletes that new directory. `~/.config/jade-rain` is never deleted. A second run is safe. `./uninstall.sh --yes` also asks Omarchy to disable the plugin. Without `--yes`, uninstall does not call `omarchy`.

## License

MIT. Copyright 2026 KarPage. Version 0.1.0.

[bjarneo/omarchy-matrix-theme](https://github.com/bjarneo/omarchy-matrix-theme) publishes no license (there is no `LICENSE` file, and the GitHub license field is empty). Jade Rain Matrix does not include that repository’s files, video, images, or code. The credit above is the notice.

Glyphs are drawn with Noto Sans CJK from the system package `noto-fonts-cjk`. That font is under the SIL Open Font License and is not bundled here. `assets/kp-logo-white.png` is the Kar Page mark shipped with this project.
