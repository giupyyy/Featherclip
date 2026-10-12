# LowClip

A tiny background replay-buffer clipper for Windows. No overlay, no injected hooks, no bloat.

**How it stays light:** the app itself does almost nothing. It launches one `ffmpeg` process that
grabs the screen via DXGI Desktop Duplication (`ddagrab`), encodes on your GPU (NVENC / AMF / QuickSync),
and writes 2-second segments into a small rolling folder. When you hit the hotkey, the last N seconds of
segments are stitched into an `.mp4` with `-c copy` (no re-encode, no hitch). The tray process idles at ~0% CPU.
The settings window is a separate process that only exists while it's open.

## Setup
1. Install Python 3.10+ (tick "Add to PATH").
2. Get an ffmpeg **full/essentials build 6.1 or newer** for Windows (e.g. gyan.dev or BtbN builds).
   Put `ffmpeg.exe` next to `lowclip.pyw` (or anywhere on PATH).
3. `pip install -r requirements.txt`
4. Double-click `lowclip.pyw` (or `pythonw lowclip.pyw`). A red dot appears in the tray.
5. Click the tray icon → **Settings…** to pick monitor/window, audio, folders, hotkey. Save.
6. Default hotkey: `Ctrl+Alt+F9`. Clips go to `Videos\LowClip`.

Optional standalone build: run `build.bat`.

## Desktop audio
ffmpeg has no built-in WASAPI loopback, so audio uses DirectShow devices. Microphones show up automatically.
For game/desktop sound enable **Stereo Mix** (Sound settings → Recording → show disabled devices), or install a
free loopback device such as `virtual-audio-capturer` (screen-capture-recorder) or VB-Cable.

## Notes
- Clips are `clip_seconds` up to `clip_seconds + segment_seconds` long (cut points are keyframes).
- Window capture uses `gdigrab` (CPU) and may not see exclusive-fullscreen games. Prefer monitor capture.
- Monitor index follows ffmpeg's `output_idx`; if the wrong screen is captured, try another index.
- Logs: `%APPDATA%\LowClip\ffmpeg.log`. Config: `%APPDATA%\LowClip\config.json`.
- Put `buffer_dir` on a RAM disk or a non-system SSD if you want zero disk writes on your main drive.

## Roadmap ideas
Native WASAPI loopback (per-app audio), per-game profiles, auto-pause when no game is running, Rust rewrite of the tray.
