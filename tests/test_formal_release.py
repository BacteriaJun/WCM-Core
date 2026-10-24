# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Verify formal report presence and correctness after make formal-check.
Not a substitute for running SMT solver; `make test` does both.
"""
import json
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class FormalReleaseTests(unittest.TestCase):
    def test_z3_report_all_obligations_conclusive(self):
        p=ROOT/'verification/reports/formal_results.json'
        self.assertTrue(p.is_file(),'run make formal-check first')
        report=json.loads(p.read_text())
        self.assertTrue(report['passed'])
        self.assertGreaterEqual(len(report['obligations']),25)
        self.assertTrue(all(entry['pass'] for entry in report['obligations']))
        self.assertTrue(all(entry['solver_result'] in ('sat','unsat') for entry in report['obligations']))
        self.assertEqual(sum(entry['solver_result']=='sat' for entry in report['obligations']),1)
    def test_exact_smt_sources_published(self):
        entries=json.loads((ROOT/'verification/reports/formal_results.json').read_text())['obligations']
        import hashlib
        for result in entries:
            query=(ROOT/'verification/formal/smt2'/f'{result["name"]}.smt2').read_bytes()
            self.assertEqual(hashlib.sha256(query).hexdigest(),result['query_sha256'])
    def test_pin_manifest_matches_actual_sources(self):
        pin=json.loads((ROOT/'verification/formal/implementation_pins.json').read_text())['sha256']
        import hashlib
        for name,digest in pin.items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)
if __name__=='__main__':unittest.main()
