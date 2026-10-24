# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""End-to-end C17 Cell simulation scenarios and release-image provenance."""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
CTL=ROOT/'tools/wcmctl.py'

class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='wcm-scenarios-')
        cls.bundle=pathlib.Path(cls.tmp.name)/'bundle'
        cls.device=pathlib.Path(cls.tmp.name)/'installed'
        for cmd in (['build','--device','virtual-node','--out',str(cls.bundle)],
                    ['install','--bundle',str(cls.bundle),'--device-root',str(cls.device)]):
            r=subprocess.run([sys.executable,str(CTL),*cmd],capture_output=True,text=True)
            if r.returncode:raise RuntimeError(r.stderr)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def scenario(self,name,ticks=250):
        r=subprocess.run([sys.executable,str(CTL),'simulate','--device-root',str(self.device),
            '--scenario',name,'--ticks',str(ticks)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        data=json.loads(r.stdout)
        self.assertFalse(data['summary']['downlink'])
        self.assertFalse(data['summary']['ack'])
        self.assertFalse(data['summary']['hardware_qualified'])
        return data
    def test_nominal_end_to_end(self):
        r=self.scenario('nominal');s=r['summary']
        self.assertEqual((s['completed'],s['symbols'],s['boots'],s['passive']),(3,96,1,True))
        self.assertEqual([e['event'] for e in r['events']].count('report_committed'),3)
    def test_brownout_cold_boot_allows_duplicate(self):
        r=self.scenario('brownout');s=r['summary']
        self.assertEqual((s['completed'],s['boots'],s['symbols'],s['passive']),(4,2,128,True))
        self.assertIn('cold_boot',[e['event'] for e in r['events']])
    def test_absent_sensor_fail_closed(self):
        self.assertEqual(self.scenario('sensor-silent')['summary']['completed'],0)
    def test_no_energy_fail_closed(self):
        self.assertEqual(self.scenario('energy-starve')['summary']['symbols'],0)
    def test_in_flight_world_break_no_commit(self):
        s=self.scenario('fault-inflight')['summary']
        self.assertEqual((s['completed'],s['symbols'],s['interrupted'],s['epoch_breaks']),(0,4,1,1))
    def test_not_a_remote_command_channel(self):
        data=self.scenario('nominal')
        self.assertTrue(all('command' not in e for e in data['events']))
        exe=self.device/'firmware/wcm_scenario'
        text=exe.read_bytes()
        self.assertNotIn(b'wcm_frame_decode',text)
    def test_tampered_simulator_rejected(self):
        exe=self.device/'firmware/wcm_scenario';before=exe.read_bytes()
        try:
            exe.write_bytes(before+b'X')
            r=subprocess.run([sys.executable,str(CTL),'simulate','--device-root',str(self.device),
                '--scenario','nominal'],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('sha256 mismatch',r.stderr)
        finally:exe.write_bytes(before)
    def test_malformed_scenarios_rejected(self):
        for wrong in ('station-command','', 'ack'):
            r=subprocess.run([sys.executable,str(CTL),'simulate','--device-root',str(self.device),
                '--scenario',wrong],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)

if __name__=='__main__':unittest.main()
