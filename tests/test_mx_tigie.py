"""The Mexican side, tested on a small synthetic fixture in the tigie-nico-mx contract.

The fixture's descriptions are illustrative. They are not tariff data.
"""

import datetime as dt
import shutil
import tempfile
import unittest
from pathlib import Path

from hs_crosswalk.mx_tigie import TigieFormatError, load_tigie

from . import MX_DIR


class TigieTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mx = load_tigie(MX_DIR)

    def test_contract_files_are_read_with_extra_columns(self):
        self.assertEqual(len(self.mx.subpartidas), 11)
        self.assertEqual(len(self.mx.fracciones), 11)
        self.assertEqual(len(self.mx.nicos), 13)
        self.assertEqual(self.mx.issues, [])

    def test_removed_nico_is_not_a_line(self):
        codes = {line.code for line in self.mx.lines}
        self.assertNotIn("3821000198", codes)
        self.assertIn("3821000199", codes)
        self.assertEqual(self.mx.stats()["nicos_removed"], 1)

    def test_as_of_keeps_a_nico_removed_later(self):
        mx = load_tigie(MX_DIR, as_of=dt.date(2022, 1, 1))
        self.assertIn("3821000198", {line.code for line in mx.lines})

    def test_fraccion_without_nico_stands_in(self):
        line = next(line for line in self.mx.lines if line.code == "08027001")
        self.assertEqual(line.kind, "fraccion")
        self.assertEqual(line.hs6, "080270")

    def test_chapter_98_is_national(self):
        line = next(line for line in self.mx.lines if line.code == "9801000100")
        self.assertTrue(line.is_national)
        self.assertEqual(line.hs6, "")
        self.assertNotIn("980100", self.mx.hs6_codes())


class TigieContractErrors(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for f in MX_DIR.iterdir():
            shutil.copy(f, self.tmp / f.name)

    def test_missing_file(self):
        (self.tmp / "nicos.csv").unlink()
        with self.assertRaises(TigieFormatError):
            load_tigie(self.tmp)

    def test_missing_column(self):
        (self.tmp / "fracciones.csv").write_text("fraccion,subpartida\n01012101,010121\n", encoding="utf-8")
        with self.assertRaises(TigieFormatError):
            load_tigie(self.tmp)

    def test_bad_codes_are_skipped_and_reported(self):
        with open(self.tmp / "nicos.csv", "a", encoding="utf-8") as fh:
            fh.write("01012101,07,0101210199,Codigo que no coincide,2020-12-28,,x\n")
            fh.write("0101210,01,010121001,Fraccion corta,2020-12-28,,x\n")
        mx = load_tigie(self.tmp)
        self.assertEqual(len(mx.issues), 2)
        self.assertNotIn("0101210199", {line.code for line in mx.lines})

    def test_prohibited_fraccion_is_flagged(self):
        with open(self.tmp / "fracciones.csv", "a", encoding="utf-8") as fh:
            fh.write("12089003,120890,De amapola (ilustrativo).,,Prohibida,Prohibida,x\n")
        mx = load_tigie(self.tmp)
        line = next(line for line in mx.lines if line.code == "12089003")
        self.assertTrue(line.prohibited)
        self.assertEqual(line.kind, "fraccion")

    def test_byte_order_mark_is_accepted(self):
        path = self.tmp / "subpartidas.csv"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.assertEqual(len(load_tigie(self.tmp).subpartidas), 11)


if __name__ == "__main__":
    unittest.main()
