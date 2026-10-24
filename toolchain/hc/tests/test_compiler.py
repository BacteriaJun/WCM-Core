# Modified for v1.0.0: normalized public identifiers and technical documentation.
import copy
import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from src.compiler import SpecificationError, generate, validate

ROOT=Path(__file__).resolve().parents[1]
with (ROOT/'examples/reference_core.toml').open('rb') as f: GOOD=tomllib.load(f)

class CompilerTests(unittest.TestCase):
    def test_good_budget_and_bits(self):
        capacity,t=validate(copy.deepcopy(GOOD))
        self.assertEqual(int(capacity),2625)
        self.assertEqual(t['tx']['worst_case_nJ'],800)
    def test_reproducible_build(self):
        with tempfile.TemporaryDirectory() as d:
            a=generate(copy.deepcopy(GOOD),ROOT/'examples/reference_core.toml',Path(d)/'a')
            b=generate(copy.deepcopy(GOOD),ROOT/'examples/reference_core.toml',Path(d)/'b')
            self.assertEqual(a,b)
            self.assertEqual((Path(d)/'a/wcm_reference_core.v').read_bytes(),(Path(d)/'b/wcm_reference_core.v').read_bytes())
            text=(Path(d)/'a/wcm_reference_core.v').read_text()
            self.assertIn('module wcm_reference_core',text)
            self.assertIn('wcm_hc_fixed_core #(.FRAME_BITS(8))',text)
            self.assertIn('w0_live && w1_live && local_mission_authorized &&',text)
            self.assertIn('!observation_dirty_latched;',text)
            self.assertEqual(a['declared_sequential_bits_without_frontend_or_driver'],20)
            self.assertEqual(a['required_capacitance_density_nF_per_mm2'],7500.0)
    def test_variable_frame(self):
        for bits in (2,4,8,16,32):
            cfg=copy.deepcopy(GOOD);cfg['frame_bits']=bits
            cfg['transactions']['tx']['worst_case_nJ']=max(800,40+bits*30)
            cfg['transactions']['tx']['deadline_us']=max(1500,bits*100+100)
            cfg['witness'][0]['max_age_us']=max(2000,cfg['transactions']['tx']['deadline_us'])
            cfg['witness'][1]['max_age_us']=max(2000,cfg['transactions']['tx']['deadline_us'])
            with self.subTest(bits=bits),tempfile.TemporaryDirectory() as d:
                meta=generate(cfg, ROOT/'examples/reference_core.toml',d)
                self.assertEqual(meta['frame_bits'],bits)
                self.assertTrue((Path(d)/'wcm_reference_core.v').exists())
    def test_disabled_action_is_hardwired(self):
        cfg=copy.deepcopy(GOOD);cfg['transactions']['aero']['enabled']=False
        with tempfile.TemporaryDirectory() as d:
            generate(cfg, ROOT/'examples/reference_core.toml',d)
            text=(Path(d)/'wcm_reference_core.v').read_text()
            self.assertIn(".req_aero(1'b0)",text)
            self.assertIn(".aero_energy_ok(1'b0)",text)
    def test_rejected_specs(self):
        mods={
            'unknown schema key':lambda c:c.update(untrusted='yes'),
            'bad schema':lambda c:c.update(schema=2),
            'invalid identifier':lambda c:c.update(name='AAA;eval'),
            'no witness':lambda c:c.update(witness=[]),
            'same witness':lambda c:c['witness'][1].update(name='mission'),
            'bad age':lambda c:c['witness'][0].update(max_age_us=0),
            'bad capacitor':lambda c:c['power'].update(capacitance_nF=0),
            'reversed voltage':lambda c:c['power'].update(v_high_mV=1000),
            'unknown voltage units':lambda c:c['power'].update(v_high_V=3.0),
            'bad efficiency':lambda c:c['power'].update(efficiency_ppm=2000000),
            'insufficient energy':lambda c:c['power'].update(capacitance_nF=1),
            'too-long deadline':lambda c:c['transactions']['tx'].update(deadline_us=2001),
            'false source proof':lambda c:c['trust_boundary'].update(qualified_local_policy_authorization=False),
            'missing proof':lambda c:c['trust_boundary'].pop('independent_time_watchdog'),
            'float energy':lambda c:c['transactions']['tx'].update(worst_case_nJ=800.4),
            'disabled both':lambda c:[c['transactions'][t].update(enabled=False) for t in ('tx','aero')],
            'huge frame':lambda c:c.update(frame_bits=65),
            'frame exceeds deadline':lambda c:c['transactions']['tx'].update(deadline_us=500),
            'frame energy insufficient':lambda c:c['transactions']['tx'].update(worst_case_nJ=50),
            'aero execution slower than deadline':lambda c:c['transactions']['aero'].update(deadline_us=100),
            'aero energy insufficient':lambda c:c['transactions']['aero'].update(worst_case_nJ=100),
            'oversize node':lambda c:c['geometry'].update(max_span_um=1001),
            'bad capacitor area fraction':lambda c:c['geometry'].update(capacitor_area_fraction_ppm=1000001),
        }
        for label, fn in mods.items():
            cfg=copy.deepcopy(GOOD);fn(cfg)
            with self.subTest(label=label),self.assertRaises(SpecificationError):validate(cfg)

if __name__=='__main__':unittest.main()
