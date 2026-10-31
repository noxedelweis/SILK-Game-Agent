import math
import tempfile
import unittest
from pathlib import Path
from nav_v2 import navigation_v2, parse_waypoints
from motion_session import Sample
from openmw_motion import ControlRejected


class FakeClock:
    def __init__(self): self.t=20.
    def now(self): return self.t
    def sleep(self,seconds): self.t+=seconds


class FakeGame:
    def __init__(self,clock):
        self.clock=clock
        self.down_time=0.
        self.x=0.;self.y=0.;self.seq=2;self.focus=True;self.esc=False
        self.events=[];self.blocked=False;self.rotate=False
    def is_openmw_foreground(self): return self.focus
    def is_emergency_stop(self): return self.esc
    def press_key(self,key):
        self.down_time=self.clock.now()
        self.events.append(('down',key))
    def release_key(self,key):
        self.events.append(('up',key)); self.seq+=1
        if not self.blocked:
            dx,dy={'W':(28.8,0.),'S':(-28.8,0.),'D':(0.,28.8),'A':(0.,-28.8)}[key]
            factor=max(0.,self.clock.now()-self.down_time)/.20
            dx*=factor;dy*=factor
            if self.rotate and key == 'A': dx,dy=(28.8,0.)
            self.x+=dx;self.y+=dy
    def read(self,path):return Sample(self.seq,'Balmora',self.x,self.y,0.,100.)


class TestNavigationV2(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.log=Path(self.temp.name)/'openmw.log'
        self.log.write_text('SILK_OBS_V03|2|Balmora|0|0|0|100\n')
        self.c=FakeClock();self.w=FakeGame(self.c)
    def tearDown(self):self.temp.cleanup()
    def go(self,points=((35.,15.),),**kwargs):
        args=dict(confirm=True,backend=self.w, sample_reader=self.w.read,
                  sleeper=self.c.sleep,clock=self.c.now,wallclock=lambda:self.log.stat().st_mtime,
                  max_pulses=12)
        args.update(kwargs)
        return navigation_v2(self.log,points,**args)
    def test_parser(self):
        self.assertEqual(parse_waypoints('35,15; 65,15;65,-20'),((35.,15.),(65.,15.),(65.,-20.)))
        self.assertEqual(parse_waypoints('30 20'),((30.,20.),))
    def test_invalid_parser(self):
        for s in ('', 'bad', '1,1','NaN,10','999,5','35,15;35,15',
                  '35,15;65,15;65,-20;65,40','55,10;', '35;15', '30,20;300,1'):
            with self.subTest(s=s),self.assertRaises(ControlRejected): parse_waypoints(s)
    def test_arrived_single(self):
        result=self.go()
        self.assertEqual(result['status'],'arrived')
        self.assertEqual(result['waypoints_reached'],1)
        self.assertLessEqual(len(result['pulses']),12)
        self.assertEqual(len([e for e in self.w.events if e[0]=='down']),len([e for e in self.w.events if e[0]=='up']))
    def test_multiple_waypoints(self):
        result=self.go(((35.,15.),(65.,15.),(65.,-20.)))
        self.assertEqual(result['total_waypoints'],3)
        self.assertLessEqual(len(result['pulses']),12)
        self.assertGreaterEqual(result['waypoints_reached'],1)
        self.assertEqual(result['cell'],'Balmora')
    def test_no_consent(self):
        with self.assertRaises(ControlRejected): self.go(confirm=False)
        self.assertEqual(self.w.events,[])
    def test_no_focus(self):
        self.w.focus=False
        with self.assertRaises(ControlRejected): self.go()
        self.assertEqual(self.w.events,[])
    def test_esc(self):
        self.w.esc=True
        with self.assertRaises(ControlRejected): self.go()
        self.assertEqual(self.w.events,[])
    def test_stale(self):
        with self.assertRaises(ControlRejected): self.go(wallclock=lambda:self.log.stat().st_mtime+100)
        self.assertEqual(self.w.events,[])
    def test_no_sample(self):
        with self.assertRaises(ControlRejected):self.go(sample_reader=lambda path:None)
        self.assertEqual(self.w.events,[])
    def test_calibration_blocked(self):
        self.w.blocked=True
        with self.assertRaises(ControlRejected):self.go()
        self.assertEqual(self.w.events[:2],[('down','W'),('up','W')])
    def test_bad_budget(self):
        with self.assertRaises(ControlRejected):self.go(max_pulses=999)
    def test_inconsistent_rotation(self):
        # Need A correction for target positive X, negative Y after D calibration.
        self.w.rotate=True
        r=self.go(((30.,-35.),))
        self.assertIn(r['status'],('orientation_changed','diverging'))
    def test_output_waypoints_anchored_at_start(self):
        self.w.x=1000.;self.w.y=-50.
        r=self.go(((35.,15.),))
        self.assertEqual(r['waypoints_xy'],[[1035.,-35.]])
    def test_limit_all_including_calibration(self):
        result=self.go(((130.,0.),),max_pulses=4)
        self.assertLessEqual(len(result['pulses']),4)


if __name__=='__main__':unittest.main()
