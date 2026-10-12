@echo off
rem Optional: build a standalone folder (no Python needed on the target PC).
rem Put ffmpeg.exe next to LowClip.exe afterwards.
pip install pyinstaller pystray Pillow
pyinstaller --noconsole --onedir --name LowClip lowclip.pyw
echo Done. Output is in dist\LowClip
