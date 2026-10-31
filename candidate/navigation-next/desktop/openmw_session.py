"""SILK: user-initiated OpenMW session launcher with read-only live monitoring.

Does not enable controls, change savegames, modify OpenMW configs, or call Ollama.
Spawns one detached observer per session; previous observers stop when token changes.
Fresh connection requires an OpenMW SILK_OBS_V03 record produced AFTER launch.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable

from openmw_launch import launch_openmw, is_openmw_running
from motion_session import newest_sample
from observer_import import find_openmw_log

ID_RE = re.compile(r'^[0-9a-f]{32}$')
STATE_FILENAME = 'session_state.json'
DISPLAY_FILENAME = 'session_state.txt'


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.silk_session_',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def write_status(folder: Path, payload: dict):
    """Only display from local trusted telemetry, never infer game readiness."""
    atomic_write(folder/STATE_FILENAME,json.dumps(payload,ensure_ascii=False,indent=2))
    status=payload['status']
    if status == 'connected':
        sample=payload.get('sample',{})
        msg=f'OpenMW: подключено | {sample.get("cell","?")} | seq {sample.get("seq","?")} | управление выключено'
    elif status=='waiting':
        msg='OpenMW: игра запущена — загрузите сохранение; жду свежую телеметрию SILK'
        if payload.get('probe_hint'):
            msg='OpenMW: нет координат SILK_OBS_V03 — загрузите сохранение / проверьте Lua-зонд'
    elif status=='stale':
        msg='OpenMW: телеметрия давно не обновлялась — проверь игру и Lua-зонд'
    elif status=='closed':
        msg='OpenMW: игра закрыта — наблюдение завершено'
    else:
        msg='OpenMW: наблюдение не подключено — '+str(payload.get('reason','ошибка'))[:150]
    atomic_write(folder/DISPLAY_FILENAME,msg+'\n')


def read_status(folder: Path) -> dict | None:
    try:
        data=json.loads((folder/STATE_FILENAME).read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else None
    except (FileNotFoundError, ValueError, OSError):
        return None


def newest_with_signature(find_log: Callable, read_sample: Callable):
    try:
        log=find_log()
        if not log:
            return None, None
        log=Path(log)
        st=log.stat()
        sample=read_sample(log)
        return (sample, {'path':str(log), 'mtime_ns':st.st_mtime_ns, 'size':st.st_size})
    except (OSError, PermissionError):
        return None, None


def changed_after_start(sample, signature, baseline, since_ns: int) -> bool:
    if sample is None or signature is None:
        return False
    if signature['mtime_ns'] < since_ns:
        return False
    old=baseline.get('sample')
    oldsig=baseline.get('signature')
    if not old or not oldsig or oldsig['path'] != signature['path']:
        return True
    if signature['size'] < oldsig['size']:
        return True # OpenMW reset/truncated the previous log
    if signature['mtime_ns'] <= oldsig['mtime_ns']:
        return False
    return (sample.seq != old['seq'] or sample.cell != old['cell']
            or (sample.x,sample.y,sample.z,sample.health) !=
               (old['x'],old['y'],old['z'],old['health']))


def start_session(home: Path, active: Path, *, launch=launch_openmw,
                  start_process=subprocess.Popen, find_log=None, read_sample=newest_sample,
                  wallclock_ns=time.time_ns):
    """Start on explicit GUI click. Watcher never sends keys, only checks log."""
    home=Path(home)
    folder=home/'_system'/'session'
    folder.mkdir(parents=True,exist_ok=True)
    find_log=find_log or (lambda: find_openmw_log(active))
    before, before_signature=newest_with_signature(find_log,read_sample)
    baseline={
        'sample': None if before is None else dict(seq=before.seq,cell=before.cell,
                   x=before.x,y=before.y,z=before.z,health=before.health),
        'signature': before_signature,
    }
    started_ns=wallclock_ns()
    result=launch()
    token=uuid.uuid4().hex
    state={'session_id':token,'status':'waiting','game':result['status'],
           'started_ns':started_ns,'baseline':baseline,'controls_enabled':False,
           'updated_ns':wallclock_ns()}
    write_status(folder,state)
    args=[sys.executable,str(sys.argv[0]),'session-watch','--session-id',token]
    flags=(getattr(subprocess,'CREATE_NO_WINDOW',0)|
           getattr(subprocess,'DETACHED_PROCESS',0)) if os.name=='nt' else 0
    try:
        process=start_process(args,creationflags=flags,close_fds=True,
                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except OSError as exc:
        state.update(status='error',reason='Не удалось включить мониторинг: '+str(exc))
        write_status(folder,state)
        return {'status':'launch_only','game':result,'watcher':'failed','reason':str(exc),
                'controls_enabled':False}
    return {'status':'session_started','game':result,'watcher_pid':process.pid,
            'telemetry':'Ожидается свежая запись SILK_OBS_V03 после загрузки персонажа',
            'controls_enabled':False}


def monitor_session(folder: Path, token: str, *, find_log, read_sample=newest_sample,
                    running=is_openmw_running, clock=time.monotonic,
                    ns_clock=time.time_ns, sleep=time.sleep, limit_seconds=28800.0,
                    poll_seconds=2.5):
    if not ID_RE.fullmatch(token):
        raise ValueError('Недопустимый идентификатор сеанса')
    folder=Path(folder)
    first=read_status(folder)
    if not first or first.get('session_id') != token:
        return 'superseded'
    start=clock()
    last_fresh=None
    connected=False
    last_check=0.0
    while clock() - start < limit_seconds:
        state=read_status(folder)
        if not state or state.get('session_id') != token:
            return 'superseded'
        if clock()-last_check >= 4:
            last_check=clock()
            try:
                alive=running()
            except (OSError, RuntimeError):
                alive=False
            # Respect a brief startup window before calling it closed.
            if not alive and clock()-start > 12:
                state.update(status='closed',updated_ns=ns_clock())
                write_status(folder,state)
                return 'closed'
        sample,signature=newest_with_signature(find_log,read_sample)
        # Show a persistent, actionable hint after startup; do not mark connected.
        if (not connected and clock()-start >= 18 and sample is None
                and not state.get('probe_hint')):
            state.update(probe_hint=True, updated_ns=ns_clock())
            write_status(folder,state)
        if changed_after_start(sample,signature,state['baseline'],state['started_ns']):
            last_fresh=clock()
            connected=True
            state.pop('probe_hint',None)
            state.update(status='connected',updated_ns=ns_clock(),
                         sample={'cell':sample.cell,'seq':sample.seq,
                                 'x':sample.x,'y':sample.y,'z':sample.z},
                         last_observation_ns=signature['mtime_ns'])
            state['baseline']={'sample':dict(seq=sample.seq,cell=sample.cell,x=sample.x,
                                 y=sample.y,z=sample.z,health=sample.health),
                               'signature':signature}
            write_status(folder,state)
        elif connected and last_fresh is not None and clock()-last_fresh > 12:
            if state['status'] != 'stale':
                state.update(status='stale',updated_ns=ns_clock())
                write_status(folder,state)
        sleep(poll_seconds)
    state=read_status(folder)
    if state and state.get('session_id')==token:
        state.update(status='closed',reason='Достигнут лимит сеанса наблюдения',updated_ns=ns_clock())
        write_status(folder,state)
    return 'timeout'
