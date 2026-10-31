"""Safely launch the user's existing OpenMW without changing its config."""
from __future__ import annotations
import csv, io, os, shutil, subprocess
from pathlib import Path

class OpenMWLaunchError(RuntimeError): pass

KNOWN_OPENMW=(Path(r'L:\SkyForm\OpenMW 0.51.0\openmw.exe'),)

def _is_exe(path):
    return Path(path).name.casefold()=='openmw.exe' and Path(path).is_file()

def locate_openmw(extra_candidates=(), environ=None, which=shutil.which):
    environ=environ if environ is not None else os.environ
    candidates=[]
    if environ.get('SILK_OPENMW_EXE'):
        candidates.append(Path(environ['SILK_OPENMW_EXE'].strip('"')))
    candidates.extend(extra_candidates)
    candidates.extend(KNOWN_OPENMW)
    for key in ('ProgramFiles','ProgramFiles(x86)'):
        if environ.get(key):
            root=Path(environ[key])
            candidates.extend((root/'OpenMW'/'openmw.exe',root/'OpenMW 0.51.0'/'openmw.exe'))
    path=which('openmw.exe')
    if path: candidates.append(Path(path))
    for candidate in candidates:
        if _is_exe(candidate): return Path(candidate).resolve()
    raise OpenMWLaunchError(r'Не найдена OpenMW: L:\SkyForm\OpenMW 0.51.0\openmw.exe')

def is_openmw_running(*, tasklist=subprocess.run):
    if os.name!='nt': raise OpenMWLaunchError('Только Windows')
    try:
        result=tasklist(['tasklist.exe','/FI','IMAGENAME eq openmw.exe','/FO','CSV','/NH'],
                        capture_output=True,text=True,errors='replace',timeout=8,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise OpenMWLaunchError('Не удалось проверить процессы') from exc
    if result.returncode: raise OpenMWLaunchError('Не удалось получить список процессов')
    return any(row and row[0].strip().casefold()=='openmw.exe'
               for row in csv.reader(io.StringIO(result.stdout)))

def launch_openmw(*, locate=locate_openmw, is_running=is_openmw_running, popen=subprocess.Popen):
    if is_running():
        return {'status':'already_running','game':'OpenMW','controls_enabled':False}
    exe=locate()
    if not _is_exe(exe): raise OpenMWLaunchError('Неподходящий исполняемый файл')
    try:
        proc=popen([str(exe)],cwd=str(exe.parent),shell=False,stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
    except OSError as exc:
        raise OpenMWLaunchError('Windows не запустила OpenMW: '+str(exc)) from exc
    return {'status':'launched','game':'OpenMW','exe':str(exe),'pid':proc.pid,
            'controls_enabled':False,'telemetry':'Новые данные после загрузки персонажа'}
