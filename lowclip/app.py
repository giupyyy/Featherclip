import copy
import ctypes
import os
import subprocess
import sys
import threading
import time

from . import autostart, config, fullscreen, hotkey, recorder


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
        self.lock = threading.RLock()
        self.game_monitor = None
        self.last_game_seen = 0.0
        self._icon_state = None

    # ---- helpers
    def is_game_mode(self):
        return self.cfg["source"]["type"] == "game"

    def notify(self, msg):
        if self.icon and self.cfg.get("notify", True):
            try:
                self.icon.notify(msg, "Featherclip")
            except Exception:
                pass

    def update_icon(self):
        """Red = recording, grey = paused or waiting for a game."""
        if not self.icon:
            return
        rec = (not self.paused) and self.rec.running()
        if rec == self._icon_state:
            return
        self._icon_state = rec
        self.icon.icon = _icon_image("#e5484d" if rec else "#888888")
        self.icon.title = "Featherclip - recording" if rec else (
            "Featherclip - paused" if self.paused else "Featherclip - waiting for a game")

    # ---- core actions
    def apply(self):
        with self.lock:
            self.cfg = config.load()
            self.last_mtime = config.mtime()
            self.fail_count = 0
            self.gave_up = False
            self.game_monitor = None
            if self.hk:
                self.hk.stop()
            self.hk = hotkey.HotkeyListener(self.cfg["hotkey"], self.clip)
            if not self.hk.start():
                self.notify(f"Hotkey problem: {self.hk.error}")
            if self.paused:
                self.rec.stop()
            elif self.is_game_mode():
                self.rec.stop()
                self.game_tick()
            else:
                err = self.rec.start(self.cfg)
                if err:
                    self.notify(f"Could not start ffmpeg: {err}")
                    self.gave_up = True
                elif self.rec.warning:
                    self.notify(self.rec.warning)
            self.update_icon()

    def clip(self):
        threading.Thread(target=self._clip, daemon=True).start()

    def _clip(self):
        if not self.rec.running():
            self.notify("Nothing to save: not recording right now")
            return
        out = self.rec.save_clip()
        if out:
            if self.cfg["play_sound"]:
                import winsound
                winsound.Beep(1000, 90)
            self.notify(f"Saved {out.name}")
        else:
            self.notify("Clip failed (see ffmpeg.log)")

    def game_tick(self):
        """Game mode: record while a fullscreen app is in front, stop shortly after it is gone."""
        with self.lock:
            idx = fullscreen.fullscreen_monitor(self.cfg.get("ignore_programs", []))
            now = time.time()
            if idx is not None:
                self.last_game_seen = now
                if idx != self.game_monitor:
                    self.fail_count = 0
                    self.gave_up = False
                need = (not self.rec.running()) or self.game_monitor != idx
                if need and not (self.gave_up and self.game_monitor == idx):
                    if self.game_monitor == idx and not self.rec.running():
                        if now - self.rec.started_at < 10:
                            self.fail_count += 1
                        else:
                            self.fail_count = 0
                        if self.fail_count >= 3:
                            self.gave_up = True
                            self.notify("Recording keeps failing. Check ffmpeg.log in %APPDATA%\\LowClip")
                            self.update_icon()
                            return
                    rcfg = copy.deepcopy(self.cfg)
                    rcfg["source"] = {"type": "monitor", "monitor": idx, "window_title": ""}
                    err = self.rec.start(rcfg)
                    self.game_monitor = idx
                    if err:
                        self.notify(f"Could not start ffmpeg: {err}")
                        self.gave_up = True
                    elif self.rec.warning:
                        self.notify(self.rec.warning)
            elif self.rec.running():
                if now - self.last_game_seen > int(self.cfg.get("game_linger_seconds", 30)):
                    self.rec.stop()
                    self.game_monitor = None
            self.update_icon()

    def watch(self):
        self.apply()
        while not self.stop_evt.wait(2 if self.is_game_mode() else 3):
            m = config.mtime()
            if m != self.last_mtime:
                self.apply()
                continue
            if self.paused:
                continue
            if self.is_game_mode():
                self.game_tick()
                continue
            if self.gave_up or self.rec.running():
                continue
            # ffmpeg died (display change, driver reset, bad settings...)
            if time.time() - self.rec.started_at < 10:
                self.fail_count += 1
            else:
                self.fail_count = 0
            if self.fail_count >= 3:
                self.gave_up = True
                self.notify("Recording keeps failing. Check ffmpeg.log in %APPDATA%\\LowClip")
                self.update_icon()
                continue
            self.rec.start(self.cfg)
            self.update_icon()

    # ---- tray menu
    def toggle_pause(self, icon=None, item=None):
        with self.lock:
            self.paused = not self.paused
            self.gave_up = False
            self.fail_count = 0
            if self.paused:
                self.rec.stop()
            elif self.is_game_mode():
                self.game_monitor = None
                self.game_tick()
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
        self.icon = pystray.Icon("Featherclip", _icon_image("#888888"), "Featherclip", menu)
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
    fullscreen.make_dpi_aware()
    App().run()
