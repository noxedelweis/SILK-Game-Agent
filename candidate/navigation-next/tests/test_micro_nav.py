import os
import tempfile
import unittest
import math
from pathlib import Path
from micro_nav import parse_offset, compute_control_vector, guarded_navigation, wait_for_initial_coordinates
from motion_session import Sample
from openmw_motion import ControlRejected

class Clock:
 def __init__(self):self.t=10.0
 def now(self):return self.t
 def sleep(self,v):self.t+=v

class World:
 def __init__(self):
  self.x=0.;self.y=0.;self.seq=5;self.keys=[];self.focus=True;self.esc=False
  self.pending=False;self.blocked=False
 def is_openmw_foreground(self):return self.focus
 def is_emergency_stop(self):return self.esc
 def press_key(self,key):self.keys.append(('down',key))
 def release_key(self,key):
  self.keys.append(('up',key));
  if not self.blocked:
   delta={'W':(28.8,0),'D':(0,28.8),'S':(-28.8,0),'A':(0,-28.8)}[key]
   self.x+=delta[0];self.y+=delta[1]
  self.seq+=1
 def read(self,path):return Sample(self.seq,'Balmora',self.x,self.y,10.,80.)

class TestMicroNav(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.log=Path(self.tmp.name)/'openmw.log';self.log.write_text('SILK_OBS_V03|5|Balmora|0|0|10|80\n')
  self.clock=Clock();self.world=World()
 def tearDown(self):self.tmp.cleanup()
 def call(self,**kw):
  params=dict(confirm=True,backend=self.world,sample_reader=self.world.read,
   sleeper=self.clock.sleep,clock=self.clock.now,wallclock=lambda:self.log.stat().st_mtime)
  params.update(kw)
  return guarded_navigation(self.log,(45.,40.),**params)
 def test_offset_validation(self):
  self.assertEqual(parse_offset('35,15'),(35.,15.))
  for s in ('bad','999,999','1,1','NaN,2','35;hello'):
   with self.assertRaises(ControlRejected):parse_offset(s)
 def test_projection(self):
  cmd=compute_control_vector((28.8,0),(0,28.8),(50,2))
  self.assertEqual(cmd['key'],'W')
 def test_consent_denied(self):
  with self.assertRaises(ControlRejected):guarded_navigation(self.log,(45.,40.),backend=self.world)
  self.assertEqual(self.world.keys,[])
 def test_foreground_denied(self):
  self.world.focus=False
  with self.assertRaises(ControlRejected):self.call()
  self.assertEqual(self.world.keys,[])
 def test_escape_denied(self):
  self.world.esc=True
  with self.assertRaises(ControlRejected):self.call()
  self.assertEqual(self.world.keys,[])
 def test_bounded_route(self):
  result=self.call()
  self.assertIn(result['status'],('arrived','budget_exhausted'))
  self.assertLessEqual(len(result['pulses']),8)
  self.assertEqual(len([a for a,b in self.world.keys if a=='down']),len([a for a,b in self.world.keys if a=='up']))
  self.assertEqual(result['target_cell'],'Balmora')
 def test_stuck_during_calibration(self):
  self.world.blocked=True
  with self.assertRaises(ControlRejected):self.call()
 def test_first_sample_can_arrive_late(self):
  calls=[0]
  def delayed(path):
   calls[0]+=1
   if calls[0]<4:return None
   return self.world.read(path)
  result=self.call(sample_reader=delayed)
  self.assertTrue(calls[0]>=4)
  self.assertIn(result['status'],('arrived','budget_exhausted'))
 def test_no_initial_sample_never_sends_keys(self):
  with self.assertRaisesRegex(ControlRejected,'нет SILK_OBS_V03'):
   self.call(sample_reader=lambda path:None)
  self.assertEqual(self.world.keys,[])
 def test_probe_error_in_live_log_has_hint(self):
  self.log.write_text('SILK_PROBE_ERROR: lua failed\n',encoding='utf-8')
  with self.assertRaisesRegex(ControlRejected,'SILK_PROBE_ERROR'):
   self.call(sample_reader=lambda path:None)
  self.assertEqual(self.world.keys,[])
 def test_escape_during_wait_never_sends_keys(self):
  self.world.esc=True
  with self.assertRaises(ControlRejected):
   self.call(sample_reader=lambda path:None)
  self.assertEqual(self.world.keys,[])
 def test_parallel_vectors_rejected(self):
  with self.assertRaises(ControlRejected):compute_control_vector((28,0),(25,0),(30,20))
 def test_stale_file_denied(self):
  with self.assertRaises(ControlRejected):guarded_navigation(self.log,(45.,40.),confirm=True,
   backend=self.world,wallclock=lambda:self.log.stat().st_mtime+16)
  self.assertEqual(self.world.keys,[])
 def test_max_steps_denied(self):
  with self.assertRaises(ControlRejected):self.call(max_steps=600)
  self.assertEqual(self.world.keys,[])

if __name__=='__main__':unittest.main()
