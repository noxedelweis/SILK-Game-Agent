"""Inspect an installed read-only OpenMW Lua probe without changing game files."""
from pathlib import Path
import re
from env_probe import PROBE_ID, LUA_PATH, default_openmw_cfg
from env_reader import parse_line


def diagnose(root, log=None, *, config=None):
    cfg = Path(config) if config else default_openmw_cfg()
    directory = (Path(root) / '_system' / 'openmw_env_050').resolve()
    report = dict(config=str(cfg), probe=str(directory), log=str(log) if log else None,
                  config_exists=cfg.is_file(), script_exists=(directory / LUA_PATH).is_file(),
                  descriptor_exists=(directory / PROBE_ID).is_file(),
                  boot_found=False, marker_found=False, lua_errors=[])
    data = cfg.read_text('utf-8-sig', errors='replace') if cfg.is_file() else ''
    def normalized(value): return value.strip().strip('"').casefold().replace('\\', '/')
    lines = [line.strip() for line in data.splitlines() if not line.lstrip().startswith('#')]
    report['data_enabled'] = any(line.lower().startswith('data=') and
                                 normalized(line[5:]) == normalized(str(directory)) for line in lines)
    report['content_enabled'] = any(line.lower().startswith('content=') and
                                    normalized(line[8:]) == normalized(PROBE_ID) for line in lines)
    if log and Path(log).is_file():
        with Path(log).open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 256000))
            logs = stream.read().decode('utf-8', 'replace').splitlines()
        report['boot_found'] = any('SILK_ENV_BOOT_V051' in x for x in logs)
        report['marker_found'] = any('SILK_ENV_V050|' in x for x in logs)
        report['marker_parseable'] = any(parse_line(x) is not None for x in logs if 'SILK_ENV_V050|' in x)
        report['last_warning'] = next((x[-400:] for x in reversed(logs) if 'SILK_ENV_WARN_V051' in x), None)
        report['lua_errors'] = [x[-350:] for x in logs if
            (('env050.lua' in x.lower() or 'lua' in x.lower()) and
             ((' error' in x.lower() or '[error]' in x.lower() or ' failed' in x.lower() or ' failure' in x.lower() or ' traceback' in x.lower())
              or bool(re.search(r'\[[^]]*\sE\]', x))))][-8:]
    if not report['config_exists']:
        reason = 'openmw.cfg не найден; проверь пользовательский путь конфигурации.'
    elif not (report['data_enabled'] and report['content_enabled']):
        reason = 'openmw.cfg не включает зонд. Закрой OpenMW и нажми «Установить зонд».'
    elif not (report['script_exists'] and report['descriptor_exists']):
        reason = 'Нет файлов зонда. Закрой OpenMW и нажми «Установить зонд».'
    elif report['lua_errors'] or report.get('last_warning'):
        reason = 'Есть ошибки Lua. Скопируй lua_errors или last_warning из этого отчёта.'
    elif report.get('marker_parseable'):
        reason = 'В логе есть метка; если она устарела, открой сохранение и повтори проверку.'
    elif report['marker_found']:
        reason = 'Метка найдена, но формат повреждён. Нужна строка SILK_ENV_V050 из лога.'
    elif report['boot_found']:
        reason = 'Мод загрузился, но пока не пишет координаты. Убедись, что персонаж в игре.'
    else:
        reason = 'OpenMW пока не подтвердила загрузку дополнительного зонда. Сначала перезапусти игру и загрузи сохранение.'
    report['next_action'] = reason
    return report
