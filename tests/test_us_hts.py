"""The US side, tested on real rows excerpted from HTSUS 2026 Revision 22."""

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hs_crosswalk.text import clean, digits
from hs_crosswalk.us_hts import (
    HtsFormatError,
    compare_with_csv,
    load_json,
    load_schedule,
    parse_records,
)

from . import US_CSV, US_JSON


class TextTests(unittest.TestCase):
    def test_clean_collapses_whitespace_and_zero_width(self):
        self.assertEqual(clean("  Other ​  goods \n"), "Other goods")
        self.assertEqual(clean(None), "")

    def test_digits(self):
        self.assertEqual(digits("0101.21.00.10"), "0101210010")
        self.assertEqual(digits(""), "")


class ScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.us = load_schedule(US_JSON)
        cls.by_code = {r.code: r for r in cls.us.rows if r.code}

    def test_every_source_row_is_kept(self):
        self.assertEqual(len(self.us.rows), 118)

    def test_grouping_rows_are_context_not_codes(self):
        grouping = [r for r in self.us.rows if not r.code]
        self.assertTrue(grouping)
        self.assertNotIn("", self.by_code)
        horse = self.by_code["0101210010"]
        self.assertEqual(
            horse.full_path,
            "Live horses, asses, mules and hinnies: > Horses: > Purebred breeding animals > Males",
        )

    def test_parent_is_nearest_smaller_indent(self):
        rows = self.us.rows
        child = self.by_code["0101210020"]
        self.assertEqual(rows[child.parent].code, "01012100")

    def test_indent_gap_invents_no_ancestor(self):
        # 3821.00.00 is printed at indent 0 and its statistical lines at indent 2.
        rows = self.us.rows
        line = self.by_code["3821000010"]
        self.assertEqual(line.indent, 2)
        self.assertEqual(rows[line.parent].code, "38210000")
        self.assertEqual(rows[line.parent].indent, 0)
        self.assertEqual(line.full_path.count(" > "), 1)
        self.assertGreater(self.us.indent_gaps(), 0)

    def test_leaves(self):
        self.assertTrue(self.by_code["0101210010"].is_leaf)
        self.assertFalse(self.by_code["01012100"].is_leaf)
        self.assertTrue(self.by_code["0101300000"].is_leaf)
        # Watch lines in chapter 91 have no statistical suffix and are leaves at 8 digits.
        self.assertTrue(self.by_code["91011140"].is_leaf)
        self.assertFalse(self.by_code["0101"].is_leaf)

    def test_rate_line_points_at_the_line_with_rates(self):
        self.assertEqual(self.by_code["0101210010"].rate_line, "0101.21.00")
        self.assertEqual(self.by_code["0101300000"].rate_line, "0101.30.00.00")
        self.assertEqual(self.by_code["0101"].rate_line, "")
        self.assertEqual(self.by_code["0101300000"].general, "6.8%")
        self.assertEqual(self.by_code["0101210010"].units, ("No.",))

    def test_whitespace_is_normalised(self):
        for r in self.us.rows:
            self.assertEqual(r.description, clean(r.description))
            self.assertNotIn("​", r.description)

    def test_footnotes_render(self):
        notes = [f.render() for f in self.by_code["91011140"].footnotes]
        self.assertEqual(notes, ["[stat, units] See statistical note 1 to this chapter."])
        numbered = [f.render() for f in self.by_code["9801001012"].footnotes]
        self.assertTrue(numbered[0].startswith("(1) [units] "))

    def test_hs6_and_national(self):
        self.assertEqual(self.by_code["0101210010"].hs6, "010121")
        self.assertEqual(self.by_code["9801001010"].hs6, "")
        self.assertTrue(self.by_code["99038905"].is_national)
        self.assertNotIn("980100", self.us.hs6_codes())

    def test_hs6_titles(self):
        t = self.us.hs6_titles()
        self.assertEqual((t["010190"].title, t["010190"].kind), ("Other:", "subheading_row"))
        self.assertEqual((t["010121"].title, t["010121"].kind), ("Purebred breeding animals", "national_line"))
        self.assertEqual(t["080270"].kind, "grouping_row")
        self.assertEqual(t["080270"].title, "Kola nuts (Cola spp.):")
        self.assertEqual(t["340700"].kind, "heading_row")
        self.assertEqual(t["382100"].kind, "national_line")

    def test_stats(self):
        s = self.us.stats()
        self.assertEqual(s["rows"], 118)
        self.assertEqual(s["rows"], s["grouping_rows"] + s["coded_rows"])
        self.assertEqual(s["leaves"], s["goods_leaves"] + s["national_leaves"])
        self.assertEqual(s["goods_leaves_by_level"]["8"], 18)


class FormatTests(unittest.TestCase):
    def test_bad_indent_is_refused(self):
        with self.assertRaises(HtsFormatError):
            parse_records([{"htsno": "0101", "indent": "x", "description": "A"}])

    def test_bad_code_length_is_refused(self):
        with self.assertRaises(HtsFormatError):
            parse_records([{"htsno": "0101.2", "indent": "0", "description": "A"}])


class CsvAgreementTests(unittest.TestCase):
    def test_fixture_json_and_csv_agree(self):
        result = compare_with_csv(load_json(US_JSON), US_CSV)
        self.assertEqual((result["json_rows"], result["csv_rows"], result["mismatches"]), (118, 118, 0))

    def test_a_changed_rate_is_reported(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        with open(US_CSV, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        rows[9][4] = "9.9%"  # 0101.30.00.00 general rate
        bad = tmp / "bad.csv"
        with open(bad, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows(rows)
        result = compare_with_csv(load_json(US_JSON), bad)
        self.assertEqual(result["mismatches"], 1)
        self.assertEqual(result["examples"][0]["field"], "general")

    def test_wrong_header_is_refused(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        bad = tmp / "bad.csv"
        bad.write_text("a,b,c\n", encoding="utf-8")
        with self.assertRaises(HtsFormatError):
            compare_with_csv(json.loads(US_JSON.read_text(encoding="utf-8")), bad)


if __name__ == "__main__":
    unittest.main()
