# Contributing

Thank you for helping. Corrections to the data are as welcome as code.

## Report a data error

Open a [data error report](https://github.com/bajalabs/hs-crosswalk-us-mx/issues/new?template=data_error.yml)
with the code, the release and a link to the official text. US lines are checked against the HTSUS revision named
in `coverage.json`; Mexican descriptions and duties come from
[tigie-nico-mx](https://github.com/bajalabs/tigie-nico-mx), so an error in them is fixed there first.

## Set up

Python 3.12 or newer and the standard library are all you need. From a clone:

```sh
python3 -m unittest                  # the tests, on the committed fixtures, no network
```

With [uv](https://docs.astral.sh/uv/) the same commands run as `uv run python -m unittest` and
`uv run python -m hs_crosswalk ...`.

## Build

```sh
python3 -m hs_crosswalk fetch-us     # pinned HTSUS JSON + CSV from usitc.gov, sha256-checked
python3 -m hs_crosswalk fetch-mx     # pinned tigie-nico-mx CSV zip, sha256-checked
python3 -m hs_crosswalk build        # writes dist/
```

Settings, all optional:

| Variable | Default | Used for |
|---|---|---|
| `HSX_CACHE_DIR` | `data/sources` | where `fetch-us` and `fetch-mx` put the source files |
| `TIGIE_CSV_DIR` | `$HSX_CACHE_DIR/tigie-nico-mx` | the folder with `subpartidas.csv`, `fracciones.csv`, `nicos.csv` (same as `build --mx-dir`) |
| `HSX_DIST_DIR` | `dist` | the output folder (same as `build --out`) |
| `HSX_MANIFEST` | `manifests/sources.json` | the source manifest |
| `TIGIE_RELEASE_URL` | `release_url` in the manifest | base URL of the tigie-nico-mx release assets |
| `USITC_RELEASE_LIST_URL` | `https://hts.usitc.gov/reststop/releaseList` | `latest-us` |
| `USITC_HTS_FILE_URL` | `https://www.usitc.gov/sites/default/files/tata/hts/hts_{year}_revision_{revision}_{kind}` | `pin-us` |
| `HSX_USER_AGENT` | Python's own (`Python-urllib/3.x`) | the User-Agent of downloads; the USITC file host refuses some unfamiliar agents |

The fixture build that CI runs, with no network:

```sh
python3 -m hs_crosswalk build \
  --us-json tests/fixtures/us/hts_fixture.json \
  --us-csv tests/fixtures/us/hts_fixture.csv \
  --mx-dir tests/fixtures/mx --out /tmp/hsx-dist
```

`tests/fixtures/us/` holds 118 real rows of HTSUS 2026 Revision 22 (headings 0101, 0802, 3407, 3821, 9101 and
parts of 9801 and 9903) in both export formats. `tests/fixtures/mx/` is a small synthetic set in the tigie-nico-mx
contract; its descriptions are illustrative and are not tariff data.

## Move to a new revision

USITC publishes a new HTSUS revision every few weeks.

```sh
python3 -m hs_crosswalk latest-us                       # exit code 3 when a newer revision exists
python3 -m hs_crosswalk pin-us --year 2026 --revision 23 --published 2026-MM-DD
python3 -m hs_crosswalk build
```

`pin-us` downloads both exports, refuses them if the JSON and CSV disagree, and writes the new names, URLs and
sha256 into `manifests/sources.json`. Take the publication date from the
[USITC revision archive](https://www.usitc.gov/harmonized_tariff_information/hts/archive/list).

For a new tigie-nico-mx release, download its `tigie-nico-mx-csv.zip` and run
`python3 -m hs_crosswalk pin-mx --zip path/to/tigie-nico-mx-csv.zip --release vX.Y.Z`.

Then update the counts in README.md, README.es.md and CHANGELOG.md from `dist/coverage.json`.

## Propose a change

1. Open an issue first for anything larger than a fix.
2. Keep to the standard library; no new dependencies without a reason in the pull request.
3. Add or change a test with every behaviour change; run `python3 -m unittest` and the fixture build.
4. Never commit `dist/` or `data/`: large outputs are release assets.
5. Fill in the pull request template.

## Release

1. `fetch-us`, `fetch-mx`, `build` from a clean clone; `cd dist && shasum -a 256 -c SHA256SUMS`.
2. Update CHANGELOG.md, the version in `pyproject.toml`, `hs_crosswalk/__init__.py` and `CITATION.cff`.
3. Tag `vX.Y.Z` and attach every file in `dist/`, `SHA256SUMS` included, to the GitHub release.
