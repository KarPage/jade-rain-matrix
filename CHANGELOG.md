# Changelog

## 0.2.0 - 2026-11-07

- Live-preview-first settings: four modes, words, logo drag/drop, color and motion controls, and a collapsed Advanced section.
- Explicit Save with per-mode drafts, validated atomic mode saves, immediate reset feedback, and safe content-addressed logo uploads.
- One-tap rain-columns bar icon (13×14 in a 22 px slot); focus an existing settings window instead of opening another.
- Chromeless Chromium app window with a separate local profile; float and center on Lua Hyprland at 85% of the monitor, capped at 1400×1000 logical pixels.
- Preserve Matrix naming, legacy config compatibility, loopback/token/Host/Origin protections; add CSP and no-referrer headers.
- Clearing mode words or custom colors now clears inherited values rather than restoring them on reload.
- Actual-screen silent loop plus one original empty-workspace still, with Kar Page words and the logo unchanged. Compact animated WebP replaces the old generated screenshot set.
- Package, manifest and documentation now consistently use 0.2.0. The earlier commit title “1.0” was a label, not the package version; the previous package was 0.1.0. No public history or tags are rewritten.

## 0.1.0 - 2026-11-07

- First release of Jade Rain Matrix.
- Theme accent drives the head, body, tail, and glow. A hex override is optional.
- Words file, optional PNG logo traced from alpha (or luminance when the PNG has no transparency), and `logo_size` / `word_scale`.
- Local mp4 loop plus a still, set with `omarchy-theme-bg-set`. Live/still toggle. Opt-in `theme-set` hook.
- Presets: `full` (2880×1800, 640 frames), `laptop`, and `draft`.
- `jade-rain source` reads a local `.txt`, `.md`, or `.epub` into `~/.config/jade-rain/source.txt`. PDF uses optional `pdftotext`. `text_mode` and `text_density` control it. The default mode is `off`.
- The `~/.local/bin/jade-rain` link resolves the checkout with `readlink -f`.
- Source phrases repeat down the column at the brighter steady color, so mix and replace stay readable at the default density.
- Named profiles in `config.toml`, with per-mode colors, phrases, logo, glyph set, density, and speed. `jade-rain edit` opens a local editor. `live`, `still`, `light`, and `screensaver` each keep their own settings.
- Opt-in screensaver hook for Omarchy’s idle launcher. mpv plays the loop; any key or click quits.
- The editor is square, monospace, and jade. The preview fills its pane and updates as settings change. A one-glyph bar widget opens it.
- The user-facing name is Jade Rain Matrix. `jade-rain-matrix` is the command. `jade-rain` still runs it. Config is read from `~/.config/jade-rain-matrix`, or from `~/.config/jade-rain` when the new directory has no files. The old directory is never deleted.
- The editor accepts only a `127.0.0.1` or `localhost` Host for its own port, and only a matching Origin when a browser sends one.
- `./install.sh` does not change the Omarchy bar. `./install.sh --bar` asks first. `./install.sh --bar --yes` adds the glyph without a prompt.
