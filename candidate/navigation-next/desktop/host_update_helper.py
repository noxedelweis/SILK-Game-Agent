"""Detached Windows host-swapping helper. No 3rd-party dependencies.

The live EXE cannot atomically replace itself on Windows; this short-lived
helper waits for it to exit, backs up the old file outside the desktop,
verifies the downloaded PE, replaces it on the same volume and relaunches.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1024*1024), b''):
            h.update(part)
    return h.hexdigest()


def swap_host(target, staged, expected_sha, root, *, launcher=None, sleep=time.sleep,
              attempts=80, pause=0.25):
    """Transactional replacement; rolls back if replacement/relaunch fails."""
    target=Path(target).resolve(strict=True)
    staged=Path(staged).resolve(strict=True)
    root=Path(root).resolve()
    if target.suffix.lower()!='.exe' or target.name not in ('SILK_Game_Agent.exe','SILK_Game_Agent_UTF8_Fix.exe'):
        raise ValueError('Целевой путь не является SILK Game Agent EXE')
    if not expected_sha or len(expected_sha)!=64 or digest(staged)!=expected_sha:
        raise ValueError('Контрольная сумма нового EXE не совпадает')
    fromdir=root/'_system'/'host_backups'
    fromdir.mkdir(parents=True,exist_ok=True)
    backup=fromdir/'previous_host.exe'
    # Temp on the exact same volume as target, necessary for os.replace on Windows.
    neighboring=target.with_name('.SILK_Game_Agent.pending.exe')
    if neighboring.exists():
        raise FileExistsError('Найден незавершённый временный EXE: '+str(neighboring))
    history=fromdir/'last_swap.json'
    launcher=launcher or (lambda executable: subprocess.Popen([str(executable)], close_fds=True))
    shutil.copy2(staged,neighboring)
    try:
        if digest(neighboring)!=expected_sha:
            raise ValueError('Ошибка копирования обновления')
        # Old executable remains untouched until file unlock; tolerate Windows locks.
        last=None
        for _ in range(attempts):
            try:
                shutil.copy2(target, backup)
                os.replace(neighboring,target)
                last=None
                break
            except PermissionError as exc:
                last=exc
                sleep(pause)
        if last is not None:
            raise last
        try:
            process=launcher(target)
            if process is None:
                raise RuntimeError('Не удалось запустить обновлённое приложение')
        except Exception:
            # The previous host backup is always preserved in LOCALAPPDATA.
            os.replace(backup,target)
            raise
        history.write_text(json.dumps({'target':str(target),'new_sha256':expected_sha,
            'backup':str(backup),'status':'launched'},ensure_ascii=False,indent=2),encoding='utf-8')
        return {'status':'launched','target':str(target),'backup':str(backup)}
    finally:
        if neighboring.exists():
            neighboring.unlink()


def main():
    p=argparse.ArgumentParser()
    for key in ('target','staged','sha256','root'):
        p.add_argument('--'+key,required=True)
    p.add_argument('--parent-pid',default='0')
    args=p.parse_args()
    root=Path(args.root)
    logfile=root/'_system'/'last_host_update.log'
    try:
        result=swap_host(args.target,args.staged,args.sha256,root)
        logfile.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0
    except Exception as e:
        logfile.write_text('ERROR: '+str(e),encoding='utf-8')
        return 1

if __name__=='__main__':
    sys.exit(main())
