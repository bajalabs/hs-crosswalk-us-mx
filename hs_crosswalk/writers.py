"""Write the release files: CSV, JSON, SQLite and SHA256SUMS."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from .crosswalk import CROSSWALK_COLUMNS, HS6_COLUMNS, CrosswalkRow
from .mx_tigie import MxTariff
from .sources import sha256_file
from .us_hts import UsSchedule

US_HTS_COLUMNS = (
    "code",
    "htsno",
    "level",
    "indent",
    "description",
    "full_path",
    "units",
    "general",
    "special",
    "column2",
    "quota_quantity",
    "additional_duties",
    "footnotes",
    "hs6",
    "chapter",
    "is_leaf",
    "rate_line",
    "source_row",
)
COVERAGE_COLUMNS = ("chapter", "hs6", "both", "us_only", "mx_only", "us_lines", "mx_lines")
SQLITE_NAME = "hs-crosswalk-us-mx.sqlite"

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE us_tree (
  source_row INTEGER PRIMARY KEY, htsno TEXT, code TEXT, indent INTEGER NOT NULL,
  description TEXT NOT NULL, parent_row INTEGER REFERENCES us_tree(source_row),
  kind TEXT NOT NULL CHECK (kind IN ('code', 'grouping'))
);
CREATE TABLE us_hts (
  code TEXT PRIMARY KEY, htsno TEXT NOT NULL, level INTEGER NOT NULL, indent INTEGER NOT NULL,
  description TEXT NOT NULL, full_path TEXT NOT NULL, units TEXT, general TEXT, special TEXT,
  column2 TEXT, quota_quantity TEXT, additional_duties TEXT, footnotes TEXT, hs6 TEXT,
  chapter TEXT NOT NULL, is_leaf INTEGER NOT NULL, rate_line TEXT,
  source_row INTEGER NOT NULL REFERENCES us_tree(source_row)
);
CREATE TABLE us_footnotes (
  code TEXT NOT NULL REFERENCES us_hts(code), ordinal INTEGER NOT NULL, marker TEXT,
  columns TEXT, kind TEXT, text TEXT NOT NULL, PRIMARY KEY (code, ordinal)
);
CREATE TABLE hs6 (
  hs6 TEXT PRIMARY KEY, title_en TEXT, title_es TEXT, in_us INTEGER NOT NULL,
  in_mx INTEGER NOT NULL, us_lines INTEGER NOT NULL, mx_lines INTEGER NOT NULL,
  title_en_kind TEXT, title_en_path TEXT
);
CREATE TABLE mx_subpartidas (
  subpartida TEXT PRIMARY KEY, partida TEXT, capitulo TEXT, descripcion TEXT
);
CREATE TABLE mx_fracciones (
  fraccion TEXT PRIMARY KEY, subpartida TEXT, descripcion TEXT, umt TEXT,
  igi_vigente TEXT, ige_vigente TEXT
);
CREATE TABLE mx_nicos (
  codigo TEXT PRIMARY KEY, fraccion TEXT, nico TEXT, descripcion TEXT, alta TEXT, baja TEXT,
  current INTEGER NOT NULL
);
CREATE TABLE crosswalk (
  us_hts10 TEXT, mx_codigo10 TEXT, hs6 TEXT, match_level TEXT NOT NULL, notes TEXT
);
CREATE TABLE coverage_by_chapter (
  chapter TEXT PRIMARY KEY, hs6 INTEGER, both INTEGER, us_only INTEGER, mx_only INTEGER,
  us_lines INTEGER, mx_lines INTEGER
);
"""

INDEXES_AND_VIEWS = """
CREATE INDEX us_hts_hs6 ON us_hts(hs6);
CREATE INDEX us_hts_htsno ON us_hts(htsno);
CREATE INDEX crosswalk_us ON crosswalk(us_hts10);
CREATE INDEX crosswalk_mx ON crosswalk(mx_codigo10);
CREATE INDEX crosswalk_hs6 ON crosswalk(hs6);
CREATE INDEX mx_fracciones_subpartida ON mx_fracciones(subpartida);
CREATE INDEX mx_nicos_fraccion ON mx_nicos(fraccion);
CREATE VIEW v_crosswalk AS
SELECT c.us_hts10, u.htsno AS us_htsno, u.description AS us_description,
       u.full_path AS us_full_path, r.general AS us_general_rate,
       c.mx_codigo10, COALESCE(n.descripcion, f.descripcion) AS mx_descripcion,
       COALESCE(nf.igi_vigente, f.igi_vigente) AS mx_igi,
       c.hs6, h.title_en AS hs6_title_en, h.title_es AS hs6_title_es,
       c.match_level, c.notes
FROM crosswalk c
LEFT JOIN us_hts u ON u.code = c.us_hts10
LEFT JOIN us_hts r ON r.htsno = u.rate_line
LEFT JOIN mx_nicos n ON n.codigo = c.mx_codigo10
LEFT JOIN mx_fracciones nf ON nf.fraccion = n.fraccion
LEFT JOIN mx_fracciones f ON f.fraccion = c.mx_codigo10
LEFT JOIN hs6 h ON h.hs6 = c.hs6;
"""


def _write_csv(path: Path, header: tuple[str, ...], rows) -> int:
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow(row)
            count += 1
    return count


