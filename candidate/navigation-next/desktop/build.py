"""Create a reproducible embedded GUI zipapp and C payload include (stdlib only)."""
from __future__ import annotations
import base64
import hashlib
import re
import zipfile
import tempfile
import sys
from pathlib import Path

base=Path(__file__).resolve().parents[1]
desktop=base/'desktop'
release=base/'release'
artifacts=base/'dist'
artifacts.mkdir(exist_ok=True)
version=(release/'version.txt').read_text(encoding='ascii').strip()
if not re.fullmatch(r'0\.\d+\.\d+',version):
    raise ValueError('Version must be 0.X.Y')
encoded=(release/f'SILK_Game_Agent_v{version}.zip.b64').read_text(encoding='ascii')
raw=base64.b64decode(encoded,validate=True)
agent_zip=artifacts/f'SILK_Game_Agent_v{version}.zip'
agent_zip.write_bytes(raw)
with zipfile.ZipFile(agent_zip) as zf:
    if any('../' in x or x.startswith('/') for x in zf.namelist()):
        raise ValueError('Unsafe zip member')
    if not any(x.startswith('SILK_Game_Agent_v'+version+'/knowledge_cli.py') for x in zf.namelist()):
        raise ValueError('Agent package missing knowledge CLI')
# Test compatibility with the actual updater before embedding the ZIP in an EXE.
from updater import safe_extract
with tempfile.TemporaryDirectory() as staging:
    safe_extract(agent_zip,Path(staging),'SILK_Game_Agent_v'+version)
script=(desktop/'__main__.py').read_text(encoding='utf-8')
script=re.sub(r"BUNDLED_VERSION='[^']*'",f"BUNDLED_VERSION='{version}'",script)
script=re.sub(r"PACKAGE_SHA='[a-f0-9]*'",f"PACKAGE_SHA='{hashlib.sha256(raw).hexdigest()}'",script)
with zipfile.ZipFile(desktop/'app.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
    zf.writestr('__main__.py',script)
    for name in ('updater.py','host_update.py','host_update_helper.py','openmw_motion.py','motion_session.py','observer_import.py','openmw_launch.py','openmw_session.py','micro_nav.py','nav_v2.py','env_probe.py','env_reader.py','env_diagnostics.py','object_nav.py','feature_gates.py'):
        zf.write(desktop/name,arcname=name)
    zf.writestr('payload/'+agent_zip.name,raw)
payload=(desktop/'app.zip').read_bytes()
chunks=[payload[i:i+16] for i in range(0,len(payload),16)]
include='static const unsigned char payload_bytes[] = {\n'+''.join('    '+','.join('0x%02x'%n for n in group)+',\n' for group in chunks)+'};\n'
(desktop/'payload.inc').write_text(include,encoding='ascii')
compiled=(desktop/'launcher.c').read_text(encoding='utf-8').replace('BUNDLE_CACHE_TOKEN',version.replace('.', '_'))
(desktop/'launcher_build.c').write_text(compiled,encoding='utf-8')
print('release_version='+version,'agent_sha='+hashlib.sha256(raw).hexdigest(),
      'app_bundle='+str(len(payload))+'B')
