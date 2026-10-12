import copy
import json
import os
import tempfile
from pathlib import Path

APPDATA = Path(os.environ.get("APPDATA", str(Path.home()))) / "LowClip"
CONFIG_PATH = APPDATA / "config.json"
LOG_PATH = APPDATA / "ffmpeg.log"

DEFAULTS = {
    "ffmpeg_path": "ffmpeg",          # "ffmpeg" = look next to the app, then PATH
    "source": {"type": "monitor", "monitor": 0, "window_title": ""},
    "fps": 60,
    "bitrate_mbps": 20,
    "output_height": 0,               # 0 = native (cheapest). Scaling costs some CPU.
    "encoder": "auto",
    "draw_mouse": True,
    "desktop_audio": True,            # record everything you hear (WASAPI loopback)
    "desktop_audio_device": "",       # "" = default playback device
    "audio_devices": [],              # extra inputs, e.g. microphones (dshow names)
    "mix_audio": True,                # False = one audio track per device
    "audio_bitrate_kbps": 160,
    "clip_seconds": 30,
    "buffer_seconds": 60,
    "segment_seconds": 2,
    "clips_dir": str(Path.home() / "Videos" / "LowClip"),
    "buffer_dir": str(Path(tempfile.gettempdir()) / "lowclip_buffer"),
    "hotkey": "ctrl+alt+f9",
    "play_sound": True,
    "notify": True,
    "start_with_windows": False,
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    try:
        data = json.loads(CONFIG_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    return _merge(DEFAULTS, data)


def save(cfg):
    APPDATA.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), "utf-8")
    os.replace(tmp, CONFIG_PATH)


def mtime():
    try:
        return CONFIG_PATH.stat().st_mtime
    except OSError:
        return 0.0
