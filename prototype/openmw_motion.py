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


# Native Windows INPUT must include the largest union member MOUSEINPUT;
# sizeof(INPUT) is 40 bytes on x64 and 28 on x86.
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', ctypes.c_uint16), ('wScan', ctypes.c_uint16),
                ('dwFlags', ctypes.c_uint32), ('time', ctypes.c_uint32),
                ('dwExtraInfo', ctypes.c_void_p)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_int32), ('dy', ctypes.c_int32),
                ('mouseData', ctypes.c_uint32), ('dwFlags', ctypes.c_uint32),
                ('time', ctypes.c_uint32), ('dwExtraInfo', ctypes.c_void_p)]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', ctypes.c_uint32), ('wParamL', ctypes.c_uint16),
                ('wParamH', ctypes.c_uint16)]

class INPUTUNION(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint32), ('u', INPUTUNION)]

def validate_input_abi():
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    actual = ctypes.sizeof(INPUT)
    if actual != expected or INPUT.u.offset != (8 if expected == 40 else 4):
        raise ControlRejected(f'Неверная структура Windows INPUT: {actual} вместо {expected}')
    return actual


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

        validate_input_abi()
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
        ctypes.set_last_error(0)
        accepted = self.user32.SendInput(1, ctypes.byref(payload), ctypes.sizeof(payload))
        if accepted != 1:
            error = ctypes.get_last_error()
            if error == 87:
                hint = 'Windows отклонила структуру INPUT (ошибка 87).'
            elif error in (5, 0):
                hint = ('Возможно, OpenMW запущена с более высокими правами или '
                        'ввод блокируется защитой Windows. Не повышай права SILK автоматически.')
            else:
                hint = 'Проверь активное окно и уровень прав OpenMW.'
            raise ControlRejected(f'Windows SendInput: код {error}. {hint}')

    def press_w(self):
        self._send_w(False)

    def release_w(self):
        self._send_w(True)


def forward_once(seconds: float = 0.20, *, confirm: bool = False) -> dict:
    return StepController(Win32Backend()).forward(seconds, confirm=confirm)
