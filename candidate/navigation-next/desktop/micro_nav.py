"""SILK Game Agent supervised micro-navigation using only v0.3 read-only telemetry.

A *single* user-approved session: calibrate 2 vectors from short W/D pulses,
then at most six bounded WASD pulses toward a nearby point in the current cell.
This is a feasibility test; not route/pathfinding or proof of causal attribution.
No independent control of game camera or window focus. ESC stops all motion.
"""
from __future__ import annotations

import math
import re
import time
from pathlib import Path
from typing import Callable

from motion_session import Sample, newest_sample
from openmw_motion import ControlRejected, Win32Backend, DirectionController

OFFSET = re.compile(r'^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*[,; ]\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*$')


def parse_offset(text: str) -> tuple[float, float]:
    if not isinstance(text, str) or len(text) > 70:
        raise ControlRejected('Укажи относительную точку: dx,dy, например 35,15')
    match = OFFSET.fullmatch(text)
    if not match:
        raise ControlRejected('Нужны два смещения X,Y (например 35,15), а не название места')
    dx, dy = float(match.group(1)), float(match.group(2))
    if not all(math.isfinite(v) for v in (dx,dy)) or not 15 <= math.hypot(dx,dy) <= 90:
        raise ControlRejected('Для первого теста расстояние должно быть от 15 до 90 игровых единиц')
    return dx,dy


def v2(a: Sample, b: Sample) -> tuple[float, float]:
    if a.cell != b.cell or b.seq <= a.seq:
        raise ControlRejected('Локация изменилась или телеметрия не обновилась')
    return b.x-a.x,b.y-a.y


def compute_control_vector(forward: tuple[float,float], right:tuple[float,float],
                           delta:tuple[float,float]) -> dict:
    """Solve delta = a*forward + b*right; a,b are 0.20s pulse counts."""
    fx,fy=forward;rx,ry=right; dx,dy=delta
    f=math.hypot(fx,fy);r=math.hypot(rx,ry)
    cross=fx*ry-fy*rx
    if min(f,r)<7 or abs(cross) < .32*f*r:
        raise ControlRejected('Нельзя определить направление: короткие движения слишком малы или почти параллельны')
    a=(dx*ry-dy*rx)/cross
    b=(fx*dy-fy*dx)/cross
    if not all(math.isfinite(v) for v in (a,b)):
        raise ControlRejected('Неверная калибровка направления')
    if abs(a)>=abs(b):
        return {'key':'W' if a>0 else 'S','duration':max(.08,min(.22,abs(a)*.20)),
                'projection':a,'cross':cross}
    return {'key':'D' if b>0 else 'A','duration':max(.08,min(.22,abs(b)*.20)),
            'projection':b,'cross':cross}


def sample_after(before:Sample, reader:Callable[[],Sample|None], backend,
                 sleeper=time.sleep, clock=time.monotonic, timeout=8.) -> Sample:
    """Reject missing/old/new-cell samples. Never pretend an old position is new."""
    deadline=clock()+timeout
    while clock()<deadline:
        if backend.is_emergency_stop() or not backend.is_openmw_foreground():
            raise ControlRejected('Остановка: ESC или фокус OpenMW потерян')
        obs=reader()
        if obs is not None and obs.seq>before.seq:
            if obs.cell != before.cell:
                raise ControlRejected('Смена локации: микронавигация немедленно остановлена')
            return obs
        sleeper(min(.2,max(.01,deadline-clock())))
    raise ControlRejected('Нет свежей телеметрии OpenMW: маршрут остановлен')



def wait_for_initial_coordinates(log_path: Path, reader: Callable[[], Sample | None], backend, *,
                                 clock=time.monotonic, sleeper=time.sleep,
                                 wallclock=time.time, timeout=12.0) -> Sample:
    """Bounded, no-key wait for the FIRST Lua telemetry record after game startup.

    The v0.4.11 nav path checked only once: when OpenMW rotated its log on
    launch or the probe had yet to write its 3-second sample, it failed even
    though the session would soon connect. Never use stale file data.
    """
    deadline = clock() + timeout
    while True:
        if backend.is_emergency_stop():
            raise ControlRejected('ESC: ожидание телеметрии отменено; клавиши не отправлялись')
        try:
            mtime = log_path.stat().st_mtime
            # The observer may be writing. Avoid trusting a file from an old session.
            if wallclock() - mtime <= 15.0:
                result = reader()
                if result is not None:
                    return result
        except (FileNotFoundError, PermissionError, OSError):
            pass
        remaining = deadline - clock()
        if remaining <= 0:
            break
        sleeper(min(.25, max(.01, remaining)))
    try:
        stat = log_path.stat()
        if wallclock() - stat.st_mtime > 15.0:
            reason = 'Журнал OpenMW не обновляется — сначала загрузите сохранение и убедитесь, что игра не на паузе.'
        else:
            # The file is live, but no probe observations. Extract a safe hint.
            with log_path.open('rb') as fh:
                fh.seek(max(0, stat.st_size - 65536))
                tail=fh.read()
            if b'SILK_PROBE_ERROR' in tail:
                reason = 'Lua-зонд сообщает SILK_PROBE_ERROR. Проверьте подключенный мод SILK v0.3.'
            else:
                reason = 'OpenMW пишет журнал, но нет SILK_OBS_V03: проверьте включение Lua-зонда SILK v0.3.'
    except (OSError, PermissionError):
        reason = 'Не удалось прочитать журнал OpenMW.'
    raise ControlRejected(reason + ' Маршрут не начинался, клавиши не отправлялись.')

