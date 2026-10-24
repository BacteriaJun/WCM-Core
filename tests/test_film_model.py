# Modified for v1.0.0: normalized public identifiers and technical documentation.
import importlib.util
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'hardware/film/model/reference.py'
spec=importlib.util.spec_from_file_location('filmreference',source)
model=importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
class FilmModelSmoke(unittest.TestCase):
    def test_precondition_guard(self):
        s=model.State()
        self.assertFalse(model.outputs(s,model.Event('initial'))['authority'])
        self.assertFalse(model.outputs(s,model.Event('initial'))['optical'])
