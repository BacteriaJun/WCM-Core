# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Tests for the Mission-64 behavioral model and Film source packaging.
"""
import importlib.util
import pathlib
import random
import subprocess
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'hardware/film/model'))
sys.path.insert(0,str(ROOT/'toolchain/mission'))
from mission64_reference import FilmMission,Mode,crc_atm
import missionc

class FilmMissionTests(unittest.TestCase):
    def default(self):
        return missionc.pack(missionc.parse_spec(ROOT/'devices/virtual-node/mission.toml'))
    def load(self, mission):
        model=FilmMission()
        for byte in mission:
            for b in range(7,-1,-1):model.bit((byte>>b)&1)
        model.edge()
        return model
    def test_crc_algorithm_independent_1000(self):
        rng=random.Random(1906)
        for _ in range(1000):
            data=rng.randbytes(7)
            self.assertEqual(crc_atm(data),missionc.crc8(data))
    def test_loader_golden_and_strict_fields(self):
        good=self.default();self.assertEqual(good.hex(),'11118104300000f7')
        m=self.load(good)
        self.assertTrue(m.mission_valid)
        self.assertEqual(m.mode,Mode.ACTIVE)
        self.assertEqual(m.fields()['threshold'],6)
        for i in range(64):
            mutated=(int.from_bytes(good,'big')^(1<<i)).to_bytes(8,'big')
            self.assertFalse(self.load(mutated).mission_valid)
        for k in (0,1,2,6,7):
            partial=FilmMission()
            for bit in ''.join(f'{b:08b}' for b in good[:k]):partial.bit(int(bit))
            self.assertFalse(partial.mission_valid)
            self.assertFalse(partial.request)
    def test_overlong_after_verification(self):
        m=self.load(self.default());m.bit(0)
        self.assertTrue(m.bad);self.assertFalse(m.mission_valid)
        self.assertFalse(m.request)
    def test_threshold_inflight_not_counted_until_complete(self):
        m=self.load(self.default())
        m.edge(tick=True,sensor_value=50)
        m.edge();self.assertFalse(m.request)
        m.edge(tick=True,sensor_value=70)
        m.edge();self.assertTrue(m.request)
        self.assertEqual(m.reports,0)
        m.edge(accept=True)
        self.assertEqual(m.mode,Mode.INFLIGHT)
        self.assertEqual(m.reports,0)
        m.edge(complete=True)
        self.assertEqual(m.reports,1)
        self.assertFalse(m.request)
        for _ in range(11):m.edge(tick=True,sensor_value=70);m.edge()
        self.assertTrue(m.request)
        for _ in range(2):
            m.edge(accept=True);m.edge(complete=True)
            if m.mode != Mode.PASSIVE:
                for _ in range(11):m.edge(tick=True,sensor_value=70);m.edge()
        self.assertEqual(m.mode,Mode.PASSIVE)
        self.assertEqual(m.reports,3)
        self.assertFalse(m.request)
    def test_timebase_overflow_fails_closed(self):
        m=self.load(self.default())
        m.elapsed_ms=65535
        m.edge(tick=True,sensor_value=70)
        self.assertEqual(m.mode,Mode.FAILED)
        self.assertFalse(m.request)
    def test_abort_fail_closed_and_brownout_reload(self):
        m=self.load(self.default())
        for _ in range(2):m.edge(tick=True,sensor_value=70);m.edge()
        self.assertTrue(m.request)
        m.edge(accept=True);m.edge(abort=True)
        self.assertEqual(m.mode,Mode.FAILED)
        for _ in range(300):m.edge(tick=True,accept=True,complete=True)
        self.assertEqual(m.reports,0)
        self.assertFalse(m.request)
        m.reset()
        self.assertFalse(m.mission_valid)
        self.assertEqual(m.mode,Mode.LOAD)
    def test_periodic_and_varying_seed(self):
        p=missionc.unpack(self.default());p.update(task=2,threshold=0,seed=15,max_reports=1)
        m=self.load(missionc.pack(p))
        for _ in range(14):m.edge(tick=True,sensor_value=0);m.edge()
        self.assertFalse(m.request)
        m.edge(tick=True,sensor_value=0);m.edge()
        self.assertTrue(m.request)
    def test_reject_malformed_semantics_recrc(self):
        orig=missionc.unpack(self.default())
        invalids=[{'version':2},{'task':3},{'sensor':2},{'sample_period':0},
                  {'report_period':0},{'max_reports':0},{'flags':1},
                  {'task':2,'threshold':1},{'threshold':0}]
        for changes in invalids:
            raw={**orig,**changes}
            word=0
            for name,width in missionc.FIELDS:word=(word<<width)|raw[name]
            body=word.to_bytes(7,'big');img=body+bytes([missionc.crc8(body)])
            self.assertTrue(self.load(img).bad)
    def test_random_valid_configs(self):
        rng=random.Random(20261024)
        for _ in range(500):
            orig=missionc.unpack(self.default());t=rng.choice((1,2))
            orig.update(task=t,threshold=rng.randrange(1,64) if t==1 else 0,
                sample_period=rng.randrange(1,64),report_period=rng.randrange(1,64),
                max_reports=rng.randrange(1,64),seed=rng.randrange(4096))
            m=self.load(missionc.pack(orig))
            self.assertTrue(m.mission_valid)
            self.assertEqual(m.fields()['task'],t)
            self.assertEqual(m.fields()['max_reports'],orig['max_reports'])
    def test_film_release_includes_serial_engine_and_mission(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)/'film'
            p=subprocess.run([sys.executable,str(ROOT/'tools/wcmctl.py'),'build',
                '--device','film-reference','--out',str(out)],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual((out/'mission.bin').read_bytes(),self.default())
            self.assertEqual((out/'rtl/mission_serial_bits.txt').read_text().strip(),
                             ''.join(f'{b:08b}' for b in self.default()))
            self.assertTrue((out/'rtl/wcm_mission64_endpoint.v').is_file())
            self.assertTrue((out/'rtl/wcm_mission64_engine.v').is_file())
            reject=subprocess.run([sys.executable,str(ROOT/'tools/wcmctl.py'),'install',
                '--bundle',str(out),'--device-root',str(pathlib.Path(tmp)/'installed')],
                capture_output=True,text=True)
            self.assertNotEqual(reject.returncode,0)

if __name__=='__main__':unittest.main()
