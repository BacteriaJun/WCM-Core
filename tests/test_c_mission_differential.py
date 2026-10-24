# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Sampled cross-language mission checks across C17, Python and the Film behavioral oracle.
"""
import ctypes
import importlib.util
import pathlib
import random
import subprocess
import sys
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'toolchain/mission'))
from missionc import pack,unpack
sys.path.insert(0,str(ROOT/'hardware/film/model'))
from mission64_reference import FilmMission

class M(ctypes.Structure):
    _fields_=[('version',ctypes.c_uint8),('task',ctypes.c_uint8),('sensor',ctypes.c_uint8),
             ('threshold',ctypes.c_uint8),('sample_period',ctypes.c_uint8),
             ('report_period',ctypes.c_uint8),('max_reports',ctypes.c_uint8),
             ('seed',ctypes.c_uint16),('flags',ctypes.c_uint8)]

class CodecDifferential(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='wcm-codec-')
        lib=pathlib.Path(cls.temp.name)/'libmission.so'
        subprocess.run(['gcc','-std=c17','-O2','-fPIC','-shared','-Wall','-Wextra',
                       '-Werror',str(ROOT/'system/mission/wcm_mission64.c'),'-o',str(lib)],check=True)
        cls.native=ctypes.CDLL(str(lib))
        cls.native.wcm_mission_decode.argtypes=(ctypes.POINTER(ctypes.c_uint8),ctypes.POINTER(M))
        cls.native.wcm_mission_decode.restype=ctypes.c_bool
        cls.native.wcm_mission_due.argtypes=(ctypes.POINTER(M),ctypes.c_uint16,
            ctypes.c_uint32,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_uint8)
        cls.native.wcm_mission_due.restype=ctypes.c_bool
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def decode(self,raw):
        image=(ctypes.c_uint8*8)(*raw);record=M()
        accepted=bool(self.native.wcm_mission_decode(image,ctypes.byref(record)))
        film=FilmMission()
        for byte in raw:
            for bit in range(7,-1,-1):film.bit((byte>>bit)&1)
        return accepted,record,film
    def test_6000_random_raw_missions(self):
        rng=random.Random(0x573C01)
        for _ in range(6000):
            raw=rng.randbytes(8)
            accepted,_,film=self.decode(raw)
            try:unpack(raw);py=True
            except ValueError:py=False
            self.assertEqual(accepted,py,raw.hex())
            self.assertEqual(accepted,film.mission_valid,raw.hex())
    def test_1000_random_valid_missions_and_due(self):
        rng=random.Random(0x573C02)
        for _ in range(1000):
            t=rng.choice((1,2));thr=rng.randrange(1,64) if t==1 else 0
            mission=dict(version=1,task=t,sensor=1,threshold=thr,
                sample_period=rng.randint(1,63),report_period=rng.randint(1,63),
                max_reports=rng.randint(1,63),seed=rng.randrange(4096),flags=0)
            raw=pack(mission);accepted,m,film=self.decode(raw)
            self.assertTrue(accepted)
            self.assertTrue(film.mission_valid)
            self.assertEqual(film.fields()['seed'],mission['seed'])
            for _ in range(8):
                sensor=rng.randrange(0,1000);samples=rng.randrange(0,50)
                last=rng.randrange(0,1000000);elapsed=rng.randrange(0,1000000)
                reports=rng.randrange(0,64)
                expected=(samples>0 and reports<mission['max_reports'] and
                    (t==2 or sensor>=10*thr) and
                    (elapsed>=((mission['seed']%16)*1000) if reports==0 else
                      (elapsed>=last and elapsed-last>=mission['report_period']*10000)))
                got=self.native.wcm_mission_due(ctypes.byref(m),sensor,samples,
                    elapsed,last,reports)
                self.assertEqual(got,expected,(mission,sensor,samples,reports))
    def test_all_single_bit_mutations_of_128_valid_missions(self):
        rng=random.Random(0x573C03)
        for _ in range(128):
            m=dict(version=1,task=1,sensor=1,threshold=rng.randint(1,63),
                   sample_period=rng.randint(1,63),report_period=rng.randint(1,63),
                   max_reports=rng.randint(1,63),seed=rng.randrange(4096),flags=0)
            raw=pack(m);word=int.from_bytes(raw,'big')
            for b in range(64):
                bad=(word ^ (1<<b)).to_bytes(8,'big')
                accepted,_,film=self.decode(bad)
                self.assertFalse(accepted,bad.hex())
                self.assertFalse(film.mission_valid,bad.hex())

if __name__=='__main__':unittest.main()
