"""Build updater-compatible SILK agent archives without changing code bytes.

The SILK updater rejects ZIP entries tagged only with POSIX permissions (0600)
without a file-type bit. We always mark files as S_IFREG | 0644, preserve their
content, and fail on links, invalid names and duplicate paths.
"""
from __future__ import annotations

import argparse
import os
import stat
import tempfile
import zipfile
from pathlib import Path


def rebuild(source: Path, destination: Path, old_root: str, new_root: str) -> None:
    if not old_root.startswith('SILK_Game_Agent_v') or not new_root.startswith('SILK_Game_Agent_v'):
        raise ValueError('Versioned SILK archive directories required')
    source=Path(source).resolve(strict=True)
    destination=Path(destination).resolve()
    if source == destination:
        raise ValueError('Refusing to overwrite source archive')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path=tempfile.mkstemp(prefix='.silkzip-',suffix='.zip',dir=destination.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(source) as src, zipfile.ZipFile(temp_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as out:
            seen=set()
            for item in src.infolist():
                path=item.filename
                if item.is_dir():
                    continue
                if '\\' in path or '\x00' in path or not path.startswith(old_root+'/'):
                    raise ValueError('Unexpected archive path: '+repr(path))
                parts=path.split('/')
                if any(not p or p in ('.','..') or p.endswith((' ','.')) or any(c in p for c in '<>:"|?*') for p in parts):
                    raise ValueError('Unsafe archive path: '+repr(path))
                mode=item.external_attr>>16
                if stat.S_IFMT(mode) not in (0,stat.S_IFREG):
                    raise ValueError('Refusing symlink or special ZIP member: '+path)
                renamed=new_root+'/'+path[len(old_root)+1:]
                if renamed.casefold() in seen:
                    raise ValueError('Duplicate archive entry: '+renamed)
                seen.add(renamed.casefold())
                entry=zipfile.ZipInfo(renamed,item.date_time)
                entry.create_system=3
                entry.compress_type=zipfile.ZIP_DEFLATED
                entry.external_attr=(stat.S_IFREG|0o644)<<16
                out.writestr(entry,src.read(item))
        # Validate the output with the same mode semantics as installed SILK updaters.
        with zipfile.ZipFile(temp_path) as result:
            if result.testzip() is not None:
                raise ValueError('Damaged output ZIP')
            if not result.infolist() or not all(stat.S_ISREG(i.external_attr>>16) for i in result.infolist()):
                raise ValueError('ZIP member type validation failed')
        os.replace(temp_path,destination)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--old-root',required=True)
    parser.add_argument('--new-root',required=True)
    args=parser.parse_args()
    rebuild(args.source,args.destination,args.old_root,args.new_root)
