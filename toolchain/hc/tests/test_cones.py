# Modified for v1.0.0: normalized public identifiers and technical documentation.
import tempfile
import unittest
from pathlib import Path
from tools.check_rtl_cones import verify

ROOT=Path(__file__).resolve().parents[1]

class ConeTests(unittest.TestCase):
    def test_emitted_cones(self):
        self.assertEqual(verify(ROOT/'build/wcm_reference_core.v'),53)

    def test_mutated_fault_gate_is_rejected(self):
        original=(ROOT/'build/wcm_reference_core.v').read_text()
        changed=original.replace('assign optical_reflect = hard_enable && evidence_output_ok',
                                 'assign optical_reflect = evidence_output_ok')
        self.assertNotEqual(original,changed)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mutant.v';p.write_text(changed)
            with self.assertRaisesRegex(AssertionError,'forbidden condition'):
                verify(p)

    def test_dirty_gate_is_essential(self):
        original=(ROOT/'build/wcm_reference_core.v').read_text()
        # Make a mutant that allows dirty events through both gates.
        changed=original.replace('&&\n                           !observation_dirty_latched;', ';')
        changed=changed.replace(' && !observation_dirty_latched;', ';')
        self.assertNotEqual(original,changed)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mutant.v';p.write_text(changed)
            with self.assertRaisesRegex(AssertionError,'observation_dirty_latched'):
                verify(p)
