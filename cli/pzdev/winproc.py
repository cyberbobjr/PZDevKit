"""Windows process helpers of pz-autotest: running games, game window, posted clicks, process tree kill, memory."""
from __future__ import annotations

import ctypes
import subprocess
import time

BUSY_NAMES = ('java.exe', 'projectzomboid64.exe', 'projectzomboid32.exe')


def _java_command_lines() -> dict[str, str]:
    """pid -> command line of every java.exe (empty dict when it cannot be read)."""
    cmd = ['powershell', '-NoProfile', '-Command',
           "Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" | "
           "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    lines = {}
    for line in out.splitlines():
        pid, _, command = line.partition('	')
        if pid.strip().isdigit():
            lines[pid.strip()] = command
    return lines


def busy_processes() -> list[str]:
    """Running Project Zomboid games or servers (ours or not: never killed here). A java.exe
    whose command line does not mention Zomboid (Ghidra, an IDE...) does not count; one whose
    command line cannot be read does."""
    out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, errors='replace').stdout
    found, commands = [], None
    for line in out.splitlines():
        cells = [c.strip('"') for c in line.split('","')]
        if not cells or cells[0].lower() not in BUSY_NAMES:
            continue
        pid = cells[1] if len(cells) > 1 else '?'
        if cells[0].lower() == 'java.exe':
            if commands is None:
                commands = _java_command_lines()
            command = commands.get(pid)
            if command is not None and command.strip() and 'zomboid' not in command.lower():
                continue
        found.append(f'{cells[0]} (pid {pid})')
    return found


def find_window(pid: int) -> int | None:
    """Visible top-level window of the process (the game window), or None."""
    user32 = ctypes.windll.user32
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
            found.append(hwnd)
        return True

    user32.EnumWindows(proto(callback), 0)
    return found[0] if found else None


def post_click(hwnd: int) -> None:
    """Left button down then up at the centre of the client area, posted to the window (no focus, no cursor move):
    GameLoadingState reads Mouse.isButtonDown(0) (GLFW state), set by these messages."""
    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

    rect = RECT()
    user32.GetClientRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
    x, y = rect.right // 2, rect.bottom // 2
    lparam = (y << 16) | (x & 0xFFFF)
    user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0201, 0x0001, lparam)  # WM_LBUTTONDOWN, MK_LBUTTON
    time.sleep(0.4)
    user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0202, 0, lparam)  # WM_LBUTTONUP


def kill_tree(pid: int) -> None:
    """Kills a process started by this tool and its children (never called on another pid)."""
    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)


def free_memory_mb() -> int:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullAvailPhys // (1024 * 1024))
    except (AttributeError, OSError):
        pass
    return 0
