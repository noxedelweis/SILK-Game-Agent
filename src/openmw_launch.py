"""Start the user's existing OpenMW executable without changing game settings.

No shell; safe path recognition; duplicate-instance guard; game saves/mods untouched.
The Lua observer probe embedded in OpenMW creates the log after loading a save.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
from pathlib import Path


class OpenMWLaunchError(RuntimeError):
    pass


KNOWN_OPENMW = (Path(r'L:\SkyForm\OpenMW 0.51.0\openmw.exe'),)


def _is_exe(candidate: Path) -> bool:
    """Never launch executables other than an existing openmw.exe."""
    return candidate.name.casefold() == 'openmw.exe' and candidate.is_file()


def locate_openmw(extra_candidates=(), environ=None, which=shutil.which) -> Path:
    environ = environ if environ is not None else os.environ
    candidates = []
    if environ.get('SILK_OPENMW_EXE'):
        candidates.append(Path(environ['SILK_OPENMW_EXE'].strip('"')))
    candidates.extend(extra_candidates)
    candidates.extend(KNOWN_OPENMW)
    for key in ('ProgramFiles', 'ProgramFiles(x86)'):
        if environ.get(key):
            root = Path(environ[key])
            candidates.extend((root/'OpenMW'/'openmw.exe', root/'OpenMW 0.51.0'/'openmw.exe'))
    path_from_env = which('openmw.exe')
    if path_from_env:
        candidates.append(Path(path_from_env))
    for candidate in candidates:
        p = Path(candidate)
        if _is_exe(p):
            return p.resolve()
    raise OpenMWLaunchError('OpenMW не найдена. Проверен путь L:\\SkyForm\\OpenMW 0.51.0\\openmw.exe. '
                            'Настройки и сохранения не изменены.')


def _native_process_names():
    """Enumerate Windows processes without spawning tasklist/cmd or a console.

    The old tasklist.exe polling could take focus from OpenMW repeatedly.
    Raises on an API error instead of assuming the game is not running.
    """
    if os.name != 'nt':
        raise OpenMWLaunchError('Проверка процессов доступна только на Windows')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_void_p),
            ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260),
        ]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    snap = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if snap in (None, ctypes.c_void_p(-1).value):
        raise OpenMWLaunchError(f'Windows не дала снимок процессов, WinError={ctypes.get_last_error()}')
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(snap, ctypes.byref(entry)):
            err = ctypes.get_last_error()
            if err == 18:  # ERROR_NO_MORE_FILES
                return []
            raise OpenMWLaunchError(f'Не удалось получить список процессов, WinError={err}')
        result = [entry.szExeFile]
        while kernel.Process32NextW(snap, ctypes.byref(entry)):
            result.append(entry.szExeFile)
        return result
    finally:
        kernel.CloseHandle(snap)


def is_openmw_running(*, names=None):
    """Native process probe: never creates windows and never runs tasklist.exe."""
    if os.name != 'nt':
        raise OpenMWLaunchError('Запуск OpenMW доступен только на Windows')
    try:
        all_names = _native_process_names() if names is None else names()
        return any(str(name).strip().casefold() == 'openmw.exe' for name in all_names)
    except (OSError, ctypes.ArgumentError, ValueError) as exc:
        raise OpenMWLaunchError('Не удалось проверить процессы OpenMW: ' + str(exc)) from exc


def launch_openmw(*, locate=locate_openmw, is_running=is_openmw_running,
                  popen=subprocess.Popen) -> dict:
    """User-triggered launch only, never start the game for background automation."""
    if is_running():
        return {'status':'already_running', 'game':'OpenMW',
                'telemetry':'Lua-зонд начинает выдавать новые данные после загрузки персонажа'}
    exe = locate()
    if not _is_exe(exe):
        raise OpenMWLaunchError('Небезопасный или отсутствующий путь к OpenMW.exe')
    try:
        child = popen([str(exe)], cwd=str(exe.parent), shell=False,
                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, close_fds=True)
    except OSError as e:
        raise OpenMWLaunchError('Windows не смогла запустить OpenMW: '+str(e)) from e
    return {'status':'launched', 'game':'OpenMW', 'exe':str(exe),
            'pid':child.pid, 'telemetry':'Ожидается загрузка персонажа; Lua-зонд должен начать запись координат',
            'controls_enabled':False}