# Modified for v1.0.0: normalized public identifiers and technical documentation.
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('missionc',ROOT/'toolchain/mission/missionc.py')
mission=importlib.util.module_from_spec(spec);spec.loader.exec_module(mission)

class TestOfflineMission(unittest.TestCase):
    def default(self):return mission.parse_spec(ROOT/'devices/virtual-node/mission.toml')
    def test_golden_64bit(self):
        img=mission.pack(self.default())
        self.assertEqual(img.hex(),'11118104300000f7')
        self.assertEqual(mission.unpack(img),self.default())
    def test_bit_flip_crc(self):
        img=bytearray(mission.pack(self.default()))
        for i in range(8):
            for b in range(8):
                bad=img.copy();bad[i]^=1<<b
                with self.assertRaises(mission.MissionError):mission.unpack(bytes(bad))
    def test_reject_unsupported_and_bad_config(self):
        for values in [dict(self.default(),flags=1),dict(self.default(),version=2),
                       dict(self.default(),sample_period=0),dict(self.default(),max_reports=0),
                       dict(self.default(),threshold=0),dict(self.default(),seed=4096),
                       dict(self.default(),task=3),dict(self.default(),sample_period=-1)]:
            with self.assertRaises(mission.MissionError):mission.pack(values)
    def test_periodic_profile(self):
        x=dict(self.default(),task=2,threshold=0,max_reports=1,seed=4095)
        self.assertEqual(mission.unpack(mission.pack(x)),x)
    def test_batch_readback_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            result=mission.provision(mission.pack(self.default()),18,base/'batch')
            self.assertFalse(result['hardware_written'])
            m=json.loads((base/'batch/batch.json').read_text())
            self.assertEqual(len(m['records']),18)
            seeds=[]
            for e in m['records']:
                data=(base/'batch'/e['file']).read_bytes()
                self.assertEqual(len(data),8)
                seeds.append(mission.unpack(data)['seed'])
            self.assertEqual(len(set(seeds)),18)
            with self.assertRaises(mission.MissionError):
                mission.provision(mission.pack(self.default()),18,base/'batch')
    def test_seed_collision_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(mission.MissionError):
                mission.provision(mission.pack(self.default()),3,Path(temp)/'bad',2048)

    def test_custom_tasks_change_device_behavior(self):
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('wcmctl',ROOT/'tools/wcmctl.py')
        ctl=module_from_spec(spec);spec.loader.exec_module(ctl)
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            periodic=dict(self.default(),task=2,threshold=0,max_reports=2,seed=5)
            p=d/'periodic.bin';p.write_bytes(mission.pack(periodic))
            image=d/'image';ctl.build('virtual-node',image,mission_image=p)
            ctl.install(image,d/'device')
            boot=ctl.boot(d/'device')
            self.assertEqual(boot['mission_task'],2)
            self.assertEqual(boot['reports_sent'],2)
            self.assertEqual(boot['optical_symbols_emitted'],64)
            impossible=dict(self.default(),task=1,threshold=63,max_reports=2)
            q=d/'impossible.bin';q.write_bytes(mission.pack(impossible))
            ctl.build('virtual-node',d/'image2',mission_image=q)
            ctl.install(d/'image2',d/'device2')
            boot2=ctl.boot(d/'device2')
            self.assertEqual(boot2['reports_sent'],0)
            self.assertEqual(boot2['optical_symbols_emitted'],0)
            # Integrity gate refuses tampering with the preprovisioned bytes.
            (d/'device2'/'mission.bin').write_bytes(p.read_bytes())
            with self.assertRaisesRegex(ctl.ReleaseError,'sha256 mismatch'):
                ctl.boot(d/'device2')

    def test_cli_compile_and_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp);command=['python3',str(ROOT/'tools/wcmctl.py')]
            subprocess.run(command+['mission-compile','--source',str(ROOT/'devices/virtual-node/mission.toml'),'--out',str(a/'mission.bin')],check=True,capture_output=True)
            subprocess.run(command+['provision-batch','--mission',str(a/'mission.bin'),'--count','8','--out',str(a/'batch')],check=True,capture_output=True)
            self.assertEqual(len(list((a/'batch').glob('node-*.bin'))),8)
            self.assertTrue((a/'batch/batch.json').is_file())

if __name__=='__main__':unittest.main()
