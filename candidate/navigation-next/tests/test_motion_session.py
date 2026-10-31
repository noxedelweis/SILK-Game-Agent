import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from motion_session import Sample, parse_line, observe_movement, newest_sample, step_once
from openmw_motion import ControlRejected

class Clock:
    def __init__(self): self.t = 100.0
    def now(self): return self.t
    def sleep(self, seconds): self.t += seconds

class Backend:
    def __init__(self, foreground=True, escape=False):
        self.foreground=foreground; self.escape=escape; self.keys=[]
    def is_openmw_foreground(self): return self.foreground
    def is_emergency_stop(self): return self.escape
    def press_w(self): self.keys.append('down')
    def release_w(self): self.keys.append('up')

class MotionSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.log=Path(self.temp.name)/'openmw.log'
        self.log.write_text('SILK_OBS_V03|8|Balmora|100|200|50|90\n',encoding='utf-8')
        self.before=Sample(8,'Balmora',100,200,50,90)
    def tearDown(self): self.temp.cleanup()
    def test_parse(self):
        self.assertEqual(newest_sample(self.log), self.before)
        self.assertIsNone(parse_line('bad|1|Balmora'))
    def test_trailing_partial(self):
        with self.log.open('ab') as f: f.write(b'SILK_OBS_V03|9|Balmora|100|')
        self.assertEqual(newest_sample(self.log),self.before)
    def test_confirmation_required(self):
        k=Backend()
        with self.assertRaises(ControlRejected):
            step_once(self.log,backend=k,confirm=False)
        self.assertEqual(k.keys, [])
    def test_stale_log_rejected(self):
        k=Backend()
        with self.assertRaises(ControlRejected):
            step_once(self.log,backend=k,confirm=True,wallclock=lambda:os.stat(self.log).st_mtime+21)
        self.assertEqual(k.keys, [])
    def test_window_foreground_required(self):
        k=Backend(foreground=False);c=Clock()
        with self.assertRaises(ControlRejected):
            step_once(self.log,backend=k,confirm=True,sleeper=c.sleep,clock=c.now,wallclock=lambda:os.stat(self.log).st_mtime)
        self.assertEqual(k.keys, [])
    def test_escape_preflight(self):
        k=Backend(escape=True);c=Clock()
        with self.assertRaises(ControlRejected):
            step_once(self.log,backend=k,confirm=True,sleeper=c.sleep,clock=c.now,wallclock=lambda:os.stat(self.log).st_mtime)
        self.assertEqual(k.keys, [])
    def test_one_step_and_move_observed(self):
        k=Backend();c=Clock();state={'n':0}
        def reader(path):
            state['n']+=1
            if k.keys==['down','up']: return Sample(9,'Balmora',103,200,50,90)
            return self.before
        result=step_once(self.log,backend=k,confirm=True,sleeper=c.sleep,clock=c.now,
                         wallclock=lambda:os.stat(self.log).st_mtime,sample_reader=reader)
        self.assertTrue(result['command_sent'])
        self.assertTrue(result['telemetry']['verified'])
        self.assertEqual(k.keys,['down','up'])
    def test_sent_without_new_telemetry_is_unverified(self):
        k=Backend();c=Clock()
        result=step_once(self.log,backend=k,confirm=True,sleeper=c.sleep,clock=c.now,
                         wallclock=lambda:os.stat(self.log).st_mtime,verify_seconds=.3,
                         sample_reader=lambda p:self.before)
        self.assertFalse(result['telemetry']['verified'])
        self.assertEqual(k.keys,['down','up'])
    def test_user_moving_during_countdown_cancels(self):
        k=Backend();c=Clock();calls=[self.before,Sample(9,'Balmora',105,200,50,90)]
        with self.assertRaises(ControlRejected):
            step_once(self.log,backend=k,confirm=True,sleeper=c.sleep,clock=c.now,
                      wallclock=lambda:os.stat(self.log).st_mtime,sample_reader=lambda p:calls.pop(0))
        self.assertEqual(k.keys, [])
    def test_cross_cell_not_claimed_as_verified_step(self):
        out=observe_movement(self.before,Sample(9,'Balmora, Guild of Mages',500,20,20,80))
        self.assertFalse(out['verified'])
    def test_no_implicit_causality(self):
        out=observe_movement(self.before,Sample(9,'Balmora',110,200,50,90))
        self.assertEqual(out['attribution'],'Связь с командой предполагается, а не доказывается')

    def test_complete_final_record_without_newline(self):
        from motion_session import newest_sample
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            log=Path(folder)/'openmw.log'
            log.write_text('[info] SILK_OBS_V03|8|Balmora|1.20|2.40|3.00|40.00',encoding='utf-8')
            sample=newest_sample(log)
            self.assertIsNotNone(sample)
            self.assertEqual(sample.seq,8)

if __name__=='__main__': unittest.main()
