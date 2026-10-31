"""SILK Game Agent Updater v0.2: local + GitHub Releases, transactional, stdlib.

No operations against Steam, OpenMW, openmw.cfg, live mods, or SILK Desktop.
Use only packages from sources you trust; sha256 detects corruption, not authorship.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse
import urllib.error
import zipfile
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path

APP_PREFIX = 'SILK_Game_Agent_v'
APP_RE = re.compile(r'^SILK_Game_Agent_v(\d+)\.(\d+)\.(\d+)$')
ARCHIVE_RE = re.compile(r'^SILK_Game_Agent_v(\d+)\.(\d+)\.(\d+)\.zip$')
MAX_FILES = 1000
MAX_BYTES = 100 * 1024 * 1024
DB_REL = Path('knowledge_data') / 'morrowind.sqlite3'
REQUIRED = ('knowledge_cli.py', 'knowledge/library.py', 'run_tests.bat', 'tests/test_knowledge.py')
# Integrity pin for the release included in this bootstrapper.
BUILTIN_SHA256 = {'0.4.3': '9322e845ad5ed3063eb95710208029e13f29c9fcffb99cc3d4173383fcc76d80'}
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
GITHUB_ALLOWED_HOSTS = frozenset({'github.com', 'api.github.com', 'release-assets.githubusercontent.com',
                                   'objects.githubusercontent.com', 'github-releases.githubusercontent.com'})
GITHUB_REPO_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}$')


def version_of_dir(name: str) -> tuple[int, int, int] | None:
    match = APP_RE.fullmatch(name)
    return tuple(map(int, match.groups())) if match else None


def version_of_archive(name: str) -> tuple[int, int, int] | None:
    match = ARCHIVE_RE.fullmatch(name)
    return tuple(map(int, match.groups())) if match else None


def version_str(version: tuple[int, int, int]) -> str:
    return '.'.join(map(str, version))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_db_count(path: Path) -> int:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError('Нет базы знаний: ' + str(path))
    uri = path.resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        check = conn.execute('PRAGMA quick_check').fetchone()[0]
        if check != 'ok':
            raise ValueError('Проверка SQLite не пройдена: ' + str(check))
        count = int(conn.execute('SELECT COUNT(*) FROM pages').fetchone()[0])
    if count < 1:
        raise ValueError('База знаний не содержит статей')
    return count


def backup_db(source: Path, target: Path) -> int:
    """Online SQLite backup, consistent even if source is in WAL mode."""
    expected = safe_db_count(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError('Не перезаписываю базу: ' + str(target))
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                dst.commit()
        actual = safe_db_count(target)
        if actual != expected:
            raise RuntimeError(f'В базе стало {actual} статей вместо {expected}')
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return expected


def _valid_member(info: zipfile.ZipInfo, expected: str) -> tuple[str, ...]:
    path = info.filename
    if not path or path.startswith('/') or '\\' in path or '\x00' in path:
        raise ValueError('Опасный путь в архиве: ' + repr(path))
    parts = path.rstrip('/').split('/')
    if parts[0] != expected or any(p in ('', '.', '..') for p in parts):
        raise ValueError('Неправильная структура ZIP: ' + repr(path))
    # Windows filename restrictions, casefold ambiguity, trailing dots/spaces.
    for part in parts:
        if any(x in part for x in '<>:"|?*') or part.endswith((' ', '.')):
            raise ValueError('Недопустимое имя файла: ' + repr(part))
        if part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(n) for n in range(1, 10)), *('LPT'+str(n) for n in range(1, 10))}:
            raise ValueError('Зарезервированное имя Windows: ' + repr(part))
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode) or (mode and not stat.S_ISREG(mode) and not stat.S_ISDIR(mode)):
        raise ValueError('Ссылки и специальные файлы в ZIP запрещены: ' + path)
    return tuple(parts)


def safe_extract(archive: Path, dest_root: Path, name: str) -> Path:
    """Extract only code under exactly one expected version directory."""
    out = dest_root / name
    seen: set[str] = set()
    total = 0
    count = 0
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            parts = _valid_member(info, name)
            if info.is_dir():
                continue
            count += 1
            total += info.file_size
            if count > MAX_FILES or total > MAX_BYTES:
                raise ValueError('Архив превышает лимит числа или объёма файлов')
            if len(parts) < 2:
                raise ValueError('Файл в корне архива вместо папки версии')
            lower = '/'.join(parts).casefold()
            if lower in seen:
                raise ValueError('Дублирующиеся имена в ZIP: ' + info.filename)
            seen.add(lower)
            path = dest_root.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as inp, path.open('xb') as dst:
                shutil.copyfileobj(inp, dst)
    if count == 0:
        raise ValueError('В архиве нет файлов')
    require_code(out)
    return out


def require_code(folder: Path) -> None:
    if folder.is_symlink() or not folder.is_dir():
        raise RuntimeError('Версия отсутствует или содержит ссылку: ' + str(folder))
    for rel in REQUIRED:
        f = folder / rel
        if not f.is_file() or f.is_symlink():
            raise RuntimeError(f'Нет обязательного файла {rel} в {folder}')


def run_self_tests(folder: Path) -> str:
    result = subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'],
        cwd=str(folder), text=True, encoding='utf-8', errors='replace',
        capture_output=True, timeout=120,
    )
    log = (result.stdout + '\n' + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError('Автотесты новой версии не пройдены:\n' + log[-6000:])
    return log[-3000:]


def parse_github_repo(text: str) -> str:
    """Only explicit public GitHub owner/repo URLs. No arbitrary HTTP endpoints."""
    text = text.strip()
    if text.startswith('https://github.com/'):
        parsed = urllib.parse.urlparse(text)
        if parsed.netloc != 'github.com' or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('Допустим только прямой адрес https://github.com/OWNER/REPO')
        text = parsed.path.strip('/')
    if text.endswith('.git'):
        text = text[:-4]
    if not GITHUB_REPO_RE.fullmatch(text) or any(x in text for x in ('..', '//')):
        raise ValueError('Укажи OWNER/REPO или https://github.com/OWNER/REPO')
    return text


class _GitHubOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlsplit(newurl)
        if u.scheme != 'https' or u.hostname not in GITHUB_ALLOWED_HOSTS or u.username or u.password or u.port not in (None, 443):
            raise ValueError('Неожиданный адрес перенаправления загрузки GitHub')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class GitHubReleases:
    """Fetches official GitHub Releases; publisher's repository is a trust boundary."""
    def __init__(self, repo: str, opener=None):
        self.repo = parse_github_repo(repo)
        self.opener = opener or urllib.request.build_opener(_GitHubOnlyRedirect())

    def _request(self, url: str):
        u = urllib.parse.urlsplit(url)
        if u.scheme != 'https' or u.hostname not in GITHUB_ALLOWED_HOSTS or u.username or u.password or u.port not in (None, 443):
            raise ValueError('Запрещённый источник обновления')
        return urllib.request.Request(url, headers={'User-Agent': 'SILK-Game-Agent-Updater/0.2',
                                                      'Accept': 'application/vnd.github+json'})

    def latest(self) -> dict:
        api = f'https://api.github.com/repos/{self.repo}/releases/latest'
        with self.opener.open(self._request(api), timeout=12) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('Ответ GitHub слишком большой')
        obj = json.loads(raw.decode('utf-8'))
        if not isinstance(obj, dict) or obj.get('draft') or obj.get('prerelease'):
            raise ValueError('Нет подходящего опубликованного релиза')
        tag = str(obj.get('tag_name', ''))
        match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', tag)
        if not match:
            raise ValueError('Тег релиза должен быть vX.Y.Z')
        version = tuple(map(int, match.groups()))
        filename = APP_PREFIX + version_str(version) + '.zip'
        assets = [a for a in obj.get('assets', []) if isinstance(a, dict) and a.get('name') == filename]
        if len(assets) != 1:
            raise ValueError(f'В последнем релизе нет ровно одного {filename}')
        asset = assets[0]
        digest = asset.get('digest', '')
        if not isinstance(digest, str) or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
            raise ValueError('GitHub не предоставил SHA256 digest — автоматическая установка запрещена')
        size = asset.get('size')
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_DOWNLOAD_BYTES:
            raise ValueError('Недопустимый размер пакета')
        url = str(asset.get('browser_download_url', ''))
        expected = f'https://github.com/{self.repo}/releases/download/{urllib.parse.quote(tag, safe="")}/{filename}'
        if url != expected:
            raise ValueError('URL релиза не соответствует выбранному GitHub репозиторию')
        if asset.get('state') not in (None, 'uploaded'):
            raise ValueError('Архив релиза ещё не опубликован')
        return {'repo': self.repo, 'version': version, 'filename': filename,
                'sha256': digest.split(':', 1)[1].lower(), 'size': size, 'url': url}

    def download(self, release: dict, updates_dir: Path) -> Path:
        """Atomic streamed download; no install until hash and byte count validated."""
        updates_dir.mkdir(parents=True, exist_ok=True)
        target = updates_dir / release['filename']
        digest_file = updates_dir / (release['filename'] + '.sha256')
        if target.exists():
            if sha256(target) != release['sha256']:
                raise ValueError('Существующий архив с этим именем отличается от релиза. Не перезаписываю')
            # Even a cached package must have an authenticated API digest.
            digest_file.write_text(release['sha256'] + '  ' + release['filename'] + '\n', encoding='ascii')
            return target
        fd, tempname = tempfile.mkstemp(prefix='.silk_download_', suffix='.part', dir=str(updates_dir))
        try:
            got_bytes = 0
            h = hashlib.sha256()
            with os.fdopen(fd, 'wb') as f:
                with self.opener.open(self._request(release['url']), timeout=20) as response:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        got_bytes += len(block)
                        if got_bytes > MAX_DOWNLOAD_BYTES or got_bytes > release['size']:
                            raise ValueError('Файл превышает ожидаемый размер')
                        h.update(block)
                        f.write(block)
                f.flush()
                os.fsync(f.fileno())
            if got_bytes != release['size'] or h.hexdigest() != release['sha256']:
                raise ValueError('Контроль размера или SHA256 скачанного ZIP не пройден')
            if target.exists():
                raise FileExistsError('Пакет появился во время загрузки; не перезаписываю')
            os.replace(tempname, target)
            digest_file.write_text(release['sha256'] + '  ' + release['filename'] + '\n', encoding='ascii')
            return target
        finally:
            if os.path.exists(tempname):
                os.unlink(tempname)


