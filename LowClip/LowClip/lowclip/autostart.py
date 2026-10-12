import subprocess
import sys
import winreg
from pathlib import Path

from . import devices

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "LowClip"


def launch_cmd(extra=None):
    extra = extra or []
    if getattr(sys, "frozen", False):
        return [sys.executable] + extra
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    py = str(pyw if pyw.exists() else exe)
    return [py, str(devices.app_dir() / "lowclip.pyw")] + extra


def set_enabled(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(launch_cmd()))
        else:
            try:
                winreg.DeleteValue(k, NAME)
            except FileNotFoundError:
                pass
