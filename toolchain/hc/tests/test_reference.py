# Modified for v1.0.0: normalized public identifiers and technical documentation.
import unittest
from collections import deque
from src.reference import Cell, S, EVENTS, step, outputs

class ReferenceTests(unittest.TestCase):
    def ready(self):
        x=step(Cell(),{'settle_pulse':True})
        self.assertEqual(x.state,S.REBIND)
        x=step(x,{'capture_w0':True,'capture_w1':True,'energy_sample':True})
        return step(x)
    def test_positive_tx_bits(self):
        c=self.ready();self.assertEqual(c.state,S.READY)
        c=step(c,{'req_tx':True, 'tx_frame':0xAD});self.assertEqual(c.state,S.TX)
        observed=[]
        for i in range(8):
            observed.append(int(outputs(c)['optical_reflect']))
            c=step(c,{'symbol_done_tick':True})
        self.assertEqual(observed,[1,0,1,0,1,1,0,1])
        self.assertEqual(c.state,S.QUARANTINE)
    def test_aero_completion_requires_authentication(self):
        c=step(self.ready(),{'req_aero':True})
        self.assertEqual(c.state,S.AERO)
        self.assertEqual(step(c,{'aero_done_pulse':True}).state,S.AERO)
        self.assertEqual(step(c,{'aero_done_pulse':True,'aero_done_auth':True}).state,S.REBIND)
    def test_new_capture_invalidates_pending_tx(self):
        c=step(self.ready(),{'req_tx':True})
        c=step(c,{'capture_w1':True})
        self.assertEqual(c.state,S.QUARANTINE)
    def test_brownout_masks_without_clock(self):
        c=step(self.ready(),{'req_tx':True,'tx_frame':128})
        self.assertTrue(outputs(c)['optical_reflect'])
        self.assertFalse(outputs(c,{'power_good':False})['optical_reflect'])
        self.assertEqual(step(c,{'power_good':False}).state,S.QUARANTINE)
    def test_witness_and_auth_revocation_asynchronous(self):
        c=step(self.ready(),{'req_tx':True})
        for event in ({'w0_live':False},{'local_mission_authorized':False},{'world_break':True},{'observation_dirty_latched':True}):
            self.assertFalse(outputs(c,event)['authorized'])
            self.assertEqual(step(c,event).state,S.QUARANTINE)
    def test_midcycle_dirty_does_not_require_executor_tick(self):
        c=step(self.ready(),{'req_tx':True,'tx_frame':0x80})
        self.assertTrue(outputs(c)['optical_reflect'])
        self.assertFalse(outputs(c,{'observation_dirty_latched':True})['optical_reflect'])
        self.assertFalse(outputs(c,{'observation_dirty_latched':True})['authorized'])
        c=step(c,{'observation_dirty_latched':True})
        self.assertEqual(c.state,S.QUARANTINE)
        self.assertFalse(outputs(c)['authorized'])
    def test_exploration(self):
        # Distinct reachable states; enumerate transitions under 17 event classes.
        # Reference-model-only, no RTL correspondence proof.
        seen={Cell()};frontier={Cell()};transitions=0; violations=0
        for _ in range(9):
            nxt=set()
            for c in frontier:
                for name,e in EVENTS.items():
                    y=step(c,e)
                    out=outputs(y,e)
                    transitions+=1
                    if y.tx_start and y.aero_start: violations+=1
                    if out['tx_start'] and out['aero_start']: violations+=1
                    if out['authorized'] and (not y.w0 or not y.w1):violations+=1
                    if out['authorized'] and y.state not in (S.TX,S.AERO):violations+=1
                    if name in ('break','brownout','lost_witness','revoke','dirty') and y!=Cell():violations+=1
                    if c.state==S.QUARANTINE and name not in ('settle',) and y.state != S.QUARANTINE:violations+=1
                    nxt.add(y)
            frontier=nxt-seen
            seen |= nxt
            if not frontier:break
        self.assertEqual(violations,0)
        self.assertGreater(transitions,200)
        print(f'bounded host reference exploration: states={len(seen)}, transitions={transitions}, violations={violations}')

if __name__=='__main__':unittest.main()