class Updater:
    def __init__(self, home: Path, root: Path | None = None):
        self.home = Path(home).resolve()
        self.root = Path(root).resolve() if root else self.home.parent
        self.updates = self.home / 'updates'
        self.statefile = self.home / 'state.json'
        self.sourcefile = self.home / 'source.json'
        self.online_statusfile = self.home / 'online_status.json'
        if self.root == self.home:
            raise ValueError('Папка версий не может совпадать с папкой обновлятора')

    def source(self) -> str | None:
        if not self.sourcefile.is_file():
            return None
        obj = json.loads(self.sourcefile.read_text(encoding='utf-8'))
        if not isinstance(obj, dict) or not isinstance(obj.get('repo'), str):
            raise ValueError('Повреждён source.json')
        return parse_github_repo(obj['repo'])

    def configure_source(self, repo: str) -> dict:
        repo = parse_github_repo(repo)
        self.home.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.source-', suffix='.tmp', dir=str(self.home))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump({'repo': repo}, f, ensure_ascii=False, indent=2)
            os.replace(temp, self.sourcefile)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        self.online_statusfile.unlink(missing_ok=True)
        return {'status': 'source_configured', 'repo': repo, 'note': 'Trusted only if this is YOUR repository'}

    def check_online(self, download: bool = False) -> dict:
        repo = self.source()
        if not repo:
            return {'status': 'not_configured', 'hint': 'Запусти configure_source.bat и укажи свой GitHub OWNER/REPO'}
        gh = GitHubReleases(repo)
        release = gh.latest()
        current = self.active()
        now = version_of_dir(current.name) if current else (-1, -1, -1)
        fresh = release['version'] > now
        info = {'status': 'available' if fresh else 'up_to_date', 'repo': repo,
                'remote_version': version_str(release['version']),
                'active': current.name if current else None,
                'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                'downloaded': False}
        if fresh and download:
            package = gh.download(release, self.updates)
            info['downloaded'] = True
            info['package'] = str(package)
        self.home.mkdir(parents=True, exist_ok=True)
        self.online_statusfile.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
        return info

    def offer_update(self, confirm=None) -> dict:
        """Offer installation of a previously downloaded release, for interactive launchers."""
        if not self.online_statusfile.is_file():
            return {'status': 'no_downloaded_update'}
        state = json.loads(self.online_statusfile.read_text(encoding='utf-8'))
        version = str(state.get('remote_version', ''))
        if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not state.get('downloaded'):
            return {'status': 'no_downloaded_update'}
        active = self.active()
        now = version_of_dir(active.name) if active else (-1, -1, -1)
        target_version = tuple(map(int, version.split('.')))
        if target_version <= now:
            return {'status': 'already_current'}
        package = self.updates / (APP_PREFIX + version + '.zip')
        if not package.is_file():
            return {'status': 'not_downloaded'}
        self.validate_package_hash(package)
        if confirm is None:
            decision = input(f'Доступна SILK Game Agent v{version}. Установить сейчас? [y/N]: ').strip().lower()
            accepted = decision in ('y', 'yes', 'д', 'да')
        else:
            accepted = bool(confirm)
        if not accepted:
            return {'status': 'declined', 'version': version}
        return self.update(package)

    def update_online(self) -> dict:
        repo = self.source()
        if not repo:
            result = self.update()
            result['online'] = 'not_configured'
            return result
        try:
            online = self.check_online(download=True)
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            print('GitHub недоступен: ' + str(exc) + '; пробую только проверенные локальные пакеты')
            result = self.update()
            result['online'] = 'offline_fallback'
            return result
        if online['status'] == 'available':
            result = self.update(Path(online['package']))
            result['online'] = 'downloaded_from_github'
            return result
        result = self.update()
        result['online'] = 'up_to_date_on_github'
        return result

    def installed(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted((p for p in self.root.iterdir() if p.is_dir() and not p.is_symlink() and version_of_dir(p.name)),
                      key=lambda p: version_of_dir(p.name), reverse=True)

    def valid_installed(self) -> list[Path]:
        out = []
        for folder in self.installed():
            try:
                require_code(folder)
                safe_db_count(folder / DB_REL)
            except (OSError, RuntimeError, sqlite3.Error, ValueError):
                continue
            out.append(folder)
        return out

    def state(self) -> dict:
        if self.statefile.exists():
            data = json.loads(self.statefile.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('history'), list):
                raise ValueError('Файл состояния обновлятора повреждён')
            active = data.get('active')
            if active and not version_of_dir(active):
                raise ValueError('Неверное название активной версии')
            return data
        return {'active': None, 'history': []}

    def active(self) -> Path | None:
        name = self.state().get('active')
        if name:
            folder = self.root / name
            require_code(folder)
            safe_db_count(folder / DB_REL)
            return folder
        available = self.valid_installed()
        return available[0] if available else None

    def save_state(self, state: dict) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix='.state-', suffix='.tmp', dir=str(self.home))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, self.statefile)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def local_releases(self) -> list[Path]:
        self.updates.mkdir(parents=True, exist_ok=True)
        return sorted((p for p in self.updates.glob('SILK_Game_Agent_v*.zip') if version_of_archive(p.name) and p.is_file()),
                      key=lambda p: version_of_archive(p.name), reverse=True)

    def pick_release(self, chosen: Path | None = None) -> Path | None:
        if chosen:
            chosen = Path(chosen).resolve(strict=True)
            if not version_of_archive(chosen.name):
                raise ValueError('Имя ZIP должно быть SILK_Game_Agent_vX.Y.Z.zip')
            return chosen
        current = self.active()
        now = version_of_dir(current.name) if current else (-1, -1, -1)
        return next((p for p in self.local_releases() if version_of_archive(p.name) > now), None)

    def validate_package_hash(self, package: Path) -> str:
        got = sha256(package)
        v = version_str(version_of_archive(package.name))
        pinned = BUILTIN_SHA256.get(v)
        sidecar = package.with_name(package.name + '.sha256')
        if pinned and pinned != got:
            raise ValueError(f'SHA256 версии {v} не совпадает с эталоном — установка остановлена')
        if sidecar.is_file():
            expected = sidecar.read_text(encoding='utf-8-sig').split()[0].strip().lower()
            if not re.fullmatch(r'[a-f0-9]{64}', expected) or expected != got:
                raise ValueError('SHA256 архива не совпадает с файлом .sha256')
        elif not pinned:
            raise ValueError('Для внешнего пакета нужен одноимённый файл .zip.sha256. Без него автоустановка запрещена')
        return got

    def _db_source(self, exclude: Path | None = None) -> Path | None:
        active = self.active()
        preferred = ([active] if active else []) + self.valid_installed()
        used: set[Path] = set()
        for folder in preferred:
            if not folder or folder == exclude or folder in used:
                continue
            used.add(folder)
            db = folder / DB_REL
            try:
                safe_db_count(db)
                return db
            except (OSError, ValueError, sqlite3.Error):
                continue
        return None

    def _activate(self, target: Path, previous: Path | None) -> dict:
        old_state = self.state()
        old = previous
        hist = [old.name] if old and old.name != target.name else []
        hist += [x for x in old_state['history'] if x != target.name and x not in hist]
        state = {'active': target.name, 'history': hist,
                 'updated_at_utc': datetime.now(timezone.utc).isoformat()}
        self.save_state(state)
        return {'status': 'active', 'version': target.name, 'pages': safe_db_count(target / DB_REL),
                'previous': old.name if old and old != target else None,
                'rollback_available': bool(hist)}

    def update(self, chosen: Path | None = None, do_tests: bool = True) -> dict:
        package = self.pick_release(chosen)
        if package is None:
            active = self.active()
            if active and self.state().get('active') is None:
                older = next((p for p in self.valid_installed() if version_of_dir(p.name) < version_of_dir(active.name)), None)
                adopted = self._activate(active, older)
                adopted['status'] = 'adopted_existing'
                return adopted
            return {'status': 'up_to_date_or_no_package', 'active': active.name if active else None,
                    'hint': 'Положи следующий SILK_Game_Agent_vX.Y.Z.zip в updates/ вместе с .zip.sha256'}
        version = version_of_archive(package.name)
        name = APP_PREFIX + version_str(version)
        current = self.active()
        if current and version < version_of_dir(current.name):
            raise ValueError('Откат на предыдущую версию выполняется командой rollback, не update')
        self.validate_package_hash(package)
        target = self.root / name
        if target.exists():
            # Safe adoption of a version the user has already unpacked.
            require_code(target)
            db = target / DB_REL
            if not db.exists():
                source = self._db_source(exclude=target)
                if not source:
                    raise RuntimeError('Не найдена исходная SQLite-база; ничего не перезаписано')
                pages = backup_db(source, db)
                print(f'Скопирована база в уже существующую папку: {pages} страниц')
            else:
                safe_db_count(db)
            if do_tests:
                print('Проверка уже существующей версии...')
                print(run_self_tests(target))
            return self._activate(target, current)
        if current and version == version_of_dir(current.name):
            return {'status': 'up_to_date', 'active': current.name}
        self.root.mkdir(parents=True, exist_ok=True)
        # On same filesystem; final os.replace of stage directory is atomic.
        with tempfile.TemporaryDirectory(prefix='.silk_stage_', dir=str(self.root)) as temp:
            stage = safe_extract(package, Path(temp), name)
            source = self._db_source()
            if not source:
                raise RuntimeError('Не найдена существующая SQLite-база: сначала импортируй Morrowind.jsonl в прежней версии')
            pages = backup_db(source, stage / DB_REL)
            print(f'SQLite перенесена резервным копированием: {pages} страниц')
            if do_tests:
                print('Тестирование новой версии...')
                print(run_self_tests(stage))
            require_code(stage)
            safe_db_count(stage / DB_REL)
            # No existing target may be replaced. Detect race best effort.
            if target.exists():
                raise FileExistsError('Папка новой версии уже появилась; повтори обновление')
            stage.rename(target)
        result = self._activate(target, current)
        result['sha256'] = sha256(package)
        return result

    def rollback(self) -> dict:
        state = self.state()
        current = self.active()
        for index, candidate in enumerate(state['history']):
            if candidate == (current.name if current else None) or not version_of_dir(candidate):
                continue
            folder = self.root / candidate
            try:
                require_code(folder)
                safe_db_count(folder / DB_REL)
            except (OSError, ValueError, sqlite3.Error, RuntimeError):
                continue
            history = [current.name] if current else []
            history += [h for i, h in enumerate(state['history']) if i != index and h not in history and h != candidate]
            self.save_state({'active': candidate, 'history': history,
                             'updated_at_utc': datetime.now(timezone.utc).isoformat()})
            return {'status': 'rolled_back', 'active': candidate, 'previous': current.name if current else None}
        raise RuntimeError('Нет пригодной предыдущей версии. Данные не изменены')

    def status(self) -> dict:
        active = self.active()
        return {'active': active.name if active else None,
                'wiki_pages': safe_db_count(active / DB_REL) if active else None,
                'installed_versions': [p.name for p in self.installed()],
                'available_local_packages': [p.name for p in self.local_releases()],
                'rollback_versions': self.state()['history'],
                'updates_dir': str(self.updates),
                'openmw_and_silk_desktop_unchanged': True,
                'release_source': self.source(),
                'last_online_check': json.loads(self.online_statusfile.read_text(encoding='utf-8')) if self.online_statusfile.exists() else None}

    def run(self, what: str) -> int:
        active = self.active()
        if not active:
            raise RuntimeError('Нет активной версии. Сначала запусти update.bat')
        if what in ('search', 'ask'):
            prompt = 'Search Morrowind wiki for: ' if what == 'search' else 'Ask Gemma about Morrowind: '
            query = input(prompt).strip()
            if not query:
                print('Пустой запрос')
                return 1
            args = [sys.executable, str(active / 'knowledge_cli.py'), what, query]
        elif what == 'observer':
            if os.name != 'nt':
                raise RuntimeError('BAT наблюдателя рассчитан на Windows')
            args = ['cmd.exe', '/c', str(active / 'start_observer.bat')]
        elif what == 'tests':
            args = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q']
        else:
            raise ValueError('Действие не поддерживается')
        print('Запускаю из', active)
        return subprocess.call(args, cwd=str(active))


