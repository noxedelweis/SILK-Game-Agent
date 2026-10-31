"""SILK Game Agent: guarded first-person movement experiment (Windows).

Only one bounded W press; never switches windows, edits saves, or installs mods.
Explicit interactive consent is mandatory for every step. This is NOT an
autonomous player and must not be enabled by the current read-only observer.
"""
from __future__ import annotations

import ctypes
import math
import os
import time
from ctypes import wintypes


class ControlRejected(RuntimeError):
    pass


class StepController:
    """Hardware-independent control logic for unit-testing safety rules."""

    def __init__(self, backend, sleeper=time.sleep, clock=time.monotonic):
        self.backend = backend
        self.sleep = sleeper
        self.clock = clock

    def forward(self, seconds: float = 0.20, *, confirm: bool = False) -> dict:
        if not confirm:
            raise ControlRejected('Движение требует явного подтверждения пользователя')
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds):
            raise ControlRejected('Некорректная длительность')
        if not 0.05 <= seconds <= 0.40:
            raise ControlRejected('Допускается только короткий шаг от 0.05 до 0.40 секунды')
        if not self.backend.is_openmw_foreground():
            raise ControlRejected('OpenMW должна быть активным окном')
        if self.backend.is_emergency_stop():
            raise ControlRejected('Нажата клавиша аварийной остановки')
        started = self.clock()
        self.backend.press_w()
        try:
            while self.clock() - started < seconds:
                if self.backend.is_emergency_stop() or not self.backend.is_openmw_foreground():
                    raise ControlRejected('Движение прервано: фокус потерян или нажата ESC')
                self.sleep(max(0.001, min(0.025, seconds - (self.clock() - started))))
        finally:
            self.backend.release_w()
        return {'action': 'step_forward', 'sent': True, 'seconds_requested': float(seconds),
                'verified_in_game': False}


class Win32Backend:
    """SendInput limited to W key and only when foreground PID is openmw.exe."""

    VK_W = 0x57
    VK_ESCAPE = 0x1B
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    INPUT_KEYBOARD = 1
    KEYEVENTF_SCANCODE = 0x0008
    KEYEVENTF_KEYUP = 0x0002

    def __init__(self):
        if os.name != 'nt':
            raise OSError('Управление доступно только в Windows')
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
                        ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                        ('dwExtraInfo', ctypes.c_void_p)]
        class INPUTUNION(ctypes.Union):
            _fields_ = [('ki', KEYBDINPUT)]
        class INPUT(ctypes.Structure):
            _fields_ = [('type', wintypes.DWORD), ('u', INPUTUNION)]
        self.KEYBDINPUT, self.INPUT, self.INPUTUNION = KEYBDINPUT, INPUT, INPUTUNION
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                            wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short

    def is_openmw_foreground(self) -> bool:
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return False
        handle = self.kernel32.OpenProcess(self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return False
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buf))
            if not self.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return False
            return os.path.basename(buf.value).casefold() == 'openmw.exe'
        finally:
            self.kernel32.CloseHandle(handle)

    def is_emergency_stop(self) -> bool:
        return bool(self.user32.GetAsyncKeyState(self.VK_ESCAPE) & 0x8000)

    def _send_w(self, keyup: bool):
        scan = self.user32.MapVirtualKeyW(self.VK_W, 0)
        if not scan:
            raise ControlRejected('Не удалось определить скан-код W')
        flags = self.KEYEVENTF_SCANCODE | (self.KEYEVENTF_KEYUP if keyup else 0)
        payload = self.INPUT(type=self.INPUT_KEYBOARD,
                             u=self.INPUTUNION(ki=self.KEYBDINPUT(0, scan, flags, 0, None)))
        if self.user32.SendInput(1, ctypes.byref(payload), ctypes.sizeof(payload)) != 1:
            raise ControlRejected('Windows не приняла событие клавиатуры')

    def press_w(self):
        self._send_w(False)

    def release_w(self):
        self._send_w(True)


def forward_once(seconds: float = 0.20, *, confirm: bool = False) -> dict:
    return StepController(Win32Backend()).forward(seconds, confirm=confirm)
