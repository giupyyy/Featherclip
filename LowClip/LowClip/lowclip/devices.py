import ctypes
import re
import shutil
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

NO_WINDOW = 0x08000000

ENCODER_PREFERENCE = ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def find_ffmpeg(cfg):
    p = cfg.get("ffmpeg_path") or "ffmpeg"
    if p.lower() in ("ffmpeg", "ffmpeg.exe"):
        local = app_dir() / "ffmpeg.exe"
        if local.exists():
            return str(local)
        return shutil.which("ffmpeg") or "ffmpeg"
    return p


def list_monitors():
    """Returns [(width, height, left, top)] in enumeration order."""
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
    mons = []
    proc_t = ctypes.WINFUNCTYPE(
        wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(hmon, hdc, rect, data):
        r = rect.contents
        mons.append((r.right - r.left, r.bottom - r.top, r.left, r.top))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, proc_t(cb), 0)
    return mons


def list_windows():
    user32 = ctypes.windll.user32
    titles = []
    proc_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                titles.append(buf.value)
        return True

    user32.EnumWindows(proc_t(cb), 0)
    return sorted(set(titles), key=str.lower)


def list_audio_devices(ffmpeg):
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, timeout=15, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return []
    text = (out.stderr or b"").decode("utf-8", errors="replace")
    names = []
    for line in text.splitlines():
        m = re.search(r'"([^"]+)"\s+\(audio\)', line)
        if m:
            names.append(m.group(1))
    if not names:  # older ffmpeg output format
        in_audio = False
        for line in text.splitlines():
            if "DirectShow audio devices" in line:
                in_audio = True
                continue
            if "DirectShow video devices" in line:
                in_audio = False
                continue
            if in_audio and "Alternative name" not in line:
                m = re.search(r'"([^"]+)"', line)
                if m:
                    names.append(m.group(1))
    seen, uniq = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def test_encoder(ffmpeg, enc):
    try:
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
             "color=black:s=640x360:r=30:d=0.3", "-frames:v", "3", "-c:v", enc,
             "-f", "null", "-"],
            capture_output=True, timeout=15, creationflags=NO_WINDOW)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect_encoders(ffmpeg):
    cands = ["h264_nvenc", "hevc_nvenc", "h264_amf", "hevc_amf",
             "h264_qsv", "hevc_qsv", "libx264"]
    return [e for e in cands if test_encoder(ffmpeg, e)]
