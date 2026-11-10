"""Command line: ``python3 -m hs_crosswalk <command>``."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import DATASET, __version__
from . import crosswalk as xw
from . import sources, writers
from .mx_tigie import MX_FILES, TigieFormatError, load_tigie
from .us_hts import HtsFormatError, compare_with_csv, load_json, parse_records

DEFAULT_DIST = "dist"
DEFAULT_RELEASE_LIST = "https://hts.usitc.gov/reststop/releaseList"
DEFAULT_FILE_URL = "https://www.usitc.gov/sites/default/files/tata/hts/hts_{year}_revision_{revision}_{kind}"
FILE_SUFFIX = {"json": "json.json", "csv": "csv.csv"}


def _say(msg: str) -> None:
    print(msg, file=sys.stderr)


def _mx_dir(arg: str | None) -> Path:
    return Path(arg or os.environ.get("TIGIE_CSV_DIR") or sources.cache_dir() / sources.MX_SUBDIR)


def cmd_fetch_us(args: argparse.Namespace) -> int:
    manifest = sources.load_manifest()
    cache = sources.cache_dir()
    for role, f in sources.us_files(manifest).items():
        digest, size = sources.download(f["url"], cache / f["name"], f["sha256"])
        print(f"{role}: {cache / f['name']} {size} bytes sha256 {digest} (verified)")
    return 0


def cmd_fetch_mx(args: argparse.Namespace) -> int:
    manifest = sources.load_manifest()
    mx = manifest["mx_tigie"]
    asset = mx["asset"]
    files = sources.mx_files(manifest)
    if not asset.get("sha256") or not all(f.get("sha256") for f in files.values()):
        _say("The tigie-nico-mx release is not pinned in the manifest; pin it with `pin-mx`.")
        return 2
    url = f"{sources.mx_base_url(manifest)}/{asset['name']}"
    archive = sources.cache_dir() / asset["name"]
    digest, size = sources.download(url, archive, asset["sha256"])
    print(f"asset: {archive} {size} bytes sha256 {digest} (verified)")
    target = _mx_dir(args.dest)
    try:
        written = sources.extract_members(
            archive, {f["member"]: f["name"] for f in files.values()}, target
        )
    except zipfile.BadZipFile as exc:
        raise sources.SourceError(f"{archive.name}: {exc}") from exc
    bad = [f for f in files.values() if written[f["name"]] != f["sha256"]]
    if bad:
        for f in files.values():
            (target / f["name"]).unlink(missing_ok=True)
        raise sources.SourceError(f"sha256 mismatch for {bad[0]['member']} in {asset['name']}")
    for role, f in files.items():
        print(f"{role}: {target / f['name']} sha256 {f['sha256']} (verified)")
    return 0


def _release_list() -> list[dict]:
    url = os.environ.get("USITC_RELEASE_LIST_URL") or DEFAULT_RELEASE_LIST
    req = urllib.request.Request(url, headers={"User-Agent": sources.user_agent()})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def cmd_latest_us(args: argparse.Namespace) -> int:
    manifest = sources.load_manifest()
    current = [r for r in _release_list() if r.get("status") == "current"]
    if not current:
        _say("No release is marked current in the USITC release list.")
        return 1
    r = current[0]
    pinned = manifest["us_hts"]["release"]
    print(f"current: {r.get('name')} ({r.get('description')}), in effect from {r.get('releaseStartDate')}")
    print(f"pinned:  {pinned}")
    if r.get("name") == pinned:
        print("The manifest pins the current revision.")
        return 0
    print("A newer revision is published; see CONTRIBUTING.md to re-pin.")
    return 3


def cmd_pin_us(args: argparse.Namespace) -> int:
    manifest = sources.load_manifest()
    template = os.environ.get("USITC_HTS_FILE_URL") or DEFAULT_FILE_URL
    cache = sources.cache_dir()
    files = {}
    for role, suffix in FILE_SUFFIX.items():
        url = template.format(year=args.year, revision=args.revision, kind=suffix)
        name = url.rsplit("/", 1)[-1]
        digest, size = sources.download(url, cache / name, None)
        files[role] = {"name": name, "url": url, "sha256": digest, "bytes": size}
        print(f"{role}: {name} {size} bytes sha256 {digest}")
    records = load_json(cache / files["json"]["name"])
    check = compare_with_csv(records, cache / files["csv"]["name"])
    print(f"json/csv check: {check['json_rows']} / {check['csv_rows']} rows, {check['mismatches']} mismatches")
    if check["mismatches"]:
        _say("The JSON and CSV exports disagree; the manifest was not changed.")
        return 1
    us = manifest["us_hts"]
    us.update(
        {
            "release": f"{args.year}HTSRev{args.revision}",
            "title": f"Harmonized Tariff Schedule of the United States ({args.year}) Revision {args.revision}",
            "published": args.published,
            "retrieved": dt.date.today().isoformat(),
            "rows": check["json_rows"],
            "files": files,
        }
    )
    sources.save_manifest(manifest)
    print(f"Pinned {us['release']} in {sources.manifest_path()}")
    return 0


def cmd_pin_mx(args: argparse.Namespace) -> int:
    manifest = sources.load_manifest()
    mx = manifest["mx_tigie"]
    archive = Path(args.zip)
    members = {f"{args.member_dir}/{name}": name for name, _cols in MX_FILES.values()}
    with tempfile.TemporaryDirectory() as tmp:
        try:
            digests = sources.extract_members(archive, members, Path(tmp))
        except zipfile.BadZipFile as exc:
            raise sources.SourceError(f"{archive.name}: {exc}") from exc
        tariff = load_tigie(tmp)
        sizes = {name: (Path(tmp) / name).stat().st_size for name in digests}
    mx["asset"] = {
        "name": archive.name,
        "sha256": sources.sha256_file(archive),
        "bytes": archive.stat().st_size,
    }
    for role, (name, _cols) in MX_FILES.items():
        mx["files"][role] = {
            "name": name,
            "member": f"{args.member_dir}/{name}",
            "sha256": digests[name],
            "bytes": sizes[name],
            "rows": tariff.row_counts[name],
        }
    mx["release"] = args.release
    mx["release_url"] = args.release_url or mx["release_url"].rsplit("/", 1)[0] + f"/{args.release}"
    mx["retrieved"] = dt.date.today().isoformat()
    sources.save_manifest(manifest)
    print(f"Pinned tigie-nico-mx {args.release} ({archive.name}) in {sources.manifest_path()}")
    return 0


def _us_source_info(manifest: dict, json_path: Path, csv_path: Path | None) -> dict:
    us = manifest["us_hts"]
    files = sources.us_files(manifest)
    json_sha = sources.sha256_file(json_path)
    info = {
        "json": {"name": json_path.name, "sha256": json_sha, "bytes": json_path.stat().st_size},
        "pinned": json_sha == files["json"]["sha256"],
    }
    if csv_path is not None:
        info["csv"] = {
            "name": csv_path.name,
            "sha256": sources.sha256_file(csv_path),
            "bytes": csv_path.stat().st_size,
        }
    if info["pinned"]:
        info.update(
            {
                "release": us["release"],
                "title": us["title"],
                "published": us["published"],
                "json_url": files["json"]["url"],
                "csv_url": files["csv"]["url"],
            }
        )
    return info


def _mx_source_info(manifest: dict, directory: Path, tariff) -> dict:
    files = sources.mx_files(manifest)
    out = {"files": {}, "pinned": True}
    for role, (name, _cols) in MX_FILES.items():
        digest = sources.sha256_file(directory / name)
        out["files"][name] = {"sha256": digest, "rows": tariff.row_counts[name]}
        if files.get(role, {}).get("sha256") != digest:
            out["pinned"] = False
    if out["pinned"]:
        out["release"] = manifest["mx_tigie"]["release"]
        out["repository"] = manifest["mx_tigie"]["repository"]
    return out


def cmd_build(args: argparse.Namespace) -> int:
    manifest = sources.load_manifest()
    cache = sources.cache_dir()
    us_files = sources.us_files(manifest)
    json_path = Path(args.us_json) if args.us_json else cache / us_files["json"]["name"]
    csv_path = None
    if not args.no_csv_check:
        csv_path = Path(args.us_csv) if args.us_csv else cache / us_files["csv"]["name"]
    for p in (json_path, csv_path):
        if p is not None and not p.is_file():
            _say(f"Missing {p}. Run `python3 -m hs_crosswalk fetch-us` or pass --us-json/--us-csv.")
            return 2
    mx_dir = _mx_dir(args.mx_dir)
    if not args.us_only and not mx_dir.is_dir():
        _say(
            f"Missing the Mexican tariff files in {mx_dir}. Run `python3 -m hs_crosswalk fetch-mx`, "
            "set TIGIE_CSV_DIR, or pass --mx-dir."
        )
        return 2
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else None
    out = Path(args.out or os.environ.get("HSX_DIST_DIR") or DEFAULT_DIST)
    out.mkdir(parents=True, exist_ok=True)
    writers.clear_outputs(out)

    records = load_json(json_path)
    check = None
    if csv_path is not None:
        check = compare_with_csv(records, csv_path)
        _say(
            f"US json/csv check: {check['json_rows']} / {check['csv_rows']} rows, "
            f"{check['mismatches']} mismatches"
        )
        if check["mismatches"]:
            for ex in check["examples"][:5]:
                _say(f"  row {ex['row']} {ex['field']}: json={ex['json']!r} csv={ex['csv']!r}")
            _say("The JSON and CSV exports disagree; nothing was built.")
            return 1
    us = parse_records(records)
    us_info = _us_source_info(manifest, json_path, csv_path)
    if check is not None:
        us_info["json_csv_check"] = {k: check[k] for k in ("json_rows", "csv_rows", "mismatches")}
    if not us_info["pinned"]:
        _say("Note: the US JSON is not the revision pinned in the manifest.")

    counts: dict[str, int] = {}
    counts["us_hts.csv"] = writers.write_us_hts(out, us)
    mx = None
    if args.us_only:
        rows, hs6_rows = [], []
        coverage = xw.coverage_us_only(us)
        mx_info = None
    else:
        mx = load_tigie(mx_dir, as_of)
        for issue in mx.issues[:10]:
            _say(f"MX issue: {issue}")
        if len(mx.issues) > 10:
            _say(f"MX issues: {len(mx.issues)} in all (see build-manifest.json)")
        rows, hs6_rows, coverage = xw.build(us, mx)
        mx_info = _mx_source_info(manifest, mx_dir, mx)
        counts["hs6.csv"] = writers.write_hs6(out, hs6_rows)
        counts["crosswalk.csv"] = writers.write_crosswalk(out, rows)

    coverage = {
        "dataset": DATASET,
        "version": __version__,
        "us_release": us_info.get("release", "unpinned"),
        "mx_release": (mx_info or {}).get("release", "unpinned" if mx_info else None),
        "us": us.stats(),
        "mx": mx.stats() if mx else None,
        **coverage,
    }
    counts["coverage_by_chapter.csv"] = writers.write_coverage(out, coverage)

    meta = {
        "dataset": DATASET,
        "version": __version__,
        "mode": "us-only" if args.us_only else "full",
        "us_release": us_info.get("release", "unpinned"),
        "us_published": us_info.get("published", ""),
        "us_json_sha256": us_info["json"]["sha256"],
        "mx_release": (mx_info or {}).get("release", ""),
        "as_of": args.as_of or "",
    }
    if mx_info:
        for name, f in mx_info["files"].items():
            meta[f"mx_{name}_sha256"] = f["sha256"]
    writers.write_sqlite(out, us, mx, rows, hs6_rows, coverage, meta)

    build_manifest = {
        "dataset": DATASET,
        "version": __version__,
        "builder": f"hs_crosswalk {__version__}",
        "mode": meta["mode"],
        "options": {"as_of": args.as_of},
        "sources": {"us_hts": us_info, "mx_tigie": mx_info},
        "us": us.stats(),
        "mx": mx.stats() if mx else None,
        "mx_issues": mx.issues[:200] if mx else [],
        "outputs": writers.describe_outputs(out, counts),
    }
    (out / "build-manifest.json").write_text(
        json.dumps(build_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    writers.write_sha256sums(out)

    s = coverage["us"]
    print(
        f"US {coverage['us_release']}: {s['rows']} rows, {s['coded_rows']} coded, "
        f"{s['goods_leaves']} goods lines, {s['national_leaves']} national lines, {s['hs6']} HS-6"
    )
    if mx:
        h = coverage["hs6"]
        m = coverage["mx"]
        print(
            f"MX: {m['subpartidas']} subpartidas, {m['fracciones']} fracciones, "
            f"{m['nicos_current']} current NICOs"
        )
        print(
            f"HS-6: {h['total']} in all, {h['both']} in both, {h['us_only']} US only, "
            f"{h['mx_only']} MX only; crosswalk {coverage['crosswalk']['rows']} rows"
        )
    print(f"Wrote {out}/ (see SHA256SUMS)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m hs_crosswalk",
        description="US HTSUS as open files, joined with Mexico's TIGIE at HS-6.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("fetch-us", help="download the pinned HTSUS revision and verify sha256")
    s.set_defaults(func=cmd_fetch_us)

    s = sub.add_parser("fetch-mx", help="download the pinned tigie-nico-mx release and verify sha256")
    s.add_argument("--dest", help="target directory (default: TIGIE_CSV_DIR or the cache)")
    s.set_defaults(func=cmd_fetch_mx)

    s = sub.add_parser("build", help="build dist/ from the sources")
    s.add_argument("--us-json", help="HTSUS JSON export (default: the pinned file in the cache)")
    s.add_argument("--us-csv", help="HTSUS CSV export used for the cross-check")
    s.add_argument("--no-csv-check", action="store_true", help="skip the JSON/CSV agreement check")
    s.add_argument("--mx-dir", help="directory with subpartidas.csv, fracciones.csv, nicos.csv")
    s.add_argument("--us-only", action="store_true", help="build the US files only")
    s.add_argument("--as-of", help="YYYY-MM-DD: keep NICOs whose baja date falls after this day")
    s.add_argument("--out", help="output directory (default: HSX_DIST_DIR or dist)")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("latest-us", help="compare the pinned revision with the current USITC release")
    s.set_defaults(func=cmd_latest_us)

    s = sub.add_parser("pin-us", help="download a revision and pin it in the manifest")
    s.add_argument("--year", required=True, type=int)
    s.add_argument("--revision", required=True, type=int)
    s.add_argument("--published", required=True, help="YYYY-MM-DD, as listed in the USITC archive")
    s.set_defaults(func=cmd_pin_us)

    s = sub.add_parser("pin-mx", help="pin a tigie-nico-mx release asset (the CSV zip)")
    s.add_argument("--zip", required=True, help="path to tigie-nico-mx-csv.zip")
    s.add_argument("--release", required=True, help="tigie-nico-mx release tag, e.g. v1.0.0")
    s.add_argument("--release-url", help="base URL of the release assets")
    s.add_argument("--member-dir", default="csv", help="folder of the CSV files inside the zip")
    s.set_defaults(func=cmd_pin_mx)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (sources.SourceError, HtsFormatError, TigieFormatError, OSError, ValueError) as exc:
        _say(f"error: {exc}")
        return 1
