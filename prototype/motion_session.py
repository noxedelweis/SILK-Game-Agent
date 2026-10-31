"""Operator-approved OpenMW first-step with grounded SILK_OBS_V03 verification.

No autonomous loops, save edits, or modification of OpenMW installations.
"""
from __future__ import annotations
import math, os, re, time
from dataclasses import dataclass
from pathlib import Path
from openmw_motion import StepController, Win32Backend, ControlRejected

MARKER = re.compile(
    r'SILK_OBS_V03\|(\d+)\|([^|\r\n]{1,90})\|'
    r'(-?(?:\d+(?:\.\d+)?|\.\d+))\|(-?(?:\d+(?:\.\d+)?|\.\d+))\|'
    r'(-?(?:\d+(?:\.\d+)?|\.\d+))\|(-?(?:\d+(?:\.\d+)?|\.\d+))(?=\s|$)')

@dataclass(frozen=True)
class Sample:
    seq: int
    cell: str
    x: float
    y: float
    z: float
    health: float

def parse_line(line: str) -> Sample | None:
    m = MARKER.search(line)
    if m is None:
        return None
    seq, vals = int(m.group(1)), [float(m.group(i)) for i in range(3, 7)]
    if seq > 1_000_000_000 or not all(map(math.isfinite, vals)):
        return None
    if any(abs(x)>1e9 for x in vals[:3]):
        return None
    return Sample(seq,m.group(2),*vals)

def newest_sample(path: Path) -> Sample | None:
    with Path(path).open('rb') as f:
        f.seek(0,os.SEEK_END)
        f.seek(max(0,f.tell()-131072))
        data=f.read(131072)
    rows=data.splitlines()
    if data and not data.endswith((b'\n',b'\r')):
        rows=rows[:-1]
    for row in reversed(rows):
        sample=parse_line(row.decode('utf-8',errors='replace'))
        if sample:
            return sample
    return None

def observe_movement(before: Sample, after: Sample) -> dict:
    if after.seq <= before.seq:
        return {'verified':False,'reason':'No new telemetry sequence'}
    if after.cell != before.cell:
        return {'verified':False,'reason':'Cell changed; coordinate comparison invalid'}
    d=math.dist((before.x,before.y,before.z),(after.x,after.y,after.z))
    if d<1.0:
        return {'verified':False,'reason':'No observable displacement','distance_units':round(d,2)}
    return {'verified':True,'distance_units':round(d,2),'cell':after.cell,
            'evidence':'OpenMW player coordinates differ before and after the command',
            'attribution':'Command causality inferred, not independently proved'}

def step_once(log_path: Path, *, backend=None, sleeper=time.sleep, clock=time.monotonic,
              wallclock=time.time, switch_seconds=4.0, verify_seconds=9.0,
              sample_reader=newest_sample, confirm=False) -> dict:
    if not confirm:
        raise ControlRejected('Explicit confirmation required')
    log_path=Path(log_path)
    if not log_path.is_file():
        raise ControlRejected('Missing OpenMW log and SILK_OBS_V03 probe')
    if wallclock()-log_path.stat().st_mtime>20:
        raise ControlRejected('Stale telemetry; OpenMW probe must be live')
    before=sample_reader(log_path)
    if before is None:
        raise ControlRejected('No SILK_OBS_V03 coordinate observations')
    backend=backend or Win32Backend()
    end=clock()+switch_seconds
    while clock()<end:
        if backend.is_emergency_stop():
            raise ControlRejected('Cancelled by ESC before movement')
        sleeper(min(.05,max(.001,end-clock())))
    latest=sample_reader(log_path) or before
    if latest.seq>before.seq and (latest.cell!=before.cell or
        math.dist((before.x,before.y,before.z),(latest.x,latest.y,latest.z))>=1):
        raise ControlRejected('Player moved during countdown; attribution ambiguous')
    if not backend.is_openmw_foreground():
        raise ControlRejected('OpenMW must be the foreground window')
    StepController(backend,sleeper=sleeper,clock=clock).forward(.20,confirm=True)
    deadline=clock()+verify_seconds
    last=latest
    while clock()<deadline:
        if not backend.is_openmw_foreground() or backend.is_emergency_stop():
            break
        newer=sample_reader(log_path)
        if newer and newer.seq>latest.seq:
            last=newer
            result=observe_movement(latest,newer)
            if result['verified']:
                return {'command_sent':True,'command':'W / 0.20s','telemetry':result,
                        'before_seq':latest.seq,'after_seq':newer.seq}
        sleeper(.20)
    return {'command_sent':True,'command':'W / 0.20s',
            'telemetry':observe_movement(latest,last),
            'before_seq':latest.seq,'after_seq':last.seq}
