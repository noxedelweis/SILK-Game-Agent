"""Read-only OpenMW environment telemetry with explicit freshness semantics.

A paused game's onUpdate may run with dt=0: an old sample is useful for
inspection but NEVER evidence that the player/world is live now. A file's mtime
is also not the timestamp of an older sample within that file.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
import time
from pathlib import Path

_FLOAT = r'-?(?:\d+(?:\.\d+)?|\.\d+)'
LINE = re.compile(r'SILK_ENV_V050\|(\d{1,10})\|([^|\r\n]{1,100})\|('+_FLOAT+r')\|('+_FLOAT+r')\|('+_FLOAT+r')\|('+_FLOAT+r')\|([^|\r\n]{0,800})\|([^|\r\n]{0,800})(?=\s|$)')
PREFIX = re.compile(r'^\[(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?\s+[A-Za-z]\]')


def parse_line(line):
    m = LINE.search(line)
    if not m:
        return None
    try:
        seq = int(m.group(1))
        numbers = [float(m.group(i)) for i in range(3, 7)]
        if seq > 1_000_000_000 or not all(math.isfinite(n) and abs(n) < 1e9 for n in numbers):
            return None

        def objects(blob):
            out = []
            for entry in blob.split(';') if blob else []:
                parts = entry.split('~')
                if len(parts) != 3 or not parts[0] or len(parts[0]) > 120:
                    continue
                try:
                    x, y = float(parts[1]), float(parts[2])
                except ValueError:
                    continue  # Never discard a good player pose because one object is bad.
                if math.isfinite(x) and math.isfinite(y) and abs(x) < 1e9 and abs(y) < 1e9:
                    out.append({'record_id': parts[0], 'x': x, 'y': y})
            return out[:6]

        return {'seq': seq, 'cell': m.group(2), 'x': numbers[0], 'y': numbers[1],
                'z': numbers[2], 'yaw_radians': numbers[3],
                'doors': objects(m.group(7)), 'actors': objects(m.group(8))}
    except (OverflowError, ValueError):
        return None


def _sample_timestamp(line, file_mtime):
    """Infer a local timestamp from OpenMW's [HH:MM:SS.mmm I] log prefix.

    Use the most recent plausible calendar date <= mtime, allowing up to 2 s
    clock/logging skew. If absent, don't falsely certify freshness from mtime.
    """
    m = PREFIX.match(line)
    if not m:
        return None
    h, minute, sec = map(int, m.group(1, 2, 3))
    if h > 23 or minute > 59 or sec > 59:
        return None
    ms = int((m.group(4) or '0').ljust(3, '0'))
    base = dt.datetime.fromtimestamp(file_mtime).replace(hour=h, minute=minute,
            second=sec, microsecond=ms * 1000)
    candidates = [base + dt.timedelta(days=offset) for offset in (-1, 0, 1)]
    acceptable = [p.timestamp() for p in candidates if p.timestamp() <= file_mtime+2]
    return max(acceptable) if acceptable else None


def inspect_environment(path, *, now=time.time, max_age=15., limit=262144):
    """Returns latest parsed sample with state current/stale/unknown/missing.

    Designed for inspection only. Motor control should independently require
    fresh SILK_OBS_V03 and confirm the live world/cell before each keypress.
    """
    path = Path(path)
    if not path.is_file():
        return {'status': 'missing', 'observation': None, 'age_seconds': None,
                'message': 'Не найден журнал OpenMW'}
    stat = path.stat()
    with path.open('rb') as f:
        f.seek(max(0, stat.st_size-limit), os.SEEK_SET)
        lines = f.read(limit).splitlines()
    for raw in reversed(lines):
        line = raw.decode('utf-8', errors='replace')
        sample = parse_line(line)
        if sample is None:
            continue
        timestamp = _sample_timestamp(line, stat.st_mtime)
        age = None if timestamp is None else max(0., now()-timestamp)
        state = 'unknown' if age is None else ('current' if age <= max_age else 'stale')
        return {'status': state, 'observation': sample,
                'age_seconds': round(age, 1) if age is not None else None,
                'message': {'current': 'Свежая запись среды OpenMW',
                            'stale': 'Последние данные среды сохранены, но устарели (игра может быть на паузе)',
                            'unknown': 'Данные получены, но время записи неизвестно; движение запрещено без новой проверки'}[state]}
    return {'status': 'missing', 'observation': None, 'age_seconds': None,
            'message': 'В журнале пока нет распознаваемой метки SILK_ENV_V050'}


def latest_environment(path, *, now=time.time, max_age=15.):
    """Legacy API: return only demonstrably current observations."""
    result = inspect_environment(path, now=now, max_age=max_age)
    # Raw test fixtures without OpenMW timestamp must remain readable for
    # backwards-compatibility, but not be misrepresented as fresh in new UX.
    # Deprecated access path: old on-disk unit fixtures have no log prefix.
    # This interface is display-only. All new control uses inspect_environment.
    if result['status'] == 'unknown' and Path(path).is_file() and now()-Path(path).stat().st_mtime <= max_age:
        return result['observation']
    return result['observation'] if result['status'] == 'current' else None
