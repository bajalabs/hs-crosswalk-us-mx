"""The committed manifest and the hash check on downloads (no network: file:// URLs)."""

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hs_crosswalk import sources

HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ManifestTests(unittest.TestCase):
    def test_us_sources_are_pinned(self):
        m = sources.load_manifest(sources.DEFAULT_MANIFEST)
        us = m["us_hts"]
        self.assertRegex(us["release"], r"^\d{4}HTSRev\d+$")
        self.assertRegex(us["published"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(set(us["files"]), {"json", "csv"})
        for f in us["files"].values():
            self.assertTrue(f["url"].startswith("https://www.usitc.gov/"))
            self.assertRegex(f["sha256"], HEX64)
            self.assertTrue(f["url"].endswith(f["name"]))

    def test_mx_entry_has_the_contract_files(self):
        m = sources.load_manifest(sources.DEFAULT_MANIFEST)
        files = m["mx_tigie"]["files"]
        self.assertEqual({f["name"] for f in files.values()},
                         {"subpartidas.csv", "fracciones.csv", "nicos.csv"})
        for f in files.values():
            self.assertTrue(f["sha256"] is None or HEX64.match(f["sha256"]))
        self.assertTrue(m["mx_tigie"]["release_url"].startswith("https://"))


class RequestTests(unittest.TestCase):
    def test_python_user_agent_is_kept_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HSX_USER_AGENT", None)
            self.assertIsNone(sources.request("https://example.org/").get_header("User-agent"))

    def test_user_agent_can_be_set(self):
        with mock.patch.dict(os.environ, {"HSX_USER_AGENT": "tester/1"}):
            self.assertEqual(sources.request("https://example.org/").get_header("User-agent"), "tester/1")


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src = self.tmp / "src.txt"
        self.src.write_bytes(b"tariff\n")
        self.digest = sources.sha256_file(self.src)

    def test_matching_hash_is_accepted(self):
        dest = self.tmp / "out" / "file.txt"
        digest, size = sources.download(self.src.as_uri(), dest, self.digest)
        self.assertEqual((digest, size), (self.digest, 7))
        self.assertEqual(dest.read_bytes(), b"tariff\n")

    def test_wrong_hash_is_refused_and_nothing_is_kept(self):
        dest = self.tmp / "out" / "file.txt"
        with self.assertRaises(sources.SourceError):
            sources.download(self.src.as_uri(), dest, "0" * 64)
        self.assertFalse(dest.exists())
        self.assertEqual(list(dest.parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
