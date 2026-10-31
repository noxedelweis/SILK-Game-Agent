"""One operator-approved action + strictly grounded OpenMW v0.3 telemetry check.

Does not alter the game installation, mods, saves, or existing bridge.
This module deliberately does not loop actions or call an LLM.
"""
from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from openmw_motion import StepController, Win32Backend, ControlRejected

MARKER = re.compile(
    r'SILK_OBS_V03\|(\d+)\|([^|\r\n]{1,90})\|'
    r'(-?(?:\d+(?:\.\d+)?|\.\d+))\|(-?(?:\d+(?:\.\d+)?|\.\d+))\|'
    r'(-?(?:\d+(?:\.\d+)?|\.\d+))\|(-?(?:\d+(?:\.\d+)?|\.\d+))(?=\s|$)'
)

@dataclass(frozen=True)
class Sample:
    seq: int
    cell: str
    x: float
    y: float
    z: float
    health: float


def parse_line(line: str) -> Sample | None:
    match = MARKER.search(line)
    if not match:
        return None
    seq = int(match.group(1))
    pos = [float(match.group(x)) for x in range(3,7)]
    if seq > 1_000_000_000 or not all(math.isfinite(x) for x in pos):
        return None
    if any(abs(x) > 1e9 for x in pos[:3]):
        return None
    return Sample(seq, match.group(2), *pos)


def newest_sample(log_path: Path) -> Sample | None:
    """Read only the last 128 KiB; skip truncated final records."""
    path = Path(log_path)
    with path.open('rb') as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 131072))
        data = f.read(131072)
    lines = data.splitlines()
    # A last line without newline is common during active logging. Accept it
    # only if the *entire* telemetry record parses; otherwise skip it safely.
    if data and not data.endswith((b'\n', b'\r')) and lines:
        if parse_line(lines[-1].decode('utf-8', errors='replace')) is None:
            lines = lines[:-1]
    for raw in reversed(lines):
        obs = parse_line(raw.decode('utf-8', errors='replace'))
        if obs is not None:
            return obs
    return None


def observe_movement(before: Sample, after: Sample) -> dict:
    """A coordinate delta is confirmed; attributing its cause remains an inference."""
    if after.seq <= before.seq:
        return {'verified':False,'reason':'Нет новой последовательности наблюдений'}
    if before.cell != after.cell:
        return {'verified':False,'reason':'Сменился игровой интерьер/регион: по точкам нельзя судить о шаге'}
    distance = math.dist((before.x, before.y, before.z), (after.x, after.y, after.z))
    if distance < 1.0:
        return {'verified':False,'reason':'Наблюдаемого смещения не обнаружено','distance_units':round(distance,2)}
    return {'verified':True,'distance_units':round(distance,2),'cell':after.cell,
            'evidence':'Различаются координаты OpenMW до и после действия',
            'attribution':'Связь с командой предполагается, а не доказывается'}


def step_once(log_path: Path, *, backend=None, sleeper=time.sleep, clock=time.monotonic,
              wallclock=time.time, switch_seconds=4.0, verify_seconds=9.0,
              sample_reader=newest_sample, confirm=False) -> dict:
    if not confirm:
        raise ControlRejected('Требуется явное согласие на один шаг')
    log_path=Path(log_path)
    if not log_path.is_file():
        raise ControlRejected('Нет журнала OpenMW: проверь установленный Lua probe v0.3')
    if wallclock() - log_path.stat().st_mtime > 20.0:
        raise ControlRejected('Журнал OpenMW не обновлялся более 20 секунд. Запусти игру с Lua probe.')
    previous = sample_reader(log_path)
    if previous is None:
        raise ControlRejected('В журнале OpenMW нет меток SILK_OBS_V03. Сначала полностью загрузи персонажа в игре. Если сохранение уже загружено, проверь, что старый Lua-зонд SILK v0.3 включён в OpenMW Launcher. Клавиши не отправлялись.')
    if backend is None:
        backend = Win32Backend()
    # Allow switching from SILK GUI to the in-game window; NEVER grab focus.
    print(f'Наблюдение до шага: {previous.cell} seq={previous.seq}',flush=True)
    print(f'Переключись в OpenMW в течение {switch_seconds:g} секунд (Alt+Tab).',flush=True)
    end=clock() + switch_seconds
    while clock() < end:
        if backend.is_emergency_stop():
            raise ControlRejected('Отменено по ESC до начала движения')
        sleeper(min(0.05, max(0.001, end-clock())))
    # If the player moved during countdown, don't attribute their movement to the agent.
    latest = sample_reader(log_path) or previous
    if latest.seq > previous.seq and (latest.cell != previous.cell or
        math.dist((previous.x,previous.y,previous.z),(latest.x,latest.y,latest.z)) >= 1.0):
        raise ControlRejected('Игрок уже двигался во время обратного отсчёта. Отмена для чистого теста.')
    if not backend.is_openmw_foreground():
        raise ControlRejected('Окно OpenMW не стало активным. Шаг не отправлен.')
    # 200 ms of W only, with release guaranteed on normal / exceptional exit.
    StepController(backend, sleeper=sleeper, clock=clock).forward(0.20, confirm=True)
    deadline=clock() + verify_seconds
    last=latest
    while clock() < deadline:
        if not backend.is_openmw_foreground() or backend.is_emergency_stop():
            break
        newer=sample_reader(log_path)
        if newer and newer.seq > latest.seq:
            last = newer
            outcome = observe_movement(latest, newer)
            if outcome['verified']:
                return {'command_sent':True,'command':'W / 0.20s',
                        'telemetry':outcome,'before_seq':latest.seq,'after_seq':newer.seq}
        sleeper(0.20)
    return {'command_sent':True,'command':'W / 0.20s',
            'telemetry':observe_movement(latest,last),
            'before_seq':latest.seq,'after_seq':last.seq}