def us_hts_records(us: UsSchedule):
    for r in us.rows:
        if not r.code:
            continue
        yield (
            r.code,
            r.htsno,
            r.level,
            r.indent,
            r.description,
            r.full_path,
            "; ".join(r.units),
            r.general,
            r.special,
            r.column2,
            r.quota_quantity,
            r.additional_duties,
            " | ".join(f.render() for f in r.footnotes),
            r.hs6,
            r.chapter,
            1 if r.is_leaf else 0,
            r.rate_line,
            r.source_row,
        )


def write_us_hts(out: Path, us: UsSchedule) -> int:
    return _write_csv(out / "us_hts.csv", US_HTS_COLUMNS, us_hts_records(us))


def write_hs6(out: Path, hs6_rows: list[dict]) -> int:
    return _write_csv(out / "hs6.csv", HS6_COLUMNS, ([r[c] for c in HS6_COLUMNS] for r in hs6_rows))


def write_crosswalk(out: Path, rows: list[CrosswalkRow]) -> int:
    return _write_csv(out / "crosswalk.csv", CROSSWALK_COLUMNS, (r.as_tuple() for r in rows))


def write_coverage(out: Path, coverage: dict) -> int:
    (out / "coverage.json").write_text(
        json.dumps(coverage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    by_chapter = coverage.get("by_chapter", [])
    return _write_csv(
        out / "coverage_by_chapter.csv",
        COVERAGE_COLUMNS,
        ([row.get(c, 0) for c in COVERAGE_COLUMNS] for row in by_chapter),
    )


def write_sqlite(
    out: Path,
    us: UsSchedule,
    mx: MxTariff | None,
    rows: list[CrosswalkRow],
    hs6_rows: list[dict],
    coverage: dict,
    meta: dict[str, str],
) -> Path:
    target = out / SQLITE_NAME
    tmp = out / (SQLITE_NAME + ".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    try:
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
        db.executemany(
            "INSERT INTO us_tree VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    r.source_row,
                    r.htsno or None,
                    r.code or None,
                    r.indent,
                    r.description,
                    us.rows[r.parent].source_row if r.parent is not None else None,
                    "code" if r.code else "grouping",
                )
                for r in us.rows
            ),
        )
        db.executemany(f"INSERT INTO us_hts VALUES ({','.join('?' * 18)})", us_hts_records(us))
        db.executemany(
            "INSERT INTO us_footnotes VALUES (?, ?, ?, ?, ?, ?)",
            (
                (r.code, i, f.marker or None, ", ".join(f.columns), f.kind, f.text)
                for r in us.rows
                if r.code
                for i, f in enumerate(r.footnotes, start=1)
            ),
        )
        db.executemany(
            f"INSERT INTO hs6 VALUES ({','.join('?' * len(HS6_COLUMNS))})",
            ([r[c] for c in HS6_COLUMNS] for r in hs6_rows),
        )
        if mx is not None:
            db.executemany(
                "INSERT INTO mx_subpartidas VALUES (?, ?, ?, ?)",
                (
                    (k, v["partida"], v["capitulo"], v["descripcion"])
                    for k, v in sorted(mx.subpartidas.items())
                ),
            )
            db.executemany(
                "INSERT INTO mx_fracciones VALUES (?, ?, ?, ?, ?, ?)",
                (
                    (k, v["subpartida"], v["descripcion"], v["umt"], v["igi_vigente"], v["ige_vigente"])
                    for k, v in sorted(mx.fracciones.items())
                ),
            )
            db.executemany(
                "INSERT INTO mx_nicos VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    (n["codigo"], n["fraccion"], n["nico"], n["descripcion"], n["alta"], n["baja"],
                     1 if n["current"] else 0)
                    for n in sorted(mx.nicos, key=lambda n: n["codigo"])
                ),
            )
        db.executemany("INSERT INTO crosswalk VALUES (?, ?, ?, ?, ?)", (r.as_tuple() for r in rows))
        db.executemany(
            "INSERT INTO coverage_by_chapter VALUES (?, ?, ?, ?, ?, ?, ?)",
            ([row.get(c, 0) for c in COVERAGE_COLUMNS] for row in coverage.get("by_chapter", [])),
        )
        db.executescript(INDEXES_AND_VIEWS)
        db.execute("PRAGMA user_version = 1")
        db.commit()
    finally:
        db.close()
    tmp.replace(target)
    return target


OUTPUT_NAMES = (
    "us_hts.csv",
    "hs6.csv",
    "crosswalk.csv",
    "coverage.json",
    "coverage_by_chapter.csv",
    SQLITE_NAME,
    "build-manifest.json",
)


def clear_outputs(out: Path) -> None:
    """Remove this builder's own files from ``out``; nothing else is touched."""
    for name in OUTPUT_NAMES + ("SHA256SUMS", SQLITE_NAME + ".tmp"):
        (out / name).unlink(missing_ok=True)


def write_sha256sums(out: Path) -> Path:
    files = sorted(out / n for n in OUTPUT_NAMES if (out / n).is_file())
    lines = [f"{sha256_file(p)}  {p.name}\n" for p in files]
    target = out / "SHA256SUMS"
    target.write_text("".join(lines), encoding="utf-8")
    return target


def describe_outputs(out: Path, row_counts: dict[str, int]) -> dict:
    result = {}
    for name in OUTPUT_NAMES:
        p = out / name
        if p.is_file() and name != "build-manifest.json":
            entry = {"bytes": p.stat().st_size, "sha256": sha256_file(p)}
            if p.name in row_counts:
                entry["rows"] = row_counts[p.name]
            result[p.name] = entry
    return result
