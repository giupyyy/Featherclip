import ctypes
import os
import subprocess
import sys
import threading
import time

from . import autostart, config, hotkey, recorder


def _icon_image(color):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
    return img


def _single_instance():
    h = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\LowClipDaemon")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ALREADY_EXISTS
        return None
    return h


class App:
    def __init__(self):
        self.cfg = config.load()
        self.rec = recorder.Recorder()
        self.hk = None
        self.paused = False
        self.stop_evt = threading.Event()
        self.last_mtime = config.mtime()
        self.fail_count = 0
        self.gave_up = False
        self.icon = None

    # ---- helpers
    def notify(self, msg):
        if self.icon and self.cfg.get("notify", True):
            try:
                self.icon.notify(msg, "LowClip")
            except Exception:
                pass

    def update_icon(self):
        if self.icon:
            self.icon.icon = _icon_image("#888888" if self.paused else "#e5484d")

    # ---- core actions
    def apply(self):
        self.cfg = config.load()
        self.last_mtime = config.mtime()
        self.fail_count = 0
        self.gave_up = False
        if self.hk:
            self.hk.stop()
        self.hk = hotkey.HotkeyListener(self.cfg["hotkey"], self.clip)
        if not self.hk.start():
            self.notify(f"Hotkey problem: {self.hk.error}")
        if self.paused:
            self.rec.stop()
        else:
            err = self.rec.start(self.cfg)
            if err:
                self.notify(f"Could not start ffmpeg: {err}")
                self.gave_up = True
        self.update_icon()

    def clip(self):
        threading.Thread(target=self._clip, daemon=True).start()

    def _clip(self):
        out = self.rec.save_clip()
        if out:
            if self.cfg["play_sound"]:
                import winsound
                winsound.Beep(1000, 90)
            self.notify(f"Saved {out.name}")
        else:
            self.notify("Clip failed (see ffmpeg.log)")

    def watch(self):
        self.apply()
        while not self.stop_evt.wait(3):
            m = config.mtime()
            if m != self.last_mtime:
                self.apply()
                continue
            if self.paused or self.gave_up or self.rec.running():
                continue
            # ffmpeg died (display change, driver reset, bad settings...)
            if time.time() - self.rec.started_at < 10:
                self.fail_count += 1
            else:
                self.fail_count = 0
            if self.fail_count >= 3:
                self.gave_up = True
                self.notify("Recording keeps failing. Check ffmpeg.log in %APPDATA%\\LowClip")
                continue
            self.rec.start(self.cfg)

    # ---- tray menu
    def toggle_pause(self, icon=None, item=None):
        self.paused = not self.paused
        self.gave_up = False
        self.fail_count = 0
        if self.paused:
            self.rec.stop()
        else:
            self.rec.start(self.cfg)
        self.update_icon()

    def open_settings(self, icon=None, item=None):
        subprocess.Popen(autostart.launch_cmd(["settings"]), creationflags=0x08000000)

    def open_clips(self, icon=None, item=None):
        os.makedirs(self.cfg["clips_dir"], exist_ok=True)
        os.startfile(self.cfg["clips_dir"])

    def open_log(self, icon=None, item=None):
        if config.LOG_PATH.exists():
            os.startfile(str(config.LOG_PATH))

    def quit(self, icon=None, item=None):
        self.stop_evt.set()
        if self.hk:
            self.hk.stop()
        self.rec.stop()
        self.icon.stop()

    def run(self):
        import pystray
        M, I = pystray.Menu, pystray.MenuItem
        menu = M(
            I("Save clip now", lambda i, it: self.clip()),
            I("Pause buffer", self.toggle_pause, checked=lambda it: self.paused),
            I("Open clips folder", self.open_clips),
            I("Settings…", self.open_settings, default=True),
            I("View ffmpeg log", self.open_log),
            I("Quit", self.quit),
        )
        self.icon = pystray.Icon("LowClip", _icon_image("#e5484d"), "LowClip", menu)
        self.icon.run(setup=lambda icon: (setattr(icon, "visible", True),
                                          threading.Thread(target=self.watch, daemon=True).start()))


def main():
    args = sys.argv[1:]
    if args[:1] == ["settings"]:
        from .settings_ui import run
        run()
        return
    mutex = _single_instance()
    if mutex is None:
        return
    App().run()
