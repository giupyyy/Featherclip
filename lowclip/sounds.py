"""Short confirmation sounds, generated in memory and played through the normal Windows audio output."""
import io
import math
import struct
import wave

_cache = {}

PATTERNS = {
    "ok": [(880, 90), (1320, 120)],   # two rising tones = clip saved
    "fail": [(300, 280)],             # one low tone = something went wrong
}


def _wav(pattern, vol=0.35, rate=44100):
    frames = bytearray()
    for freq, ms in pattern:
        n = int(rate * ms / 1000)
        for i in range(n):
            env = min(1.0, i / (rate * 0.008), (n - i) / (rate * 0.02))  # fade in/out, no clicks
            frames += struct.pack("<h", int(32767 * vol * env * math.sin(2 * math.pi * freq * i / rate)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def play(kind="ok"):
    """Blocks for ~0.2 s, so call it from a worker thread."""
    import winsound
    if kind not in _cache:
        _cache[kind] = _wav(PATTERNS[kind])
    try:
        winsound.PlaySound(_cache[kind], winsound.SND_MEMORY)  # SND_MEMORY can't be async
    except Exception:
        try:
            winsound.MessageBeep()
        except Exception:
            pass
