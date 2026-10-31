"""Supervised waypoint navigation for SILK/OpenMW using confirmed v0.3 probe.

Every individual WASD pulse is gated by explicit session consent, active OpenMW
foreground, live post-command observations, and ESC. No camera control or door
activation, no unsafe blind retries. Relative waypoints anchor to initial position.
"""
from __future__ import annotations
import math
import re
import time
from pathlib import Path
from micro_nav import sample_after, wait_for_initial_coordinates, compute_control_vector
from openmw_motion import ControlRejected, DirectionController, Win32Backend
from motion_session import newest_sample

PAIR = re.compile(r'^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*[, ]\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*$')


def parse_waypoints(text):
    """Example '35,15; 65,15; 65,-20': points relative to session origin."""
    if not isinstance(text, str) or not 1 <= len(text) <= 170:
        raise ControlRejected('Маршрут: до трёх относительных точек X,Y через точку с запятой')
    parts = text.split(';')
    if not 1 <= len(parts) <= 3:
        raise ControlRejected('Маршрут содержит от одной до трёх точек')
    points=[]
    prev=(0.,0.)
    total=0.
    for part in parts:
        m=PAIR.fullmatch(part)
        if not m:
            raise ControlRejected('Точки нужны в формате 35,15; 65,15; 65,-20')
        pt=tuple(float(m.group(i)) for i in (1,2))
        if not all(math.isfinite(c) for c in pt):
            raise ControlRejected('В координатах должны быть конечные числа')
        distance=math.dist(prev,pt)
        if distance<15 or distance>130 or math.hypot(*pt)>220:
            raise ControlRejected('Каждый участок должен быть 15–130 ед., цель не дальше 220 ед. от старта')
        total+=distance
        if total>350:
            raise ControlRejected('Длина полного маршрута ограничена 350 ед.')
        points.append(pt)
        prev=pt
    return tuple(points)


def measured_direction(key,forward,right):
    return {'W':forward, 'S':(-forward[0],-forward[1]),
            'D':right, 'A':(-right[0],-right[1])}[key]


