# Changelog

All notable changes to this project are listed here. Versions follow [Semantic Versioning](https://semver.org/):
a new HTSUS revision or TIGIE release without a schema change is a minor version; a changed or removed column is a
major version.

## 1.0.0 (2026-11-10)

First release.

- US side: HTSUS 2026 Revision 22 (published 2026-10-30), 35,805 rows. The JSON and CSV exports are checked
  against each other before the build (0 disagreements). Indent hierarchy kept; grouping rows are context only.
- Mexican side: tigie-nico-mx v1.0.0 (5,619 subpartidas, 8,183 fracciones, 11,507 current NICOs).
- Outputs: `us_hts.csv`, `hs6.csv`, `crosswalk.csv`, `coverage.json`, `coverage_by_chapter.csv`,
  `hs-crosswalk-us-mx.sqlite`, `build-manifest.json`, `SHA256SUMS`.
- Coverage: 5,612 HS-6 subheadings, all 5,612 present on both sides; 76,134 crosswalk rows.
