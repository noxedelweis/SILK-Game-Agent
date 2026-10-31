"""GitHub-authenticated GUI EXE updater; the replacement runs outside the old EXE.

No automatic launch from background polling: only the explicit GUI Update action.
Only no-auth public GitHub release binaries with pinned repo, release version,
exact asset name, size and SHA-256 digest are accepted. No arbitrary URLs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile
from pathlib import Path
from updater import GitHubReleases, sha256

REPO = 'noxedelweis/SILK-Game-Agent'
HOST_FILENAME = 'SILK_Game_Agent.exe'
MAX_EXE_BYTES = 75 * 1024 * 1024


def find_host_release(*, client=None):
    client = client or GitHubReleases(REPO)
    agent = client.latest()  # validates latest published, non-prerelease, correct repo+agent zip
    tag = 'v' + '.'.join(map(str, agent['version']))
    api = f'https://api.github.com/repos/{REPO}/releases/tags/{urllib.parse.quote(tag, safe="")}'
    with client.opener.open(client._request(api), timeout=12) as resp:
        data = resp.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError('Слишком большой ответ GitHub')
    release = json.loads(data.decode('utf-8'))
    if release.get('tag_name') != tag or release.get('draft') or release.get('prerelease'):
        raise ValueError('Неподходящий GitHub Release')
    assets = [a for a in release.get('assets', ()) if a.get('name') == HOST_FILENAME]
    if not assets:  # Older releases only contain the agent; that is fine.
        return None
    if len(assets) != 1:
        raise ValueError('Неоднозначный EXE в GitHub Release')
    asset = assets[0]
    digest = asset.get('digest', '')
    size = asset.get('size')
    url = asset.get('browser_download_url', '')
    expected = f'https://github.com/{REPO}/releases/download/{tag}/{HOST_FILENAME}'
    if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
        raise ValueError('Для EXE отсутствует подтверждённый SHA-256 digest')
    if type(size) is not int or not 2048 <= size <= MAX_EXE_BYTES:
        raise ValueError('Неверный размер EXE')
    if url != expected or asset.get('state') not in (None, 'uploaded'):
        raise ValueError('Ссылка на EXE не соответствует опубликованному релизу')
    return {'version': agent['version'], 'sha256': digest.split(':', 1)[1].lower(),
            'size': size, 'url': url, 'filename': HOST_FILENAME}


def valid_pe_file(path: Path):
    """Reject clearly invalid/non-x64 PE payloads (not a substitute for trust)."""
    with Path(path).open('rb') as f:
        if f.read(2) != b'MZ':
            raise ValueError('Не PE-файл: отсутствует MZ')
        f.seek(0x3c)
        offset = int.from_bytes(f.read(4), 'little')
        if not 0x40 <= offset <= 1024 * 1024:
            raise ValueError('Некорректный заголовок PE')
        f.seek(offset)
        if f.read(4) != b'PE\0\0' or f.read(2) != b'\x64\x86':
            raise ValueError('Требуется 64-разрядный Windows EXE')
    return True


def download_host(release: dict, home: Path, *, client=None) -> Path:
    client = client or GitHubReleases(REPO)
    dest = Path(home) / '_system' / 'host_staging'
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / ('SILK_Game_Agent_v' + '.'.join(map(str, release['version'])) + '.exe')
    if target.is_file() and sha256(target) == release['sha256']:
        valid_pe_file(target)
        return target
    if target.exists():
        raise ValueError('Существующий пакет EXE отличается от опубликованного — не заменяю')
    fd, name = tempfile.mkstemp(prefix='.host_', suffix='.part', dir=dest)
    try:
        h = hashlib.sha256()
        count = 0
        with os.fdopen(fd, 'wb') as out:
            with client.opener.open(client._request(release['url']), timeout=25) as response:
                while True:
                    piece = response.read(1024 * 1024)
                    if not piece:
                        break
                    count += len(piece)
                    if count > release['size'] or count > MAX_EXE_BYTES:
                        raise ValueError('EXE больше допустимого размера')
                    h.update(piece)
                    out.write(piece)
            out.flush()
            os.fsync(out.fileno())
        if count != release['size'] or h.hexdigest() != release['sha256']:
            raise ValueError('Контроль SHA-256/размера EXE не пройден')
        valid_pe_file(Path(name))
        os.replace(name, target)
        return target
    finally:
        if os.path.exists(name):
            os.unlink(name)


def schedule_host_update(target_exe: Path, downloaded_exe: Path, digest: str, home: Path) -> None:
    """Spawn detached separate Python helper; GUI parent must exit (42)."""
    target_exe = Path(target_exe).resolve(strict=True)
    if target_exe.suffix.lower() != '.exe' or target_exe.name not in (
        'SILK_Game_Agent.exe', 'SILK_Game_Agent_UTF8_Fix.exe'):
        raise ValueError('Неожиданное имя запускаемого файла SILK')
    if sha256(downloaded_exe) != digest:
        raise ValueError('Проверка EXE перед установкой не пройдена')
    root = Path(home) / '_system'
    root.mkdir(parents=True, exist_ok=True)
    # Read helper from the currently verified embedded zipapp, not an internet script.
    with zipfile.ZipFile(sys.argv[0]) as bundle:
        source = bundle.read('host_update_helper.py')
    helper = root / 'host_update_helper.py'
    tmp = helper.with_suffix('.tmp')
    tmp.write_bytes(source)
    os.replace(tmp, helper)
    args = [sys.executable, str(helper), '--target', str(target_exe), '--staged', str(downloaded_exe),
            '--sha256', digest, '--root', str(home), '--parent-pid', str(os.getppid())]
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    subprocess.Popen(args, creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)


def maybe_rollback_host(target_exe: str, home: Path) -> bool:
    if not target_exe:
        return False
    backup = Path(home) / '_system' / 'host_backups' / 'previous_host.exe'
    if not backup.is_file():
        print('Резервной копии оболочки EXE ещё нет; восстановлены только компоненты агента')
        return False
    valid_pe_file(backup)
    expected = sha256(backup)
    if sha256(Path(target_exe)) == expected:
        print('Оболочка уже совпадает с резервной копией')
        return False
    schedule_host_update(Path(target_exe), backup, expected, home)
    print('Восстанавливаю предыдущую оболочку EXE...', flush=True)
    return True


def maybe_update_host(target_exe: str, installed_host_version: tuple[int, int, int], home: Path) -> bool:
    if not target_exe:
        print('Хост EXE: не передан путь запуска; обновлены только компоненты агента')
        return False
    release = find_host_release()
    if not release or release['version'] <= installed_host_version:
        print('Оболочка EXE: новая версия не требуется')
        return False
    exe_path = Path(target_exe)
    if not exe_path.is_file():
        raise FileNotFoundError('Не найден исходный EXE')
    staged = download_host(release, home)
    if sha256(exe_path) == release['sha256']:
        print('Оболочка EXE уже актуальна')
        return False
    schedule_host_update(exe_path, staged, release['sha256'], home)
    print('Новая оболочка EXE проверена. Закрываю старую версию для безопасной замены...', flush=True)
    return True
