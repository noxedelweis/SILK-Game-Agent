import os, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from openmw_launch import locate_openmw, is_openmw_running, launch_openmw, OpenMWLaunchError

class TestLaunch(unittest.TestCase):
    def test_find_existing_binary(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'openmw.exe';p.write_bytes(b'MZ')
            self.assertEqual(locate_openmw(extra_candidates=[p],environ={},which=lambda x:None),p.resolve())

    def test_reject_other_exe(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cmd.exe';p.write_bytes(b'MZ')
            with self.assertRaises(OpenMWLaunchError):
                locate_openmw(extra_candidates=[p],environ={},which=lambda x:None)

    def test_process_name_exact(self):
        with patch('openmw_launch.os.name','nt'):
            self.assertTrue(is_openmw_running(tasklist=lambda *a,**kw:SimpleNamespace(returncode=0,stdout='"openmw.exe","100","Console"\n')))
            self.assertFalse(is_openmw_running(tasklist=lambda *a,**kw:SimpleNamespace(returncode=0,stdout='"not-openmw.exe","100"\n')))
            self.assertFalse(is_openmw_running(tasklist=lambda *a,**kw:SimpleNamespace(returncode=0,stdout='INFO: no tasks match criteria')))

    def test_no_double_launch(self):
        self.assertEqual(launch_openmw(is_running=lambda:True,locate=lambda:None)['status'],'already_running')

    def test_only_run_selected_exe_no_shell(self):
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'openmw.exe';exe.write_bytes(b'MZ');calls=[]
            def run(args,**kwargs):calls.append((args,kwargs));return SimpleNamespace(pid=33)
            result=launch_openmw(is_running=lambda:False,locate=lambda:exe,popen=run)
            self.assertEqual(result['status'],'launched')
            self.assertEqual(calls[0][0],[str(exe)])
            self.assertFalse(calls[0][1]['shell'])
            self.assertFalse(result['controls_enabled'])

    def test_process_scan_failure(self):
        with patch('openmw_launch.os.name','nt'):
            with self.assertRaises(OpenMWLaunchError):
                is_openmw_running(tasklist=lambda *a,**k:SimpleNamespace(returncode=1,stdout=''))

if __name__=='__main__': unittest.main()
