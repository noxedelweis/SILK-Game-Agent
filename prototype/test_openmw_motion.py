import unittest
from openmw_motion import StepController, ControlRejected

class Clock:
    def __init__(self): self.t = 10.0
    def now(self): return self.t
    def sleep(self, sec): self.t += sec

class Keyboard:
    def __init__(self, foreground=True, escape=False):
        self.foreground=foreground; self.escape=escape; self.events=[]
    def is_openmw_foreground(self): return self.foreground
    def is_emergency_stop(self): return self.escape
    def press_w(self): self.events.append('down')
    def release_w(self): self.events.append('up')

class TestMovement(unittest.TestCase):
    def make(self, kb):
        c=Clock()
        return StepController(kb, sleeper=c.sleep, clock=c.now)
    def test_consent(self):
        kb=Keyboard()
        with self.assertRaises(ControlRejected): self.make(kb).forward()
        self.assertEqual(kb.events, [])
    def test_foreground(self):
        kb=Keyboard(foreground=False)
        with self.assertRaises(ControlRejected): self.make(kb).forward(confirm=True)
        self.assertEqual(kb.events, [])
    def test_bounds(self):
        kb=Keyboard()
        for duration in (0, 0.41, float('nan'), float('inf'), True):
            with self.assertRaises(ControlRejected): self.make(kb).forward(duration,confirm=True)
        self.assertEqual(kb.events, [])
    def test_short_safe_press(self):
        kb=Keyboard()
        out=self.make(kb).forward(.2,confirm=True)
        self.assertEqual(kb.events,['down','up'])
        self.assertFalse(out['verified_in_game'])
    def test_escape(self):
        kb=Keyboard(escape=True)
        with self.assertRaises(ControlRejected): self.make(kb).forward(confirm=True)
        self.assertEqual(kb.events, [])
    def test_loss_of_focus_releases_key(self):
        kb=Keyboard(); c=Clock()
        def sleeper(seconds):
            c.sleep(seconds); kb.foreground=False
        with self.assertRaises(ControlRejected):
            StepController(kb,sleeper=sleeper,clock=c.now).forward(.2,confirm=True)
        self.assertEqual(kb.events,['down','up'])

if __name__=='__main__': unittest.main()
