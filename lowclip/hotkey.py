import ctypes
import re
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000
MODS = {"alt": 1, "ctrl": 2, "control": 2, "shift": 4, "win": 8}
NAMED = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "pause": 0x13,
    "scrolllock": 0x91, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}


def parse(s):
    mods, vk = 0, None
    for part in s.lower().replace(" ", "").split("+"):
        if part in MODS:
            mods |= MODS[part]
        elif part in NAMED:
            vk = NAMED[part]
        elif re.fullmatch(r"f([1-9]|1\d|2[0-4])", part):
            vk = 0x6F + int(part[1:])
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        else:
            raise ValueError(f"Unknown key: {part!r}")
    if vk is None:
        raise ValueError("No main key in hotkey")
    return mods, vk


class HotkeyListener:
    def __init__(self, hotkey, callback):
        self.hotkey = hotkey
        self.callback = callback
        self.error = None
        self._t = None
        self._tid = None

    def start(self):
        self._ready = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        self._ready.wait(3)
        return self.error is None

    def _run(self):
        self._tid = kernel32.GetCurrentThreadId()
        try:
            mods, vk = parse(self.hotkey)
        except ValueError as e:
            self.error = str(e)
            self._ready.set()
            return
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # create the queue
        if not user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk):
            self.error = "RegisterHotKey failed (already used by another app?)"
            self._ready.set()
            return
        self._ready.set()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    self.callback()
                except Exception:
                    pass
        user32.UnregisterHotKey(None, 1)

    def stop(self):
        if self._t and self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._t.join(1)
