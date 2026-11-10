"""End to end: the command line builds every release file from the fixtures."""

import contextlib
import csv
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hs_crosswalk.cli import main
from hs_crosswalk.sources import sha256_file

from . import MX_DIR, US_CSV, US_JSON

EXPECTED = {
    "us_hts.csv",
    "hs6.csv",
    "crosswalk.csv",
    "coverage.json",
    "coverage_by_chapter.csv",
    "hs-crosswalk-us-mx.sqlite",
    "build-manifest.json",
    "SHA256SUMS",
}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def build(self, out, *extra):
        return run(
            "build",
            "--us-json", str(US_JSON),
            "--us-csv", str(US_CSV),
            "--mx-dir", str(MX_DIR),
            "--out", str(out),
            *extra,
        )

    def test_full_build(self):
        out = self.tmp / "dist"
        code, stdout, stderr = self.build(out)
        self.assertEqual(code, 0, stderr)
        self.assertEqual({p.name for p in out.iterdir()}, EXPECTED)

        for line in (out / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(sha256_file(out / name), digest, name)

        us = read_csv(out / "us_hts.csv")
        xw = read_csv(out / "crosswalk.csv")
        hs6 = read_csv(out / "hs6.csv")
        self.assertEqual(list(us[0])[:6], ["code", "htsno", "level", "indent", "description", "full_path"])
        self.assertEqual(list(xw[0]), ["us_hts10", "mx_codigo10", "hs6", "match_level", "notes"])
        self.assertEqual(list(hs6[0])[:5], ["hs6", "title_en", "title_es", "in_us", "in_mx"])
        self.assertTrue(all(r["code"] for r in us))

        db = sqlite3.connect(out / "hs-crosswalk-us-mx.sqlite")
        self.addCleanup(db.close)
        count = lambda t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: E731
        self.assertEqual(count("us_hts"), len(us))
        self.assertEqual(count("crosswalk"), len(xw))
        self.assertEqual(count("hs6"), len(hs6))
        self.assertEqual(count("us_tree"), 118)
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        row = db.execute(
            "SELECT us_description, us_general_rate, mx_descripcion, mx_igi FROM v_crosswalk "
            "WHERE us_hts10 = '0101290010' AND mx_codigo10 = '0101299901'"
        ).fetchone()
        self.assertEqual(row, ("Imported for immediate slaughter", "Free", "Para abasto.", "20"))

        manifest = json.loads((out / "build-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["sources"]["us_hts"]["json_csv_check"]["mismatches"], 0)
        self.assertFalse(manifest["sources"]["us_hts"]["pinned"])
        self.assertNotIn(str(self.tmp), json.dumps(manifest))

    def test_build_is_reproducible(self):
        a, b = self.tmp / "a", self.tmp / "b"
        self.assertEqual(self.build(a)[0], 0)
        self.assertEqual(self.build(b)[0], 0)
        self.assertEqual((a / "SHA256SUMS").read_text(), (b / "SHA256SUMS").read_text())

    def test_us_only_build(self):
        out = self.tmp / "us"
        code, _, stderr = run(
            "build", "--us-json", str(US_JSON), "--us-csv", str(US_CSV), "--us-only", "--out", str(out)
        )
        self.assertEqual(code, 0, stderr)
        self.assertFalse((out / "crosswalk.csv").exists())
        self.assertTrue((out / "us_hts.csv").exists())

    def test_disagreeing_csv_stops_the_build(self):
        bad = self.tmp / "bad.csv"
        text = US_CSV.read_text(encoding="utf-8-sig").replace('"6.8%"', '"7.0%"', 1)
        bad.write_text(text, encoding="utf-8")
        out = self.tmp / "dist"
        code, _, stderr = run(
            "build", "--us-json", str(US_JSON), "--us-csv", str(bad), "--mx-dir", str(MX_DIR),
            "--out", str(out),
        )
        self.assertEqual(code, 1)
        self.assertIn("disagree", stderr)
        self.assertFalse((out / "us_hts.csv").exists())

    def test_missing_mx_dir_is_explained(self):
        code, _, stderr = run(
            "build", "--us-json", str(US_JSON), "--us-csv", str(US_CSV),
            "--mx-dir", str(self.tmp / "nowhere"), "--out", str(self.tmp / "dist"),
        )
        self.assertEqual(code, 2)
        self.assertIn("TIGIE_CSV_DIR", stderr)


if __name__ == "__main__":
    unittest.main()
