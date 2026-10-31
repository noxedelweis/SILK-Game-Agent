"""Optional, read-only OpenMW 0.51 player telemetry add-on, installed ONLY by consent.

Copies a private Lua mod under SILK local data and appends two lines to openmw.cfg,
with a byte-preserving backup. Never touches the existing v0.3 probe or saves.
"""
from __future__ import annotations
import os
import re
import shutil
import time
from pathlib import Path
from openmw_motion import ControlRejected

PROBE_ID = 'silk_environment_050.omwscripts'
LUA_PATH = 'scripts/silk_agent/env050.lua'
LUA_SOURCE = r'''-- SILK_ENV_V050: read-only, opt-in OpenMW 0.51 player observation.
-- No control input, no game state or save modifications.
local self = require('openmw.self')
local nearby = require('openmw.nearby')
local seq = 0
local elapsed = 0
local function clean(s)
    s = tostring(s or '')
    return (s:gsub('[|;~\r\n]', '_'))
end
local function visible_objects(list, x, y, maxCount)
    local result = {}
    for _, obj in ipairs(list) do
        if #result >= maxCount then break end
        if obj and obj:isValid() then
            local p = obj.position
            if p and (p.x - x) ^ 2 + (p.y - y) ^ 2 < 1200 ^ 2 then
                result[#result + 1] = string.format('%s~%.1f~%.1f', clean(obj.recordId), p.x, p.y)
            end
        end
    end
    return table.concat(result, ';')
end
return {engineHandlers = {onUpdate = function(dt)
    elapsed = elapsed + dt
    if elapsed < 1.0 then return end
    elapsed = 0
    local p = self.position
    local cell = self.cell
    if not p or not cell then return end
    seq = seq + 1
    -- GameObject.rotation is a util.Transform; getYaw() is documented in OpenMW 0.51.
    local yaw = self.rotation:getYaw()
    local doors = visible_objects(nearby.doors, p.x, p.y, 6)
    local actors = visible_objects(nearby.actors, p.x, p.y, 6)
    print(string.format('SILK_ENV_V050|%d|%s|%.2f|%.2f|%.2f|%.5f|%s|%s',
          seq, clean(cell.name), p.x, p.y, p.z, yaw, doors, actors))
end}}
'''

LUA_SOURCE_LEGACY = LUA_SOURCE
LUA_SOURCE = "-- SILK 0.5.1 compatible environment probe, read only\nprint('SILK_ENV_BOOT_V051|loaded')\nlocal self = require('openmw.self')\nlocal nearby = require('openmw.nearby')\nlocal elapsed, seq = 0, 0\nlocal function clean(s)\n    return tostring(s or ''):gsub('[|;~\\r\\n]', '_')\nend\nlocal function gather(list, x, y)\n    local out = {}\n    for _, object in ipairs(list) do\n        if #out >= 6 then break end\n        if object and object:isValid() then\n            local p = object.position\n            if p and ((p.x-x)^2+(p.y-y)^2) < 1200^2 then\n                out[#out+1] = string.format('%s~%.1f~%.1f', clean(object.recordId),p.x,p.y)\n            end\n        end\n    end\n    return table.concat(out,';')\nend\nreturn {engineHandlers={onUpdate=function(dt)\n    elapsed = elapsed+(dt or 0)\n    if elapsed < 1 then return end\n    elapsed = 0\n    if not self:isActive() then return end\n    local p, cell = self.position, self.cell\n    if not p or not cell then return end\n    seq=seq+1\n    local ok_yaw, yaw = pcall(function() return self.rotation:getYaw() end)\n    if not ok_yaw then print('SILK_ENV_WARN_V051|yaw|'..clean(yaw));yaw=0 end\n    local ok_d, doors = pcall(function() return gather(nearby.doors,p.x,p.y) end)\n    if not ok_d then print('SILK_ENV_WARN_V051|doors|'..clean(doors));doors='' end\n    local ok_a, actors = pcall(function() return gather(nearby.actors,p.x,p.y) end)\n    if not ok_a then print('SILK_ENV_WARN_V051|actors|'..clean(actors));actors='' end\n    print(string.format('SILK_ENV_V050|%d|%s|%.2f|%.2f|%.2f|%.5f|%s|%s',\n       seq, clean(cell.name),p.x,p.y,p.z,yaw,doors,actors))\nend}}\n"


