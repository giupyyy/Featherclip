import datetime
import math
import subprocess
import threading
import time
from pathlib import Path

from . import config, devices

NO_WINDOW = 0x08000000
BELOW_NORMAL = 0x00004000

_auto_cache = {}


def resolve_encoder(cfg):
    enc = cfg["encoder"]
    if enc != "auto":
        return enc
    ff = devices.find_ffmpeg(cfg)
    if ff not in _auto_cache:
        found = devices.detect_encoders(ff)
        pick = next((e for e in devices.ENCODER_PREFERENCE if e in found), "libx264")
        _auto_cache[ff] = pick
    return _auto_cache[ff]


def encoder_args(enc, mbps):
    b = f"{mbps}M"
    buf = f"{mbps * 2}M"
    if enc.endswith("_nvenc"):
        return ["-preset", "p4", "-rc", "cbr", "-b:v", b, "-maxrate", b, "-bufsize", buf]
    if enc.endswith("_amf"):
        return ["-quality", "speed", "-rc", "cbr", "-b:v", b, "-maxrate", b]
    if enc.endswith("_qsv"):
        return ["-preset", "veryfast", "-b:v", b, "-maxrate", b]
    return ["-preset", "veryfast", "-b:v", b, "-maxrate", b, "-bufsize", buf]


def build_cmd(cfg):
    ff = devices.find_ffmpeg(cfg)
    enc = resolve_encoder(cfg)
    fps = int(cfg["fps"])
    seg = int(cfg["segment_seconds"])
    height = int(cfg["output_height"] or 0)
    mouse = "1" if cfg["draw_mouse"] else "0"
    src = cfg["source"]

    cmd = [ff, "-hide_banner", "-loglevel", "warning", "-nostats"]
    vf = None
    if src["type"] == "window":
        cmd += ["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", mouse,
                "-i", "title=" + src["window_title"]]
        chain = (["scale=-2:%d" % height] if height else []) + ["format=nv12"]
        vf = ",".join(chain)
    else:
        grab = f"ddagrab=output_idx={int(src['monitor'])}:framerate={fps}:draw_mouse={mouse}"
        cmd += ["-f", "lavfi", "-i", grab]
        if not (enc.endswith("_nvenc") and not height):
            chain = ["hwdownload", "format=bgra"]
            if height:
                chain.append(f"scale=-2:{height}:flags=fast_bilinear")
            chain.append("format=nv12")
            vf = ",".join(chain)

    devs = [d for d in cfg["audio_devices"] if d]
    for d in devs:
        cmd += ["-thread_queue_size", "1024", "-use_wallclock_as_timestamps", "1",
                "-f", "dshow", "-audio_buffer_size", "50", "-i", "audio=" + d]

    maps = ["-map", "0:v"]
    if devs:
        fc = [f"[{i + 1}:a]aresample=async=1000[a{i}]" for i in range(len(devs))]
        if len(devs) > 1 and cfg["mix_audio"]:
            ins = "".join(f"[a{i}]" for i in range(len(devs)))
            fc.append(f"{ins}amix=inputs={len(devs)}:duration=longest:normalize=0[aout]")
            maps += ["-map", "[aout]"]
        else:
            for i in range(len(devs)):
                maps += ["-map", f"[a{i}]"]
        cmd += ["-filter_complex", ";".join(fc)]
    cmd += maps
    if vf:
        cmd += ["-vf", vf]

    cmd += ["-c:v", enc] + encoder_args(enc, int(cfg["bitrate_mbps"]))
    cmd += ["-force_key_frames", f"expr:gte(t,n_forced*{seg})"]
    if devs:
        cmd += ["-c:a", "aac", "-b:a", f"{int(cfg['audio_bitrate_kbps'])}k"]

    wrap = math.ceil(int(cfg["buffer_seconds"]) / seg) + 4
    cmd += ["-f", "segment", "-segment_time", str(seg), "-segment_wrap", str(wrap),
            "-segment_format", "mpegts", "-reset_timestamps", "1",
            str(Path(cfg["buffer_dir"]) / "seg_%03d.ts")]
    return cmd


class Recorder:
    def __init__(self):
        self.proc = None
        self.cfg = None
        self.started_at = 0.0
        self.lock = threading.Lock()

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, cfg):
        """Returns None on success, else an error string."""
        with self.lock:
            self._stop()
            self.cfg = cfg
            buf = Path(cfg["buffer_dir"])
            buf.mkdir(parents=True, exist_ok=True)
            for f in buf.glob("seg_*.ts"):
                try:
                    f.unlink()
                except OSError:
                    pass
            config.APPDATA.mkdir(parents=True, exist_ok=True)
            try:
                cmd = build_cmd(cfg)
                log = open(config.LOG_PATH, "wb")
                log.write((" ".join(cmd) + "\n\n").encode("utf-8", "replace"))
                log.flush()
                self.proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=log, creationflags=NO_WINDOW)
                log.close()
            except OSError as e:
                self.proc = None
                return str(e)
            self.started_at = time.time()
            return None

    def stop(self):
        with self.lock:
            self._stop()

    def _stop(self):
        p = self.proc
        self.proc = None
        if p and p.poll() is None:
            try:
                p.stdin.write(b"q\n")
                p.stdin.flush()
                p.wait(3)
            except Exception:
                p.kill()

    def save_clip(self):
        """Stitch the newest segments into an mp4 without re-encoding."""
        cfg = self.cfg
        if not cfg or not self.running():
            return None
        buf = Path(cfg["buffer_dir"])
        segs = []
        for p in buf.glob("seg_*.ts"):
            try:
                st = p.stat()
                if st.st_size > 0:
                    segs.append((st.st_mtime, p))
            except OSError:
                pass
        segs.sort()
        seg = int(cfg["segment_seconds"])
        need = math.ceil(int(cfg["clip_seconds"]) / seg) + 1
        chosen = [p for _, p in segs[-need:]]
        if not chosen:
            return None
        lst = buf / "clip_list.txt"
        lines = []
        for p in chosen:
            s = str(p).replace("\\", "/").replace("'", "'\\''")
            lines.append(f"file '{s}'")
        lst.write_text("\n".join(lines) + "\n", "utf-8")
        out_dir = Path(cfg["clips_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"Clip_{datetime.datetime.now():%Y-%m-%d_%H-%M-%S}.mp4"
        r = subprocess.run(
            [devices.find_ffmpeg(cfg), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", "-movflags", "+faststart", str(out)],
            capture_output=True, creationflags=NO_WINDOW | BELOW_NORMAL)
        return out if r.returncode == 0 and out.exists() else None
