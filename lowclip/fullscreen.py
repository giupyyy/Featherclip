"""Detects whether the app in the foreground is a fullscreen app (a game) and on which monitor."""
import ctypes
import os
from ctypes import wintypes

from . import devices

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]

SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
WS_CAPTION = 0x00C00000


def make_dpi_aware():
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def covers(win, mon):
    return (win[0] <= mon[0] and win[1] <= mon[1] and win[2] >= mon[2] and win[3] >= mon[3])


def _proc_name(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        n = wintypes.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def fullscreen_monitor(ignore):
    """Index (same order as devices.list_monitors) of the monitor completely covered by the
    foreground app, or None if the foreground app is not a fullscreen app."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    if cls.value in SHELL_CLASSES:
        return None
    if user32.GetWindowLongW(hwnd, -16) & WS_CAPTION:  # has a title bar -> normal window
        return None
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    hmon = user32.MonitorFromWindow(hwnd, 2)  # nearest monitor
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not hmon or not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    m = mi.rcMonitor
    if not covers((r.left, r.top, r.right, r.bottom), (m.left, m.top, m.right, m.bottom)):
        return None
    if _proc_name(hwnd) in ignore:
        return None
    for i, (w, h, left, top) in enumerate(devices.list_monitors()):
        if (left, top) == (m.left, m.top):
            return i
    return None
