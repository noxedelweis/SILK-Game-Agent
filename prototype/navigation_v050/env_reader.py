"""Tail-only parser for experimental SILK_ENV_V050, never executes data from log."""
from __future__ import annotations
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

LINE = re.compile(r'SILK_ENV_V050\|(\d{1,10})\|([^|\r\n]{0,100})\|(-?[0-9.]+)\|(-?[0-9.]+)\|(-?[0-9.]+)\|(-?[0-9.]+)\|([^|\r\n]{0,800})\|([^|\r\n]{0,800})(?=\s|$)')


def parse_line(line):
    m=LINE.search(line)
    if not m:return None
    try:
        seq=int(m.group(1));position=[float(m.group(i)) for i in range(3,7)]
        from math import isfinite
        if seq>1_000_000_000 or not all(isfinite(x) and abs(x)<1e9 for x in position):return None
        def objects(blob):
            out=[]
            for entry in blob.split(';') if blob else []:
                parts=entry.split('~')
                if len(parts)!=3 or not parts[0]:continue
                x,y=map(float,parts[1:])
                if isfinite(x) and isfinite(y):out.append({'record_id':parts[0],'x':x,'y':y})
            return out[:6]
        return {'seq':seq,'cell':m.group(2),'x':position[0],'y':position[1],
                'z':position[2],'yaw_radians':position[3],
                'doors':objects(m.group(7)),'actors':objects(m.group(8))}
    except (ValueError,OverflowError):return None


def latest_environment(path, *, now=time.time, max_age=15.):
    if now()-Path(path).stat().st_mtime > max_age:
        return None
    with Path(path).open('rb') as fh:
        fh.seek(0,os.SEEK_END);fh.seek(max(0,fh.tell()-131072))
        tail=fh.read(131072)
    for line in reversed(tail.splitlines()):
        parsed=parse_line(line.decode('utf-8',errors='replace'))
        if parsed:return parsed
    return None