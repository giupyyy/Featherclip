# Featherclip

A tiny background replay-buffer clipper for Windows. Press a hotkey and the last seconds of your screen
(plus game/desktop sound and microphone) are saved as an MP4. No overlay, no bloat, near-zero CPU.

## Download
1. Open **[Releases](../../releases/latest)** (right side of this page).
2. Download **Featherclip-Windows.zip** under *Assets* and unzip it anywhere.
3. Double-click **Featherclip.exe**. A red dot appears in the tray (bottom right, maybe behind the **^**).
4. Right-click the dot → **Settings…** to choose monitor, sound, hotkey and save folder.

Default hotkey: `Ctrl+Alt+F9`. Windows may show a blue "protected your PC" notice because the app is
unsigned: click **More info → Run anyway**.

## Features
- Screen capture on the GPU (NVENC / AMF / QuickSync), clips saved without re-encoding
- Choose monitor or window, FPS, bitrate, resolution
- Desktop sound (everything you hear) + optional microphones, mixed or on separate tracks
- Choose where clips are saved, clip length and buffer length
- Runs in the tray, optional autostart with Windows, can be paused

## How it works
The app starts one `ffmpeg` process that records 2-second segments into a rolling temp folder.
The hotkey joins the newest segments into an MP4 (`-c copy`). Desktop sound is captured with WASAPI loopback.
Logs and settings live in `%APPDATA%\LowClip`.

## Build it yourself
GitHub Actions builds the app automatically on every push to `main` (see `.github/workflows/build.yml`)
and publishes it under Releases.
