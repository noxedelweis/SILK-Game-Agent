import datetime as dt
import math
import tempfile
import unittest
from pathlib import Path
from env_reader import inspect_environment, parse_line
from env_diagnostics import diagnose
from object_nav import plan_door_approach, navigate_to_door
from motion_session import Sample
from feature_gates import feature_channel
from openmw_motion import ControlRejected


class EnvironmentSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log=Path(self.tmp.name)/'openmw.log'
        self.now=dt.datetime(2026,11,1,0,0,1).timestamp()
        self.logline='[00:00:01.000 I] L@0xA[script]: SILK_ENV_V050|2|Balmora|0|0|5|1.59292|door~140~20|npc~1~2'
    def write_log(self, line=None):
        import os
        self.log.write_text((line if line is not None else self.logline)+'\n',encoding='utf-8')
        os.utime(self.log,(self.now,self.now))
    def test_freshness_from_actual_line_time(self):
        self.write_log()
        s=inspect_environment(self.log,now=lambda:self.now+2)
        self.assertEqual(s['status'],'current')
        self.assertEqual(s['observation']['doors'][0]['record_id'],'door')
        self.assertEqual(s['observation']['yaw_radians'],1.59292)
    def test_game_paused_log_mtime_updated_but_old_sample(self):
        self.write_log('[23:57:00.000 I] SILK_ENV_V050|2|Balmora|0|0|5|1.59|door~140~20|')
        self.assertEqual(inspect_environment(self.log,now=lambda:self.now)['status'],'stale')
    def test_lack_of_log_timestamp_never_called_current(self):
        self.write_log('SILK_ENV_V050|2|Balmora|0|0|5|1.59|door~140~20|')
        self.assertEqual(inspect_environment(self.log,now=lambda:self.now)['status'],'unknown')
    def test_midnight_rollover(self):
        self.write_log('[23:59:59.000 I] SILK_ENV_V050|2|Balmora|0|0|5|1.59|door~140~20|')
        self.assertEqual(inspect_environment(self.log,now=lambda:self.now)['status'],'current')
    def test_missing_log(self):
        self.assertEqual(inspect_environment(self.log)['status'],'missing')
    def test_malformed_object_ignored_not_whole_snapshot(self):
        r=parse_line('SILK_ENV_V050|2|Balmora|0|0|5|1.59|broken~x~y;good~100~200|npc~1~2')
        self.assertEqual([d['record_id'] for d in r['doors']],['good'])
    def test_false_lua_error_not_triggered_by_script_path(self):
        self.log.write_text('[23:59:26.554 V] #37 PLAYER : scripts/silk_agent/env050.lua\n'
          '[23:59:54.766 I] L@0x1[scripts/silk_agent/env050.lua]: SILK_ENV_V050|1|Balmora|0|0|5|1.5||\n')
        root=Path(self.tmp.name)/'agent'
        result=diagnose(root,self.log,config=Path(self.tmp.name)/'openmw.cfg')
        self.assertEqual(result['lua_errors'],[])
        self.assertTrue(result['marker_parseable'])


class DoorNavigationTests(unittest.TestCase):
    def make_snapshot(self,status='current',x=0,y=0,door=(140.,20.)):
        return {'status':status,'observation':{'seq':2,'cell':'Balmora','x':x,'y':y,
            'z':5,'yaw_radians':1.59,'doors':[{'record_id':'door_01', 'x':door[0], 'y':door[1]}], 'actors':[]}}
    def test_preview_with_bounded_route(self):
        result=plan_door_approach(self.make_snapshot())
        self.assertEqual(result['status'],'preview')
        self.assertEqual(result['mode'],'experimental_read_only')
        self.assertLessEqual(len(result['waypoints']),3)
        self.assertLessEqual(math.hypot(*result['waypoints'][-1]),210)
    def test_near_door_does_not_move(self):
        self.assertEqual(plan_door_approach(self.make_snapshot(door=(60.,0.)))['status'],'already_near')
    def test_far_door_refused(self):
        with self.assertRaises(ControlRejected):plan_door_approach(self.make_snapshot(door=(900.,0.)))
    def test_stale_or_unknown_refused(self):
        for status in ('stale','unknown','missing'):
            with self.subTest(status=status),self.assertRaises(ControlRejected):
                plan_door_approach(self.make_snapshot(status))
    def test_bad_index_refused(self):
        for index in (2,-1,False,1.1):
            with self.subTest(index=index),self.assertRaises(ControlRejected):
                plan_door_approach(self.make_snapshot(),index)
    def test_never_run_without_consent(self):
        called=[]
        with self.assertRaises(ControlRejected):navigate_to_door('dummy',confirm=False,
            navigator=lambda *a,**kw:called.append(1))
        self.assertEqual(called,[])
    def fake_backend(self):
        class Backend:
            esc = False
            focus = True
            def is_emergency_stop(self):return self.esc
            def is_openmw_foreground(self):return self.focus
        return Backend()
    def test_control_guard_rejects_drift(self):
        backend=self.fake_backend()
        snapshots=[self.make_snapshot(status='stale'),self.make_snapshot()]
        snapshots[1]['observation']['seq']=3
        def read(log):return snapshots.pop(0) if len(snapshots)>1 else snapshots[0]
        def nav(log,points,confirm,backend,switch_seconds,start_guard):
            self.assertTrue(confirm)
            self.assertEqual(switch_seconds,0.)
            with self.assertRaises(ControlRejected):
                start_guard(Sample(9,'Balmora',35.,0.,5.,100.))
            start_guard(Sample(9,'Balmora',0.,0.,5.,100.))
            return {'status':'arrived'}
        result=navigate_to_door('dummy',confirm=True,snapshot_reader=read,
                navigator=nav,backend=backend,clock=lambda:1.,
                sleeper=lambda n:None,wait_seconds=0.)
        self.assertEqual(result['status'],'arrived')
    def test_wait_for_new_observation_before_any_movement(self):
        backend=self.fake_backend()
        called=[]
        first=self.make_snapshot(); first['observation']['seq']=2
        ticks=[0.]
        def advance(n):ticks[0]+=n
        with self.assertRaises(ControlRejected):navigate_to_door('dummy',confirm=True,
            snapshot_reader=lambda _: first,backend=backend,
            clock=lambda:ticks[0],sleeper=advance,wait_seconds=0.,observation_timeout=.5,
            navigator=lambda *args,**kwargs:called.append(1))
        self.assertEqual(called,[])
    def test_no_movement_when_already_near(self):
        backend=self.fake_backend()
        state=self.make_snapshot(door=(50,0))
        counter=[0]
        def reader(_):
            counter[0]+=1
            d=self.make_snapshot(door=(50,0))
            d['observation']['seq']=counter[0]
            return d
        r=navigate_to_door('dummy',confirm=True,snapshot_reader=reader,backend=backend,
            clock=lambda:1.,sleeper=lambda n:None,wait_seconds=0.,
            navigator=lambda *args,**kwargs:self.fail('Should not navigate'))
        self.assertEqual(r['pulses'],[])
    def test_feature_channels(self):
        self.assertEqual(feature_channel('environment'),'stable')
        self.assertEqual(feature_channel('object-nav'),'experimental')

if __name__=='__main__':unittest.main()
