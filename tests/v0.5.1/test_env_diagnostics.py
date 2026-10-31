import tempfile
import unittest
from pathlib import Path
from env_probe import install_probe, LUA_SOURCE, LUA_SOURCE_LEGACY, LUA_PATH
from env_diagnostics import diagnose
from openmw_motion import ControlRejected


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.cfg=self.base/'openmw.cfg'
        self.cfg.write_text('content=Morrowind.esm\n',encoding='utf-8')
        self.root=self.base/'app'
        self.log=self.base/'openmw.log'
    def install(self):
        return install_probe(self.root, config=self.cfg, running=lambda:False,confirm=True,now=lambda:10000)
    def test_report_uninstalled(self):
        report=diagnose(self.root, self.log, config=self.cfg)
        self.assertFalse(report['content_enabled'])
        self.assertIn('не включает зонд',report['next_action'])
    def test_report_enabled(self):
        self.install()
        report=diagnose(self.root,self.log,config=self.cfg)
        self.assertTrue(report['data_enabled'])
        self.assertTrue(report['content_enabled'])
        self.assertTrue(report['script_exists'])
    def test_report_boot_and_lua_error(self):
        self.install()
        self.log.write_text('SILK_ENV_BOOT_V051|loaded\n[error] Lua failure: env050.lua broken\n',encoding='utf-8')
        report=diagnose(self.root,self.log,config=self.cfg)
        self.assertTrue(report['boot_found'])
        self.assertTrue(report['lua_errors'])
    def test_report_valid_marker(self):
        self.install()
        self.log.write_text('SILK_ENV_V050|1|Balmora|0|1|2|3||\n',encoding='utf-8')
        self.assertTrue(diagnose(self.root,self.log,config=self.cfg)['marker_parseable'])
    def test_upgrade_from_exact_old_file_with_backup(self):
        self.install()
        file=self.root/'_system/openmw_env_050'/LUA_PATH
        file.write_text(LUA_SOURCE_LEGACY,encoding='utf-8')
        before=self.cfg.read_bytes()
        result=self.install()
        self.assertEqual(result['status'],'repaired')
        self.assertTrue(result['requires_openmw_restart'])
        self.assertEqual(file.read_text('utf-8'),LUA_SOURCE)
        self.assertEqual(file.with_name(file.name+'.silk-v050-backup').read_text('utf-8'),LUA_SOURCE_LEGACY)
        self.assertEqual(self.cfg.read_bytes(),before)
    def test_never_modify_custom_script(self):
        self.install()
        file=self.root/'_system/openmw_env_050'/LUA_PATH
        file.write_text('-- custom',encoding='utf-8')
        with self.assertRaises(ControlRejected):self.install()
        self.assertEqual(file.read_text('utf-8'),'-- custom')
    def test_new_source_boot_and_isolate(self):
        self.assertIn('SILK_ENV_BOOT_V051',LUA_SOURCE)
        self.assertIn('pcall',LUA_SOURCE)
        self.assertIn('SILK_ENV_V050|',LUA_SOURCE)

if __name__=='__main__':unittest.main()