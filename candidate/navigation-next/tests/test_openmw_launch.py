from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from openmw_launch import (OpenMWLaunchError, locate_openmw, is_openmw_running, launch_openmw)

class LaunchTests(unittest.TestCase):
    def test_known_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'openmw.exe'; p.write_bytes(b'MZ')
            self.assertEqual(locate_openmw(extra_candidates=[p], environ={},which=lambda _:None),p.resolve())
    def test_never_launch_other_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'notepad.exe';p.write_bytes(b'MZ')
            with self.assertRaises(OpenMWLaunchError):
                locate_openmw(extra_candidates=[p],environ={},which=lambda _:None)
    @unittest.skipUnless(os.name == 'nt','Process listing requires native Windows')
    def test_os_process_probe(self):
        self.assertIsInstance(is_openmw_running(), bool)
    def test_exact_process_name(self):
        with patch('openmw_launch.os.name','nt'):
            self.assertTrue(is_openmw_running(names=lambda:['explorer.exe', 'OpenMW.exe']))
            self.assertFalse(is_openmw_running(names=lambda:['not-openmw.exe', 'tasklist.exe']))
            self.assertFalse(is_openmw_running(names=lambda:[]))
    def test_check_fail_closed(self):
        with patch('openmw_launch.os.name','nt'):
            with self.assertRaises(OpenMWLaunchError):
                is_openmw_running(names=lambda: (_ for _ in ()).throw(OSError('api fail')))
    def test_native_probe_without_tasklist(self):
        import inspect
        from openmw_launch import is_openmw_running, _native_process_names
        self.assertNotIn('subprocess.run', inspect.getsource(_native_process_names))
        self.assertNotIn('subprocess.run', inspect.getsource(is_openmw_running))

    def test_reuse_existing_process(self):
        self.assertEqual(launch_openmw(is_running=lambda:True,locate=lambda:1)['status'],'already_running')
    def test_spawn_exact_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'openmw.exe';binary.write_bytes(b'MZ')
            calls=[]
            def spawn(args,**kwargs):calls.append((args,kwargs));return SimpleNamespace(pid=12345)
            output=launch_openmw(is_running=lambda:False,locate=lambda:binary,popen=spawn)
            self.assertEqual(output['status'],'launched')
            self.assertFalse(output['controls_enabled'])
            self.assertEqual(calls[0][0],[str(binary)])
            self.assertEqual(calls[0][1]['cwd'], str(binary.parent))
            self.assertFalse(calls[0][1]['shell'])
    def test_spawn_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'openmw.exe';binary.write_bytes(b'MZ')
            def fail(*a,**k):raise OSError('Access denied')
            with self.assertRaises(OpenMWLaunchError):
                launch_openmw(is_running=lambda:False,locate=lambda:binary,popen=fail)

if __name__=='__main__':unittest.main()