def default_openmw_cfg(home=None):
    return Path(home or Path.home()) / 'Documents' / 'My Games' / 'OpenMW' / 'openmw.cfg'


def install_probe(root, *, config=None, running=None, confirm=False, now=time.time):
    if not confirm:
        raise ControlRejected('Установка дополнительного Lua-зонда требует отдельного подтверждения')
    from openmw_launch import is_openmw_running
    if (is_openmw_running if running is None else running)():
        raise ControlRejected('Закрой OpenMW перед установкой Lua-зонда. Сохранения останутся нетронутыми.')
    config = Path(config) if config else default_openmw_cfg()
    if not config.is_file():
        raise ControlRejected('Не найден openmw.cfg: '+str(config))
    if config.stat().st_size > 4_000_000:
        raise ControlRejected('Необычно большой openmw.cfg — изменения отменены')
    raw = config.read_bytes()
    if b'\x00' in raw:
        raise ControlRejected('openmw.cfg не похож на текстовый файл')
    # OpenMW config is UTF-8, but preserve the original byte contents and newline style.
    mod_dir = Path(root) / '_system' / 'openmw_env_050'
    mod_dir = mod_dir.resolve()
    mod_dir.mkdir(parents=True, exist_ok=True)
    descriptor = mod_dir / PROBE_ID
    script = mod_dir / LUA_PATH
    script.parent.mkdir(parents=True, exist_ok=True)
    new_descriptor = ('PLAYER: '+LUA_PATH+'\n').encode('utf-8')
    new_script = LUA_SOURCE.encode('utf-8')
    repaired = False
    for f, data in ((descriptor,new_descriptor),(script,new_script)):
        if f.exists() and f.read_bytes()!=data:
            if f == script and f.read_bytes() == LUA_SOURCE_LEGACY.encode('utf-8'):
                backup_lua = f.with_name(f.name+'.silk-v050-backup')
                if backup_lua.exists() and backup_lua.read_bytes() != f.read_bytes():
                    raise ControlRejected('Резервный Lua-файл изменён, восстановление отменено')
                if not backup_lua.exists(): shutil.copy2(f,backup_lua)
                temp_lua = f.with_name(f.name+'.silk-new')
                if temp_lua.exists(): raise ControlRejected('Найден временный Lua-файл, восстановление отменено')
                try:
                    temp_lua.write_bytes(data)
                    os.replace(temp_lua,f)
                finally: temp_lua.unlink(missing_ok=True)
                repaired = True
            else:
                raise ControlRejected('Файл зонда уже изменён пользователем: '+str(f))
        if not f.exists(): f.write_bytes(data)
    # Never append duplicate content/data lines, regardless of whitespace or quoting.
    text = raw.decode('utf-8-sig', errors='strict')
    line_data = 'data="'+mod_dir.as_posix()+'"'
    line_content = 'content='+PROBE_ID
    lines = text.splitlines()
    norm = lambda s:s.strip().casefold().replace('\\','/')
    has_data=any(norm(line)==norm(line_data) for line in lines)
    has_content=any(norm(line)==norm(line_content) for line in lines)
    if has_data and has_content:
        return {'status':'repaired' if repaired else 'already_installed','probe':str(mod_dir),'config':str(config),
                'save_modified':False,'requires_openmw_restart':repaired}
    newline = '\r\n' if b'\r\n' in raw else '\n'
    extra = ('' if text.endswith(('\n','\r')) or not text else newline)
    if not has_data: extra += line_data + newline
    if not has_content: extra += line_content + newline
    backup = config.with_name(config.name+f'.silk-backup-{int(now())}')
    if backup.exists():
        raise ControlRejected('Резервная копия уже существует: '+str(backup))
    shutil.copy2(config,backup)
    updated = raw + extra.encode('utf-8')
    temporary = config.with_name(config.name+'.silk-new')
    if temporary.exists():
        raise ControlRejected('Служебный временный файл уже существует; openmw.cfg не изменён')
    try:
        temporary.write_bytes(updated)
        os.replace(temporary,config)
    finally:
        temporary.unlink(missing_ok=True)
    return {'status':'installed','probe':str(mod_dir),'config':str(config),'backup':str(backup),
            'save_modified':False,'requires_openmw_restart':True,
            'notes':'Lua emits SILK_ENV_V050 records after loading a save; verify in OpenMW.log'}
