"""The HS-6 join: many-to-many inside a subheading, one-sided rows, national chapters."""

import unittest
from collections import Counter

from hs_crosswalk import crosswalk as xw
from hs_crosswalk.mx_tigie import load_tigie
from hs_crosswalk.us_hts import load_schedule

from . import MX_DIR, US_JSON


class CrosswalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.us = load_schedule(US_JSON)
        cls.mx = load_tigie(MX_DIR)
        cls.rows, cls.hs6_rows, cls.coverage = xw.build(cls.us, cls.mx)

    def pairs(self, hs6):
        return {(r.us_hts10, r.mx_codigo10) for r in self.rows if r.hs6 == hs6}

    def test_many_to_many_inside_a_subheading(self):
        self.assertEqual(
            self.pairs("010129"),
            {
                ("0101290010", "0101299901"),
                ("0101290010", "0101299999"),
                ("0101290090", "0101299901"),
                ("0101290090", "0101299999"),
            },
        )
        notes = {r.notes for r in self.rows if r.hs6 == "010129"}
        self.assertEqual(notes, {"n:n at HS-6 (US 2, MX 2)"})

    def test_one_sided_subheadings(self):
        us_only = [r for r in self.rows if r.hs6 == "010130"]
        self.assertEqual([(r.us_hts10, r.mx_codigo10, r.match_level) for r in us_only],
                         [("0101300000", "", "us_only")])
        mx_only = [r for r in self.rows if r.hs6 == "030111"]
        self.assertEqual([(r.us_hts10, r.mx_codigo10, r.match_level) for r in mx_only],
                         [("", "0301110100", "mx_only")])

    def test_national_chapters_are_never_matched(self):
        national = [r for r in self.rows if r.match_level == "national"]
        self.assertTrue(national)
        for r in national:
            self.assertEqual(r.hs6, "")
            self.assertTrue(bool(r.us_hts10) != bool(r.mx_codigo10))
            code = r.us_hts10 or r.mx_codigo10
            self.assertIn(code[:2], {"98", "99"})

    def test_every_line_appears_at_least_once(self):
        us_seen = {r.us_hts10 for r in self.rows if r.us_hts10}
        mx_seen = {r.mx_codigo10 for r in self.rows if r.mx_codigo10}
        self.assertEqual(us_seen, {r.code for r in self.us.leaves})
        self.assertEqual(mx_seen, {line.code for line in self.mx.lines})

    def test_matched_rows_share_the_subheading(self):
        for r in self.rows:
            if r.match_level == "hs6":
                self.assertEqual(r.us_hts10[:6], r.hs6)
                self.assertEqual(r.mx_codigo10[:6], r.hs6)

    def test_hs6_table(self):
        by = {h["hs6"]: h for h in self.hs6_rows}
        self.assertEqual(by["010121"]["title_es"], "Reproductores de raza pura.")
        self.assertEqual(by["010121"]["title_en"], "Purebred breeding animals")
        self.assertEqual((by["010130"]["in_us"], by["010130"]["in_mx"]), (1, 0))
        self.assertEqual((by["030111"]["in_us"], by["030111"]["in_mx"]), (0, 1))
        self.assertEqual(by["030111"]["title_en"], "")

    def test_coverage_adds_up(self):
        h = self.coverage["hs6"]
        self.assertEqual(h["total"], h["both"] + h["us_only"] + h["mx_only"])
        self.assertEqual((h["both"], h["us_only"], h["mx_only"]), (9, 20, 1))
        levels = self.coverage["crosswalk"]["by_match_level"]
        self.assertEqual(sum(levels.values()), len(self.rows))
        self.assertEqual(Counter(r.match_level for r in self.rows)["national"], levels["national"])
        self.assertEqual(sum(h["matched_shapes"].values()), h["both"])


if __name__ == "__main__":
    unittest.main()