def main(argv=None, home: Path | None = None):
    parser = argparse.ArgumentParser(description='SILK Game Agent Updater v0.2 (GitHub + offline)')
    cmd = parser.add_subparsers(dest='command', required=True)
    upd = cmd.add_parser('update')
    upd.add_argument('--package', type=Path, help='ZIP новой версии (с файлом .zip.sha256)')
    conf = cmd.add_parser('configure-source')
    conf.add_argument('repo', nargs='?', help='OWNER/REPO или https://github.com/OWNER/REPO')
    chk = cmd.add_parser('check-online')
    chk.add_argument('--download', action='store_true', help='Загрузить новый ZIP, но не устанавливать')
    cmd.add_parser('offer-update')
    cmd.add_parser('status')
    cmd.add_parser('rollback')
    run = cmd.add_parser('run')
    run.add_argument('action', choices=['search', 'ask', 'observer', 'tests'])
    args = parser.parse_args(argv)
    app = Updater(home or Path(__file__).resolve().parent)
    if args.command == 'update':
        out = app.update(args.package) if args.package else app.update_online()
    elif args.command == 'configure-source':
        out = app.configure_source(args.repo or input('GitHub OWNER/REPO: ').strip())
    elif args.command == 'check-online':
        out = app.check_online(download=args.download)
    elif args.command == 'offer-update':
        out = app.offer_update()
    elif args.command == 'status':
        out = app.status()
    elif args.command == 'rollback':
        out = app.rollback()
    else:
        return app.run(args.action)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, sqlite3.Error, zipfile.BadZipFile, subprocess.TimeoutExpired, urllib.error.URLError, TimeoutError) as exc:
        print('ОШИБКА ОБНОВЛЕНИЯ:', str(exc), file=sys.stderr)
        sys.exit(1)
