"""Experimental, opt-in, short-range approach to a detected OpenMW door.

This does not interact with doors, cross cells, rotate camera or solve path
planning. The goal is a safe stand-off position and the existing v0.5
coordinate controller still gates every keypress against focus/ESC/telemetry.
"""
from __future__ import annotations
import math
from env_reader import inspect_environment
from openmw_motion import ControlRejected
from nav_v2 import parse_waypoints, navigation_v2

STANDOFF = 80.0
MAX_PATH = 210.0
MIN_LEG = 15.0
MAX_LEG = 105.0


def _distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])


def choose_door(snapshot, door_index=0):
    if snapshot['status'] != 'current':
        raise ControlRejected('Для навигации к двери нужна свежая среда OpenMW; осмотр устаревших данных доступен только для чтения')
    environment = snapshot['observation']
    if not environment or not environment['cell']:
        raise ControlRejected('Неизвестна игровая локация')
    doors = environment['doors']
    if not isinstance(door_index, int) or isinstance(door_index, bool) or door_index < 0 or door_index >= len(doors):
        raise ControlRejected('Указанная дверь отсутствует в последнем наблюдении')
    return environment, doors[door_index]


def plan_door_approach(snapshot, door_index=0):
    """Plan 1–3 capped relative waypoints; no game I/O and no keypresses."""
    env, door = choose_door(snapshot, door_index)
    origin = (env['x'], env['y'])
    target = (door['x'], door['y'])
    distance = _distance(origin, target)
    if distance > MAX_PATH + STANDOFF:
        raise ControlRejected('Дверь слишком далеко для экспериментального прямого подхода')
    remaining = distance - STANDOFF
    if remaining <= MIN_LEG:
        return {'status': 'already_near', 'mode': 'experimental_read_only',
                'cell': env['cell'], 'door': door, 'distance_to_door': round(distance,2),
                'stand_off': STANDOFF, 'waypoints': [], 'source_seq': env['seq'],
                'warning': 'Дверь рядом; не требуется движение'}
    if remaining > MAX_PATH:
        raise ControlRejected('Путь слишком длинный для прямого подхода')
    ux, uy = (target[0]-origin[0])/distance, (target[1]-origin[1])/distance
    legs = math.ceil(remaining/MAX_LEG)
    if legs > 3:
        raise ControlRejected('Превышен лимит 3 участков')
    steps = [(round(ux*remaining*i/legs, 3), round(uy*remaining*i/legs, 3))
             for i in range(1,legs+1)]
    # All geometry must also pass the existing strictly bounded navigation parser.
    points = parse_waypoints(';'.join(f'{x},{y}' for x,y in steps))
    return {'status': 'preview', 'mode': 'experimental_read_only', 'cell': env['cell'],
            'door': door, 'distance_to_door': round(distance,2), 'stand_off': STANDOFF,
            'waypoints': [list(p) for p in points], 'source_seq': env['seq'],
            'warning': 'Прямой подход БЕЗ построения пути по навмешу: стены, перепады высот и препятствия пока неизвестны. Управление отдельно подтверждается.'}


def navigate_to_door(log_path, door_index=0, *, confirm=False,
                     snapshot_reader=inspect_environment, navigator=navigation_v2,
                     backend=None, clock=None, sleeper=None, wait_seconds=4., observation_timeout=10.):
    """Switch to the game, re-observe environment, then approach with live checks.

    Important: GUI focus can pause the game. Never use a pre-switch snapshot to
    steer. Wait for a *new* engine sample after OpenMW regains foreground.
    """
    import time
    from openmw_motion import Win32Backend
    if not confirm:
        raise ControlRejected('Движение к двери требует явного разрешения')
    clock = clock or time.monotonic
    sleeper = sleeper or time.sleep
    backend = backend or Win32Backend()
    previous = snapshot_reader(log_path)
    baseline_seq = (previous.get('observation') or {}).get('seq')
    print('Экспериментальный подход: перейди в OpenMW за 4 секунды; ESC — стоп.',flush=True)
    deadline=clock()+wait_seconds
    while clock()<deadline:
        if backend.is_emergency_stop():
            raise ControlRejected('ESC: движение к двери отменено')
        sleeper(min(.05,max(.001,deadline-clock())))
    if not backend.is_openmw_foreground():
        raise ControlRejected('OpenMW не активно; движение запрещено')
    deadline=clock()+observation_timeout
    snapshot=None
    while clock()<deadline:
        if backend.is_emergency_stop() or not backend.is_openmw_foreground():
            raise ControlRejected('Потеря фокуса или ESC при ожидании среды')
        found=snapshot_reader(log_path)
        obs=found.get('observation') or {}
        if found['status']=='current' and obs.get('seq') != baseline_seq:
            snapshot=found
            break
        sleeper(.15)
    if snapshot is None:
        raise ControlRejected('Нет нового наблюдения среды после возврата в OpenMW — клавиши не отправлены')
    plan=plan_door_approach(snapshot,door_index)
    if plan['status']=='already_near':
        return {'status':'already_near', 'plan':plan, 'pulses':[]}
    env=snapshot['observation']
    def guard(start):
        if start.cell!=env['cell'] or math.hypot(start.x-env['x'],start.y-env['y'])>12:
            raise ControlRejected('Координаты игрока v0.3 расходятся с целевой средой: движение отменено')
    result=navigator(log_path,tuple(tuple(p) for p in plan['waypoints']),confirm=True,
                     backend=backend, switch_seconds=0.,start_guard=guard)
    return {'status':result['status'], 'plan':plan, 'navigation':result,
            'limitations':'Только прямые короткие участки; нет гарантии проходимости и входа через дверь'}
