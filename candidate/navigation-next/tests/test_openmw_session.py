from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from openmw_session import (start_session, monitor_session, read_status, changed_after_start,
                           write_status, ID_RE)


class Clock:
    def __init__(self): self.value=100.0
    def now(self): return self.value
    def sleep(self,dt): self.value+=dt


def sample(seq, x=10):
    return SimpleNamespace(seq=seq,cell='Balmora',x=x,y=20.,z=30.,health=50.)


def stamp(mtime=10_000, size=150):
    return dict(path='L:/OpenMW/openmw.log',mtime_ns=mtime,size=size)


class SessionTests(unittest.TestCase):
    def test_unique_session_tokens(self):
        self.assertTrue(ID_RE.fullmatch('a'*32))
        self.assertFalse(ID_RE.fullmatch('../evil'))
    def test_stale_old_log_not_connected(self):
        self.assertFalse(changed_after_start(sample(10),stamp(999,200),
                         dict(sample=None,signature=None),1000))
    def test_new_seq_connected(self):
        old=dict(sample=dict(seq=10,cell='Balmora',x=10.,y=20.,z=30.,health=50.),
                 signature=stamp(1001,150))
        self.assertTrue(changed_after_start(sample(11),stamp(1002,175),old,1000))
    def test_no_false_repeat(self):
        old=dict(sample=dict(seq=10,cell='Balmora',x=10.,y=20.,z=30.,health=50.),
                 signature=stamp(1001,150))
        self.assertFalse(changed_after_start(sample(10),stamp(1001,150),old,1000))
        self.assertFalse(changed_after_start(sample(10),stamp(1002,170),old,1000))
    def test_log_replaced_after_game_restart(self):
        old=dict(sample=dict(seq=100,cell='Balmora',x=10.,y=20.,z=30.,health=50.),
                 signature=stamp(1001,5000))
        self.assertTrue(changed_after_start(sample(2),stamp(2002,500),old,1000))
    def test_session_launch_and_observer_independent_controls_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            args=[]
            def spawn(cmd,**kwargs): args.append((cmd,kwargs));return SimpleNamespace(pid=12)
            ret=start_session(folder,folder, launch=lambda: {'status':'launched'},
                              start_process=spawn,find_log=lambda:None,wallclock_ns=lambda:1000)
            self.assertEqual(ret['status'],'session_started')
            self.assertFalse(ret['controls_enabled'])
            self.assertEqual(args[0][0][2],'session-watch')
            self.assertEqual(read_status(folder/'_system'/'session')['status'],'waiting')
    def test_launch_failure_does_not_set_false_connected(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fail():raise RuntimeError('Game missing')
            with self.assertRaises(RuntimeError):
                start_session(Path(tmp),Path(tmp),launch=fail,find_log=lambda:None)
            self.assertIsNone(read_status(Path(tmp)/'_system'/'session'))
    def test_watcher_receives_fresh_obs_without_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            write_status(folder,{'session_id':'a'*32,'status':'waiting','started_ns':1000,
                            'baseline':{'sample':None,'signature':None}})
            with patch('openmw_session.newest_with_signature',return_value=(sample(2),stamp(2000,250))):
                clock=Clock()
                def tick(_): clock.value+=3
                result=monitor_session(folder,'a'*32,find_log=lambda:'unused',running=lambda:True,
                                       clock=clock.now,ns_clock=lambda:2000,sleep=tick,limit_seconds=3.5,poll_seconds=3)
            self.assertEqual(result,'timeout')
            data=read_status(folder)
            self.assertEqual(data['sample']['seq'],2)
            self.assertFalse(data['controls_enabled'] if 'controls_enabled' in data else False)
    def test_waiting_when_only_stale_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            write_status(folder,{'session_id':'a'*32,'status':'waiting','started_ns':1000,
                            'baseline':{'sample':None,'signature':None}})
            with patch('openmw_session.newest_with_signature',return_value=(sample(2),stamp(999,250))):
                clock=Clock()
                monitor_session(folder,'a'*32,find_log=lambda:'unused',running=lambda:True,
                               clock=clock.now,ns_clock=lambda:2000,sleep=clock.sleep,limit_seconds=3,poll_seconds=2)
            self.assertNotIn('sample',read_status(folder))
    def test_missing_probe_shows_help_not_connected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            write_status(folder,{'session_id':'a'*32,'status':'waiting','started_ns':1000,
                    'baseline':{'sample':None,'signature':None}, 'controls_enabled':False})
            clock=Clock()
            clock.value=100.0
            monitor_session(folder,'a'*32,find_log=lambda:None,running=lambda:True,
                            clock=clock.now,ns_clock=lambda:2000,sleep=clock.sleep,
                            limit_seconds=22,poll_seconds=2.5)
            self.assertTrue(read_status(folder).get('probe_hint'))
            self.assertIn('SILK_OBS_V03',(folder/'session_state.txt').read_text(encoding='utf-8')) if read_status(folder)['status']=='waiting' else None

    def test_session_replacement_ends_older_watcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            write_status(folder,{'session_id':'b'*32,'status':'waiting','started_ns':1000,'baseline':{}})
            self.assertEqual(monitor_session(folder,'a'*32,find_log=lambda:None),'superseded')

if __name__=='__main__':unittest.main()