def navigation_v2(log_path, waypoints, *,confirm=False,backend=None,
                  sample_reader=newest_sample, sleeper=time.sleep,
                  clock=time.monotonic, wallclock=time.time,
                  switch_seconds=4., max_pulses=12, tolerance=12.):
    if not confirm:
        raise ControlRejected('Навигация 2.0 требует явного разрешения пользователя')
    if not isinstance(waypoints,tuple) or not 1 <= len(waypoints) <= 3:
        raise ControlRejected('Нужно от одной до трёх маршрутных точек')
    if not 2 <= max_pulses <= 12 or not 6 <= tolerance <= 15:
        raise ControlRejected('Небезопасный бюджет управления')
    # Apply same full geometry validation even for non-text callers.
    parsed=parse_waypoints(';'.join(f'{x},{y}' for x,y in waypoints))
    backend=backend or Win32Backend()
    reader=lambda:sample_reader(Path(log_path))
    print('Navigation 2.0: проверяю свежие координаты (до 12 с, без движения)...',flush=True)
    before=wait_for_initial_coordinates(Path(log_path),reader,backend,
                  sleeper=sleeper,clock=clock,wallclock=wallclock)
    print('Цепочка точек X/Y: '+str(list(parsed))+'; '+before.cell,flush=True)
    print('Переключись в OpenMW за 4 секунды. Не двигай персонажа; ESC — стоп.',flush=True)
    until=clock()+switch_seconds
    while clock()<until:
        if backend.is_emergency_stop():
            raise ControlRejected('ESC: маршрут отменён до начала')
        sleeper(min(.05,max(.001,until-clock())))
    if not backend.is_openmw_foreground():
        raise ControlRejected('Окно OpenMW не активно; клавиши не отправлены')
    start=reader()
    if start is None or start.seq<before.seq or start.cell!=before.cell:
        raise ControlRejected('После переключения нет согласованной телеметрии')
    if math.hypot(start.x-before.x,start.y-before.y)>2:
        raise ControlRejected('Персонаж переместился во время обратного отсчёта; маршрут отменён')
    origin=(start.x,start.y)
    targets=[(origin[0]+x,origin[1]+y) for x,y in parsed]
    ctl=DirectionController(backend,sleeper=sleeper,clock=clock)
    pulses=[]
    position=start
    forward=None;right=None
    def step(key,seconds,calibration=False):
        nonlocal position
        old=position
        ctl.pulse(key,seconds,confirm=True)
        nxt=sample_after(old,reader,backend,sleeper=sleeper,clock=clock)
        delta=(nxt.x-old.x,nxt.y-old.y)
        position=nxt
        record={'key':key,'seconds':round(seconds,3),'seq_before':old.seq,'seq_after':nxt.seq,
                'delta':[round(v,2) for v in delta], 'calibration':calibration}
        pulses.append(record)
        return delta
    # Just two calibration pulses, each observed in-engine, no unexplained camera commands.
    forward=step('W',.20,True)
    if math.hypot(*forward)<7:
        raise ControlRejected('Калибровка W: нет движения, остановка перед вторым нажатием')
    right=step('D',.20,True)
    # Validates that vectors have independent directions.
    compute_control_vector(forward,right,(10,10))
    reached=0;status='budget_exhausted';stop_reason='Достигнут лимит коротких команд'
    for waypoint,target in enumerate(targets):
        while len(pulses)<max_pulses:
            remaining=(target[0]-position.x,target[1]-position.y)
            distance=math.hypot(*remaining)
            if distance<=tolerance:
                reached+=1;break
            command=compute_control_vector(forward,right,remaining)
            key=command['key'];seconds=command['duration']
            expected=measured_direction(key,forward,right)
            before_dist=distance
            observed=step(key,seconds)
            moved=math.hypot(*observed)
            new_dist=math.hypot(target[0]-position.x,target[1]-position.y)
            if moved<4:
                status='blocked';stop_reason='Нет движения: возможна преграда';break
            alignment=(expected[0]*observed[0]+expected[1]*observed[1])/(max(1e-6,math.hypot(*expected)*moved))
            if alignment<.45:
                status='orientation_changed';stop_reason='Изменилось направление движения или камеры';break
            if new_dist>before_dist+8:
                status='diverging';stop_reason='Персонаж удаляется от цели';break
            # Update the calibrated speed to account for changes in run/walk speed.
            scale=.20/seconds
            observed_corrected=(observed[0]*scale,observed[1]*scale)
            if key in ('W','S'):
                sign=1 if key=='W' else -1
                forward=tuple(.7*a+.3*sign*b for a,b in zip(forward,observed_corrected))
            else:
                sign=1 if key=='D' else -1
                right=tuple(.7*a+.3*sign*b for a,b in zip(right,observed_corrected))
        else:
            break
        if status in ('blocked','orientation_changed','diverging'):
            break
    else:
        status='arrived';stop_reason='Все маршрутные точки достигнуты в пределах допуска'
    if reached==len(targets):
        status='arrived';stop_reason='Все маршрутные точки достигнуты в пределах допуска'
    last_target=targets[min(reached,len(targets)-1)]
    return {'status':status, 'reason':stop_reason,'cell':start.cell,
            'total_waypoints':len(targets),'waypoints_reached':reached,
            'waypoints_xy':[[round(x,2),round(y,2)] for x,y in targets],
            'distance_to_next':round(math.hypot(last_target[0]-position.x,last_target[1]-position.y),2),
            'start_seq':start.seq,'end_seq':position.seq,
            'pulses':pulses,'manual_override':'ESC / смена активного окна',
            'attribution':'Координаты подтверждены OpenMW; принадлежность смещения командам остаётся предположением',
            'limits':'Нет поворотов камеры, поиска NPC, обхода препятствий и дверей'}