"""SILK Game Agent — single-EXE embedded Python application (console backend).

The native launcher embeds this zipapp, all code, updater, and a pinned local
v0.4.4 agent package. Python is already installed on the target user's PC.
All active agent versions and user data reside under LOCALAPPDATA, never in L:\\.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from contextlib import closing

# Windows GUI launcher redirects Python output into a file, which otherwise
# inherits the system ANSI code page (e.g. cp1251). This application prints
# Russian text and Unicode summaries; encode all parent/child output as UTF-8.
# This must run before any installer log is printed.
def _configure_output_encoding():
    os.environ['PYTHONIOENCODING'] = 'utf-8:backslashreplace'
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')

_configure_output_encoding()

from updater import Updater, backup_db, run_self_tests, safe_extract, safe_db_count

REPO='noxedelweis/SILK-Game-Agent'
BUNDLED_VERSION='0.4.5'
PACKAGE_NAME='SILK_Game_Agent_v'+BUNDLED_VERSION+'.zip'
PACKAGE_SHA='178d9326553a4a0d706afd43ba1550e4f35e4b4c289d17cd64d228c4d964594f'


def root_dir():
    override=os.environ.get('SILK_AGENT_HOME')
    if override:
        return Path(override).expanduser().resolve()
    base=os.environ.get('LOCALAPPDATA')
    if not base:
        base=str(Path.home())
    return Path(base)/'SILK Game Agent'


def get_updater():
    root=root_dir()
    return Updater(root/'_system'/'updater', root/'_system'/'versions')


def legacy_candidates():
    explicit=os.environ.get('SILK_LEGACY_DB')
    if explicit:
        yield Path(explicit)
    # The user's historical installation, strictly READ-ONLY during migration.
    for v in ('0.4.4','0.4.3','0.4.2'):
        yield Path(fr'L:\SILK_Game_Agent_v{v}\knowledge_data\morrowind.sqlite3')
    # Support installations next to the EXE, for portability.
    here=Path(sys.argv[0]).resolve().parent
    for parent in (here, here.parent, Path('L:/')):
        for v in ('0.4.4','0.4.3','0.4.2'):
            yield parent/f'SILK_Game_Agent_v{v}'/'knowledge_data'/'morrowind.sqlite3'


def legacy_jsonl():
    direct=os.environ.get('SILK_LEGACY_JSONL')
    if direct:
        yield Path(direct)
    yield Path(r'L:\SILK_Game_Agent_v0.4.2\knowledge\knowledge_data\Morrowind.jsonl')
    yield Path(r'L:\SILK_Game_Agent_v0.4.2\knowledge_data\Morrowind.jsonl')


def extract_pinned_bundle():
    # Zipapp is part of the signed/transported PE payload; still compare
    # pinned version hash to avoid accidental mismatching code.
    with zipfile.ZipFile(sys.argv[0]) as zf:
        data=zf.read('payload/'+PACKAGE_NAME)
    got=hashlib.sha256(data).hexdigest()
    if got != PACKAGE_SHA:
        raise RuntimeError('Встроенный пакет агента не прошёл SHA-256')
    return data


def initialize():
    app=get_updater()
    app.home.mkdir(parents=True,exist_ok=True)
    if not app.source():
        app.configure_source(REPO)
    if app.active():
        return app
    source=None
    for candidate in legacy_candidates():
        if not candidate.is_file():
            continue
        try:
            safe_db_count(candidate)
        except (sqlite3.Error, ValueError, OSError):
            continue
        source=candidate
        break
    data=extract_pinned_bundle()
    app.root.mkdir(parents=True,exist_ok=True)
    name='SILK_Game_Agent_v'+BUNDLED_VERSION
    target=app.root/name
    if target.exists():
        raise RuntimeError('Обнаружена незавершённая установка. Файлы не будут перезаписаны: '+str(target))
    with tempfile.TemporaryDirectory(prefix='.silk_bootstrap_',dir=app.root) as temp:
        temp=Path(temp)
        archive=temp/PACKAGE_NAME
        archive.write_bytes(data)
        stage=safe_extract(archive,temp,name)
        dest=stage/'knowledge_data'/'morrowind.sqlite3'
        if source:
            pages=backup_db(source,dest)
            print(f'База перенесена безопасным копированием: {pages} страниц', flush=True)
        else:
            from importlib.machinery import SourceFileLoader
            target_jsonl=next((p for p in legacy_jsonl() if p.is_file()),None)
            if target_jsonl is None:
                raise RuntimeError('Не нашла старую энциклопедию. Она осталась нетронутой. Ожидалась база: L:\\SILK_Game_Agent_v0.4.2\\knowledge_data\\morrowind.sqlite3')
            # Use the version's own JSONL importer when no previous SQLite exists.
            proc=subprocess.run([sys.executable,str(stage/'knowledge_cli.py'),'import',str(target_jsonl)], cwd=stage, capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=150)
            if proc.returncode:
                raise RuntimeError('Импорт энциклопедии не выполнен: '+proc.stderr[-1000:])
            pages=safe_db_count(dest)
            print(f'Энциклопедия импортирована: {pages} страниц',flush=True)
        print('Проверяю установленный агент...',flush=True)
        print(run_self_tests(stage)[-700:],flush=True)
        stage.rename(target)
    app._activate(target,None)
    return app


def child_process(args,folder,timeout=130):
    result=subprocess.run([sys.executable,*map(str,args)],cwd=str(folder),capture_output=True,encoding='utf-8',errors='replace',timeout=timeout)
    text=(result.stdout+'\n'+result.stderr).strip()
    print(text[:24000] if text else '(нет вывода)')
    if result.returncode:
        raise RuntimeError('Команда завершилась с ошибкой, код '+str(result.returncode))


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['status','update','search','ask','observer','replay','rollback','tests','folder','step','launch','session','session-watch','nav','nav2','probe-install','environment','object-preview','object-nav'])
    p.add_argument('--query-file',default='')
    p.add_argument('--host-exe',default='')
    p.add_argument('--session-id',default='')
    p.add_argument('--experimental-consent',action='store_true')
    args=p.parse_args(argv)
    if args.action=='session-watch':
        from openmw_session import monitor_session
        from observer_import import find_openmw_log
        from motion_session import newest_sample
        folder=root_dir()/'_system'/'session'
        active=get_updater().active()
        return 0 if monitor_session(folder,args.session_id,find_log=lambda:find_openmw_log(active)) else 1
    if args.action=='folder':
        print(root_dir()); return 0
    app=initialize()
    active=app.active()
    if args.action=='status':
        st=app.status()
        print('SILK GAME AGENT — ЕДИНОЕ ПРИЛОЖЕНИЕ')
        print('Активная версия:',st['active'])
        print('Статей энциклопедии:',st['wiki_pages'])
        print('Обновления:',st['release_source'])
        print('Рабочая папка:',root_dir())
        print('OpenMW: сеанс запускается одной кнопкой, телеметрия проверяется автоматически. Управление требует отдельного разрешения.')
    elif args.action=='update':
        current=app.active()
        print('Проверяю GitHub Releases...',flush=True)
        res=app.update_online()
        print(json.dumps(res,ensure_ascii=False,indent=2),flush=True)
        from host_update import maybe_update_host
        if maybe_update_host(args.host_exe,(0,5,1),root_dir()):
            return 42
    elif args.action=='rollback':
        print(json.dumps(app.rollback(),ensure_ascii=False,indent=2),flush=True)
        if args.host_exe:
            from host_update import maybe_rollback_host
            if maybe_rollback_host(args.host_exe,root_dir()):
                return 42
    elif args.action=='nav':
        from micro_nav import guarded_navigation, parse_offset
        from openmw_motion import ControlRejected
        from observer_import import find_openmw_log
        if not args.query_file:
            raise ControlRejected('Укажи смещение X,Y: например 35,15')
        offset = parse_offset(Path(args.query_file).read_text(encoding='utf-8').strip())
        found = find_openmw_log(active)
        if found is None:
            raise ControlRejected('Не найден OpenMW.log с SILK_OBS_V03; движение запрещено')
        result = guarded_navigation(found, offset, confirm=True)
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    elif args.action=='nav2':
        from nav_v2 import navigation_v2, parse_waypoints
        from openmw_motion import ControlRejected
        from observer_import import find_openmw_log
        if not args.query_file:
            raise ControlRejected('Введи относительные точки: 35,15; 60,15; 60,-20')
        points=parse_waypoints(Path(args.query_file).read_text(encoding='utf-8').strip())
        found=find_openmw_log(active)
        if found is None:
            raise ControlRejected('OpenMW.log не найден. Сначала подключи игровую сессию.')
        result=navigation_v2(found,points,confirm=True)
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    elif args.action=='probe-install':
        from env_probe import install_probe
        print(json.dumps(install_probe(root_dir(),confirm=True),ensure_ascii=False,indent=2),flush=True)
    elif args.action=='environment':
        from env_reader import inspect_environment
        from observer_import import find_openmw_log
        log=find_openmw_log(active)
        if log is None:
            raise RuntimeError('Сначала запусти OpenMW и загрузи персонажа')
        snapshot=inspect_environment(log)
        print('СОСТОЯНИЕ СРЕДЫ OPENMW:',flush=True)
        print(json.dumps(snapshot,ensure_ascii=False,indent=2),flush=True)
        if snapshot['status']=='missing':
            from env_diagnostics import diagnose
            print('ДИАГНОСТИКА ЗОНДА:',flush=True)
            print(json.dumps(diagnose(root_dir(),log),ensure_ascii=False,indent=2),flush=True)
            raise RuntimeError('В журнале нет данных расширенного зонда')
        if snapshot['status'] != 'current':
            print('ВНИМАНИЕ: данные можно изучать, но управлять персонажем по ним нельзя.',flush=True)
    elif args.action in ('object-preview','object-nav'):
        from object_nav import plan_door_approach, navigate_to_door
        from env_reader import inspect_environment
        from observer_import import find_openmw_log
        from openmw_motion import ControlRejected
        log=find_openmw_log(active)
        if log is None:
            raise ControlRejected('Не найден журнал OpenMW')
        index_text=Path(args.query_file).read_text('utf-8').strip() if args.query_file else ''
        if not index_text.isdigit() or len(index_text)>2:
            raise ControlRejected('Для выбора ближайшей двери введи её индекс: 0, 1, 2 ...')
        index=int(index_text)
        snapshot=inspect_environment(log)
        if args.action=='object-preview':
            if snapshot['status'] not in ('current','stale','unknown'):
                raise ControlRejected('Нет записей SILK_ENV_V050')
            # A stale observation can be inspected but never used to produce
            # a movement-ready plan. Make the data state explicit.
            if snapshot['status']!='current':
                print(json.dumps({'status':'read_only', 'freshness':snapshot['status'],
                    'observation':snapshot['observation'],
                    'message':'Последнее наблюдение устарело: открой OpenMW и повтори осмотр'},
                    ensure_ascii=False,indent=2),flush=True)
            else:
                print(json.dumps(plan_door_approach(snapshot,index),ensure_ascii=False,indent=2),flush=True)
        else:
            if not args.experimental_consent:
                raise ControlRejected('Экспериментальное движение к объекту требует отдельного подтверждения')
            print('ЭКСПЕРИМЕНТАЛЬНЫЙ ПОДХОД К ДВЕРИ. Нажми ESC для остановки.',flush=True)
            print(json.dumps(navigate_to_door(log,index,confirm=True),ensure_ascii=False,indent=2),flush=True)
    elif args.action=='step':
        from motion_session import step_once
        from openmw_motion import ControlRejected
        from observer_import import find_openmw_log
        found = find_openmw_log(active)
        if found is None:
            raise ControlRejected('Не найден журнал OpenMW. Проверь запуск игры и моста Lua.')
        result = step_once(found,confirm=True)
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    elif args.action=='session':
        from openmw_session import start_session
        result=start_session(root_dir(),active)
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
        print('Управление персонажем ВЫКЛЮЧЕНО. Оно разрешается отдельно.',flush=True)
    elif args.action=='launch':
        from openmw_launch import launch_openmw
        result=launch_openmw()
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        print('SILK: наблюдение становится доступно при поступлении SILK_OBS_V03 из игры.\n'
              'Управление персонажем без разрешения не включается.', flush=True)
    elif args.action=='tests':
        print(run_self_tests(active))
    elif args.action in ('search','ask'):
        if not args.query_file:
            raise ValueError('Нужно указать вопрос в поле интерфейса')
        question=Path(args.query_file).read_text(encoding='utf-8').strip()
        if not question:
            raise ValueError('Введите запрос или вопрос в верхнее поле')
        print('Вопрос: '+question,flush=True)
        child_process([active/'knowledge_cli.py',args.action,question],active,timeout=150)
    elif args.action=='replay':
        child_process([active/'run_observer.py','--replay','--no-ai'],active,timeout=120)
    elif args.action=='observer':
        print('Читаю OpenMW.log. Закрой консоль или нажми Ctrl+C для остановки.',flush=True)
        proc=subprocess.run([sys.executable,str(active/'run_observer.py'),'--model','gemma4:12b-it-q4_K_M','--ai-interval','60','--max-ai-calls','30'],cwd=active)
        return proc.returncode
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('ОШИБКА:',str(exc),file=sys.stderr,flush=True)
        sys.exit(1)
