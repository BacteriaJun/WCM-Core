# Modified for v1.0.0: normalized public identifiers and technical documentation.
import unittest
from tools.gen_trace_tb import render

class TraceTests(unittest.TestCase):
    def test_repeatable_reference_vectors(self):
        a,n=render(seed=20261023,rounds=12,per_round=48)
        b,m=render(seed=20261023,rounds=12,per_round=48)
        self.assertEqual(n,780)
        self.assertEqual(n,m)
        self.assertEqual(a,b)
        self.assertEqual(a.count('reg clk = 0;'),1)
        self.assertNotIn('reg clk = 1\'b0;',a)
        self.assertEqual(a.count('state mismatch at cycle '),n)
        self.assertEqual(a.count('actuator_authority mismatch at cycle '),n)
        self.assertIn('PASS reference-vs-RTL trace: 780 stimulus cycles',a)
