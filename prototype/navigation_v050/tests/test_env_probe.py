import tempfile
import unittest
from pathlib import Path
from env_probe import install_probe, LUA_SOURCE
from openmw_motion import ControlRejected
from env_reader import parse_line, latest_environment

class ProbeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.dir=Path(self.tmp.name);self.cfg=self.dir/'openmw.cfg'
  self.cfg.write_bytes(b'data="C:/Old Morrowind"\r\ncontent=Morrowind.esm\r\n')
  self.root=self.dir/'silk'
 def tearDown(self):self.tmp.cleanup()
 def install(self,**kw):
  settings=dict(config=self.cfg,running=lambda:False,confirm=True,now=lambda:123456)
  settings.update(kw)
  return install_probe(self.root,**settings)
 def test_no_consent_no_mutation(self):
  with self.assertRaises(ControlRejected):self.install(confirm=False)
  self.assertFalse(self.root.exists())
 def test_game_running_no_mutation(self):
  with self.assertRaises(ControlRejected):self.install(running=lambda:True)
  self.assertFalse(self.root.exists())
 def test_backup_and_idempotent(self):
  orig=self.cfg.read_bytes()
  r=self.install()
  self.assertEqual(r['status'],'installed')
  self.assertEqual(Path(r['backup']).read_bytes(),orig)
  self.assertTrue(Path(r['probe']).is_dir())
  text=self.cfg.read_text('utf-8')
  self.assertIn('content=silk_environment_050.omwscripts',text)
  self.assertIn('content=Morrowind.esm',text)
  self.assertEqual(self.install()['status'],'already_installed')
  self.assertEqual(text,self.cfg.read_text('utf-8'))
 def test_dont_overwrite_modified_lua(self):
  self.install()
  lua=self.root/'_system/openmw_env_050/scripts/silk_agent/env050.lua'
  lua.write_text('custom edits')
  with self.assertRaises(ControlRejected):self.install()
 def test_missing_config(self):
  self.cfg.unlink()
  with self.assertRaises(ControlRejected):self.install()
 def test_lua_is_passive(self):
  self.assertIn('self.rotation:getYaw()', LUA_SOURCE)
  self.assertIn('nearby.doors', LUA_SOURCE)
  self.assertIn('nearby.actors', LUA_SOURCE)
  for forbidden in ('teleport(', 'enableAI(', 'self.controls.', 'sendEvent(', 'setPosition(', 'os.execute('):
   self.assertNotIn(forbidden,LUA_SOURCE)
 def test_environment_parser(self):
  line='[info] SILK_ENV_V050|5|Balmora|100.20|-300.00|45.00|1.57100|door_x~110.0~-290.0|npc_y~101.0~-280.0\n'
  r=parse_line(line)
  self.assertEqual(r['seq'],5)
  self.assertEqual(r['cell'],'Balmora')
  self.assertEqual(r['doors'][0]['record_id'],'door_x')
  self.assertEqual(r['actors'][0]['x'],101)
 def test_tail_reader(self):
  self.cfg.write_text('previous')
  line='SILK_ENV_V050|6|Balmora|0|1|2|3||\n'
  self.cfg.write_text('ignore\n'+line)
  self.assertEqual(latest_environment(self.cfg)['yaw_radians'],3.0)
 def test_stale_environment_rejected(self):
  self.cfg.write_text('SILK_ENV_V050|6|Balmora|0|1|2|3||\n')
  self.assertIsNone(latest_environment(self.cfg,now=lambda:self.cfg.stat().st_mtime+90))
 def test_malformed_telemetry(self):
  self.assertIsNone(parse_line('SILK_ENV_V050|3|Balmora|NaN|1|2|3||'))
  self.assertIsNone(parse_line('SILK_ENV_V050|3|Balmora|0|1|2|3|door~x~z|'))

if __name__=='__main__':unittest.main()