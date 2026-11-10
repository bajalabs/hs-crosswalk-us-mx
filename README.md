[Español](README.es.md)

# hs-crosswalk-us-mx

[![CI](https://github.com/bajalabs/hs-crosswalk-us-mx/actions/workflows/ci.yml/badge.svg)](https://github.com/bajalabs/hs-crosswalk-us-mx/actions/workflows/ci.yml)
[![Code: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Data: CC0-1.0](https://img.shields.io/badge/data-CC0--1.0-green.svg)](LICENSE-DATA)
[![Latest release](https://img.shields.io/github/v/release/bajalabs/hs-crosswalk-us-mx)](https://github.com/bajalabs/hs-crosswalk-us-mx/releases/latest)

The current Harmonized Tariff Schedule of the United States (HTSUS) as clean open files, joined with Mexico's tariff
(TIGIE fracciones and NICOs) at the shared 6-digit Harmonized System level, for people who trade across the
US–Mexico border.

> **An HS-6 match means the same international subheading, not equivalent national lines or duties.** Every US line
> in a subheading is paired with every Mexican line in it. Which pair fits a given product is a classification
> decision under each country's own rules. Chapters 98 and 99 of the HTSUS and chapter 98 of the TIGIE are national
> provisions outside the Harmonized System; they are listed but never matched.

## Quick start

Download the files from the [latest release](https://github.com/bajalabs/hs-crosswalk-us-mx/releases/latest) and
check them with `shasum -a 256 -c SHA256SUMS`. Or build them from a clone with Python 3.12 or newer and nothing else:

```sh
git clone https://github.com/bajalabs/hs-crosswalk-us-mx.git
cd hs-crosswalk-us-mx
python3 -m unittest                  # offline, on the committed fixtures
python3 -m hs_crosswalk fetch-us     # HTSUS 2026 Revision 22 from usitc.gov, sha256-checked
python3 -m hs_crosswalk fetch-mx     # tigie-nico-mx v1.0.0 CSV zip from GitHub, sha256-checked
python3 -m hs_crosswalk build        # writes dist/ and dist/SHA256SUMS
```

If you already have the tigie-nico-mx CSV files, skip `fetch-mx` and point the build at them with
`--mx-dir path/to/csv` or `TIGIE_CSV_DIR=path/to/csv`. With [uv](https://docs.astral.sh/uv/), prefix the commands
with `uv run` (for example `uv run python -m hs_crosswalk build`). The build takes a few seconds.

## What is inside

Built from HTSUS 2026 Revision 22 (published 2026-10-30) and tigie-nico-mx v1.0.0:

| File | Rows | Size | Content |
|---|---:|---:|---|
| `us_hts.csv` | 29,861 | 12.0 MB | every coded HTSUS row: 961 headings, 2,093 subheadings, 6,858 eight-digit and 19,949 ten-digit lines |
| `hs6.csv` | 5,612 | 1.7 MB | every HS-6 subheading with its English (HTSUS) and Spanish (TIGIE) title |
| `crosswalk.csv` | 76,134 | 4.7 MB | US line to Mexican line pairs at HS-6, plus the national lines of both sides |
| `coverage.json`, `coverage_by_chapter.csv` | 98 chapters | 19 KB | counts, coverage and the shape of every match |
| `hs-crosswalk-us-mx.sqlite` | all of the above | 32 MB | the tables above, the full US tree, the three Mexican tables and a ready-made view |
| `build-manifest.json`, `SHA256SUMS` | | | sources with sha256, options, every output's hash |

### Coverage

| | Count |
|---|---:|
| HS-6 subheadings in all | 5,612 |
| present in both the US and Mexico | 5,612 |
| US only | 0 |
| Mexico only | 0 |
| matched one US line to one Mexican line (1:1) | 1,829 |
| one US line to several Mexican lines (1:n) | 499 |
| several US lines to one Mexican line (n:1) | 1,620 |
| several to several (n:n) | 1,664 |

US side: 35,805 source rows, of which 5,944 are uncoded grouping rows. 23,529 lines have no coded subdivision: 19,926
goods lines in chapters 01–97 (19,831 ten-digit lines and 95 eight-digit watch lines in chapter 91 that carry no
statistical suffix) and 3,603 national lines in chapters 98 and 99.

Mexican side: 5,619 subpartidas (5,612 of the Harmonized System and 7 in national chapter 98), 8,183 fracciones and
11,528 NICOs, of which 11,507 are current and 21 were suppressed. The join uses 11,556 Mexican lines: the 11,507
current NICOs and 49 fracciones that have no NICO (43 of them read `Prohibida`); 55 of these lines are in chapter 98.

Crosswalk: 72,476 matched pairs and 3,658 national rows (3,603 US, 55 Mexican).

## Schema

All CSV files are UTF-8 with a header row and LF line ends. Codes are text: keep their leading zeros.

**`us_hts.csv`**, one row per coded HTSUS row, in schedule order:

| Column | Meaning |
|---|---|
| `code` | the HTS number, digits only (4, 6, 8 or 10 digits) |
| `htsno` | the HTS number as published, `0101.21.00.10` |
| `level` | 4, 6, 8 or 10 |
| `indent` | the published indent |
| `description` | the row's own text |
| `full_path` | the descriptions of every ancestor and of the row, grouping rows included, joined by ` > ` |
| `units` | units of quantity, joined by `; ` |
| `general`, `special`, `column2` | rates of duty as published (column 1 general, column 1 special, column 2) |
| `quota_quantity`, `additional_duties` | as published; mostly empty |
| `footnotes` | `(marker) [columns] text`, joined by ` \| ` |
| `hs6` | the HS-6 subheading; empty in chapters 98 and 99 |
| `chapter` | two digits |
| `is_leaf` | 1 when the row has no coded subdivision: the lines a declaration uses |
| `rate_line` | the `htsno` of the line that carries the rates for this row (statistical lines inherit their 8-digit line's rates) |
| `source_row` | the row's position in the USITC export |

**`hs6.csv`**: `hs6`, `title_en`, `title_es`, `in_us`, `in_mx` (1 or 0), `us_lines`, `mx_lines` (lines used in the
crosswalk), `title_en_kind`, `title_en_path`. `title_en_kind` says which HTSUS row gave the title: `subheading_row`
(a published 6-digit row, 2,092), `national_line` (the subheading's only national line, 3,510), `grouping_row` (an
uncoded row that covers exactly the subheading, 5), `heading_row` (a heading with a single subheading, 4) or
`first_line` (no row covers the subheading as a whole, 1: 8424.89, whose first line is narrower than the subheading).

**`crosswalk.csv`**: `us_hts10`, `mx_codigo10`, `hs6`, `match_level`, `notes`.

| `match_level` | Meaning |
|---|---|
| `hs6` | both lines sit in the same HS-6 subheading |
| `us_only` | the subheading has no Mexican line (none in this release) |
| `mx_only` | the subheading has no US line (none in this release) |
| `national` | a line of US chapters 98/99 or Mexican chapter 98; `hs6` is empty and nothing is matched |

`us_hts10` holds ten digits, except for the 95 chapter-91 lines that have only eight. `mx_codigo10` holds the NICO
code (fracción + NICO, ten digits), or the eight-digit fracción when it has no NICO. `notes` gives the shape of the
subheading, such as `n:1 at HS-6 (US 3, MX 1)`, and flags lines without a statistical suffix, fracciones without NICO
and fracciones whose duty reads `Prohibida`.

**SQLite**: tables `us_hts`, `us_tree` (all 35,805 source rows with their parent, grouping rows included),
`us_footnotes`, `hs6`, `crosswalk`, `mx_subpartidas`, `mx_fracciones`, `mx_nicos` (with `current`),
`coverage_by_chapter` and `meta`; the view `v_crosswalk` joins each pair with both descriptions, the US general rate
and the Mexican IGI.

## Example lookups

US to Mexico, avocados:

```sh
sqlite3 -header -column dist/hs-crosswalk-us-mx.sqlite \
  "SELECT us_htsno, us_description, us_general_rate, mx_codigo10, mx_descripcion, mx_igi
   FROM v_crosswalk WHERE us_hts10 LIKE '080440%'"
```

```text
us_htsno       us_description     us_general_rate  mx_codigo10  mx_descripcion       mx_igi
-------------  -----------------  ---------------  -----------  -------------------  ------
0804.40.00.20  Certified organic  11.2¢/kg         0804400100   Aguacates (paltas).  20
0804.40.00.40  Other              11.2¢/kg         0804400100   Aguacates (paltas).  20
0804.40.00.90  Other              11.2¢/kg         0804400100   Aguacates (paltas).  20
```

Mexico to the US, laptops and tablets (NICO 8471.30.01.01, *Tableta electrónica*), with nothing but Python:

```python
import csv
with open("dist/crosswalk.csv", encoding="utf-8") as fh:
    pairs = [r for r in csv.DictReader(fh) if r["mx_codigo10"] == "8471300101"]
print(pairs)
# [{'us_hts10': '8471300100', 'mx_codigo10': '8471300101', 'hs6': '847130',
#   'match_level': 'hs6', 'notes': '1:n at HS-6 (US 1, MX 2)'}]
```

Why a match is not an equivalence: in subheading 2208.90 the US line for aquavit (2208.90.01.00) is paired with the
Mexican NICOs for tequila (2208.90.03.01, 2208.90.03.91), because both countries split the same subheading in their
own way. The pair says only that both lines are inside 2208.90.

## How it is built

| Source | Where | Rights |
|---|---|---|
| HTSUS 2026 Revision 22, JSON and CSV exports | [USITC revision archive](https://www.usitc.gov/harmonized_tariff_information/hts/archive/list) | US Government work, 17 U.S.C. §105 |
| TIGIE subpartidas, fracciones and NICOs | [tigie-nico-mx](https://github.com/bajalabs/tigie-nico-mx) release v1.0.0, `tigie-nico-mx-csv.zip` | Mexican legal text, LFDA art. 14 fr. VIII |

`manifests/sources.json` pins every file with its URL and sha256; `fetch-us` and `fetch-mx` refuse a file whose hash
differs. The build then:

1. Checks the HTSUS JSON export against the CSV export of the same revision, row by row (code, indent, description,
   units, the three rates, quota, additional duties) after whitespace normalisation. Revision 22: 35,805 rows each,
   0 disagreements. Revision 19 gives 35,804 rows and 19,831 ten-digit goods lines, also with no disagreement. The
   build stops if the exports disagree.
2. Rebuilds the hierarchy from the indents: a row's parent is the nearest earlier row with a smaller indent. Where
   the indent jumps by two levels (27 rows, for example under 3821.00.00) no ancestor is invented. Uncoded grouping
   rows stay in `full_path` and `us_tree` and are never output as codes.
3. Reads the Mexican contract files. A NICO with a `baja` date is not current (`build --as-of YYYY-MM-DD` keeps
   NICOs that end after that day). Malformed rows are skipped and listed in `build-manifest.json`; this release has
   none.
4. Pairs every US line with every Mexican line of the same HS-6 subheading, and lists national lines on their own.
5. Writes the files, the SQLite database and `SHA256SUMS`. The same inputs give byte-identical outputs.

English HS-6 titles come from the HTSUS and Spanish titles from the TIGIE. No UN Comtrade data and no World Customs
Organization text is used.

## Limitations

- A match is at the HS-6 level only. National lines below it are not compared, and neither are duties, units,
  preferences under USMCA/T-MEC, trade remedies or non-tariff measures.
- The HTSUS changes every few weeks; this release is Revision 22. Chapter 99 temporary duties and the footnotes that
  point to them change most often. Check the [current HTSUS](https://hts.usitc.gov/) before relying on a rate.
- The HTSUS export does not include the general, section or chapter notes, so `us_hts.csv` has none. The units of the
  95 chapter-91 lines without a statistical suffix are set by that chapter's statistical notes, not by the row.
- Mexican rates are the TIGIE cells as compiled by tigie-nico-mx (`igi_vigente`, `ige_vigente`); its own
  documentation explains their dates and decrees.
- Both schedules follow the 2022 edition of the Harmonized System. The 2027 edition takes effect on 1 January 2027;
  subheadings will move and this crosswalk will be rebuilt.
- One subheading (8424.89) has no HTSUS row that covers it exactly; its English title is the first national line and
  is marked `first_line`.
- These files are not legal advice and not an official publication. The HTSUS as published by the USITC and the TIGIE
  as published in the Diario Oficial de la Federación prevail.

## Licence

Code: [MIT](LICENSE). Data: [CC0 1.0](LICENSE-DATA) for the compilation; the HTSUS and the TIGIE themselves carry no
copyright (17 U.S.C. §105; Ley Federal del Derecho de Autor, art. 14, fr. VIII).

## Citation

See [CITATION.cff](CITATION.cff), or cite: Baja Labs (2026). *hs-crosswalk-us-mx* (version 1.0.0).
https://github.com/bajalabs/hs-crosswalk-us-mx

## Contributing

Data error reports and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). Security reports: see
[SECURITY.md](SECURITY.md).
