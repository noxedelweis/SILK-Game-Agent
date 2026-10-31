"""Locate OpenMW telemetry using the installed agent implementation."""
from __future__ import annotations
import sys
from pathlib import Path

def find_openmw_log(active: Path):
    folder=str(active)
    sys.path.insert(0,folder)
    try:
        from observer.logreader import find_log
        return find_log()
    finally:
        sys.path.remove(folder)