def guarded_navigation(log_path:Path, offset:tuple[float,float], *,confirm=False,
                       backend=None, sample_reader=newest_sample,
                       sleeper=time.sleep,clock=time.monotonic,wallclock=time.time,
                       switch_seconds=4.,max_steps=6) -> dict:
    """Calibrate and move toward a nearby relative X/Y target; bounded by max_steps.

    Each confirmed command is followed by one fresh in-engine position sample.
    User must not touch movement controls during the session; the algorithm
    cannot independently distinguish operator movement from its own actions.
    """
    if not confirm:
        raise ControlRejected('Требуется согласие пользователя на ограниченный маршрут')
    if (not isinstance(offset,tuple) or len(offset)!=2 or
        not all(isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x) for x in offset) or
        not 15<=math.hypot(*offset)<=90):
        raise ControlRejected('Относительное смещение должно быть 15–90 единиц')
    if not 1<=max_steps<=6:
        raise ControlRejected('Число команд ограничено шестью')
    log_path=Path(log_path)
    backend=backend or Win32Backend()
    reader=lambda:sample_reader(log_path)
    print('Проверяю телеметрию OpenMW (ожидание до 12 секунд, без движения)...',flush=True)
    before=wait_for_initial_coordinates(log_path, reader, backend, clock=clock,
                                         sleeper=sleeper, wallclock=wallclock)
    print(f'Микронавигация: {before.cell}; цель относительно позиции: {offset}',flush=True)
    print('Переключись в OpenMW в течение 4 секунд. Не нажимай кнопки движения; ESC — стоп.',flush=True)
    deadline=clock()+switch_seconds
    while clock()<deadline:
        if backend.is_emergency_stop():raise ControlRejected('ESC: маршрут отменён до старта')
        sleeper(min(.05,max(.001,deadline-clock())))
    if not backend.is_openmw_foreground():
        raise ControlRejected('OpenMW должна быть активным окном: маршрут не начат')
    start=reader()
    if start is None or start.cell!=before.cell or start.seq<before.seq:
        raise ControlRejected('Не получена согласованная исходная точка')
    if math.hypot(start.x-before.x,start.y-before.y)>2:
        raise ControlRejected('Во время отсчёта персонаж двигался: маршрут отменён')

    moves=[]
    controller=DirectionController(backend,sleeper=sleeper,clock=clock)
    position=start
    for key in ('W','D'):
        # Keep calibration on short pulses; do not run if input focus changes.
        controller.pulse(key,.20,confirm=True)
        nxt=sample_after(position,reader,backend,sleeper,clock)
        delta=v2(position,nxt)
        if math.hypot(*delta)<7:
            raise ControlRejected(f'Калибровка {key}: персонаж почти не двинулся. Вероятно, препятствие.')
        moves.append({'key':key,'seq_before':position.seq,'seq_after':nxt.seq,'delta':tuple(round(x,2) for x in delta)})
        position=nxt
    forward=tuple(moves[0]['delta']);right=tuple(moves[1]['delta'])
    # Target remains relative to position at start, not after calibration.
    target=(start.x+offset[0],start.y+offset[1]); distances=[]
    for n in range(max_steps):
        remaining=(target[0]-position.x,target[1]-position.y)
        dist=math.hypot(*remaining)
        distances.append(round(dist,2))
        if dist<=12:break
        command=compute_control_vector(forward,right,remaining)
        controller.pulse(command['key'],command['duration'],confirm=True)
        nxt=sample_after(position,reader,backend,sleeper,clock)
        traveled=math.hypot(*v2(position,nxt))
        moves.append({'key':command['key'],'seconds':round(command['duration'],3),
                      'seq_before':position.seq,'seq_after':nxt.seq,
                      'distance':round(traveled,2)})
        if traveled<4:
            raise ControlRejected('Препятствие или остановка: после команды нет достаточного смещения')
        newdist=math.hypot(target[0]-nxt.x,target[1]-nxt.y)
        if newdist>dist+8:
            raise ControlRejected('Мы удаляемся от цели: остановка и перепроверка направления')
        position=nxt
    final=math.hypot(target[0]-position.x,target[1]-position.y)
    return {'status':'arrived' if final<=12 else 'budget_exhausted',
            'target_cell':start.cell, 'target_xy':[round(x,2) for x in target],
            'start_seq':start.seq,'end_seq':position.seq, 'distance_remaining':round(final,2),
            'pulses':moves,'used_genuine_engine_samples':True,
            'attribution':'Наблюдаемое смещение согласуется с командами, но причинность не доказана',
            'limitations':'Направление строится по калибровке W и D. Повороты камеры, двери и объезды препятствий не поддерживаются.'}
