"""Read Mexico's tariff (TIGIE) from the CSV files published by ``tigie-nico-mx``.

The contract is three UTF-8 CSV files with a header row. Only the named columns are
read; extra trailing columns are ignored.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from .text import clean, digits

MX_NATIONAL_CHAPTERS = frozenset({"98"})
MX_FILES = {
    "subpartidas": ("subpartidas.csv", ("subpartida", "partida", "capitulo", "descripcion")),
    "fracciones": (
        "fracciones.csv",
        ("fraccion", "subpartida", "descripcion", "umt", "igi_vigente", "ige_vigente"),
    ),
    "nicos": ("nicos.csv", ("fraccion", "nico", "codigo", "descripcion", "alta", "baja")),
}


class TigieFormatError(ValueError):
    """A file is missing or lacks a contract column."""


@dataclass
class MxLine:
    """One Mexican national line: a NICO (10 digits) or, failing that, a fraccion (8)."""

    code: str
    fraccion: str
    descripcion: str
    kind: str  # "nico" or "fraccion"
    prohibited: bool = False  # the fraccion's import duty cell reads "Prohibida"

    @property
    def chapter(self) -> str:
        return self.code[:2]

    @property
    def is_national(self) -> bool:
        return self.chapter in MX_NATIONAL_CHAPTERS

    @property
    def hs6(self) -> str:
        return "" if self.is_national else self.code[:6]


@dataclass
class MxTariff:
    subpartidas: dict[str, dict] = field(default_factory=dict)
    fracciones: dict[str, dict] = field(default_factory=dict)
    nicos: list[dict] = field(default_factory=list)
    lines: list[MxLine] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)

    def hs6_codes(self) -> set[str]:
        codes = {s for s in self.subpartidas if s[:2] not in MX_NATIONAL_CHAPTERS}
        codes |= {line.hs6 for line in self.lines if line.hs6}
        return codes

    def stats(self) -> dict:
        current = [n for n in self.nicos if n["current"]]
        return {
            "subpartidas": len(self.subpartidas),
            "fracciones": len(self.fracciones),
            "nicos": len(self.nicos),
            "nicos_current": len(current),
            "nicos_removed": len(self.nicos) - len(current),
            "lines": len(self.lines),
            "lines_national": sum(1 for line in self.lines if line.is_national),
            "fracciones_without_nico": sum(1 for line in self.lines if line.kind == "fraccion"),
            "chapters": len({line.chapter for line in self.lines}),
            "hs6": len(self.hs6_codes()),
            "issues": len(self.issues),
        }


def _parse_date(value: str) -> dt.date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _read(path: Path, required: tuple[str, ...]) -> list[dict]:
    if not path.is_file():
        raise TigieFormatError(f"missing file: {path.name}")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = [clean(h) for h in (reader.fieldnames or [])]
        missing = [c for c in required if c not in header]
        if missing:
            raise TigieFormatError(f"{path.name}: missing column(s) {', '.join(missing)}")
        reader.fieldnames = header
        return [{c: clean(row.get(c)) for c in required} for row in reader]


def load_tigie(directory: str | Path, as_of: dt.date | None = None) -> MxTariff:
    """Load the three contract files from ``directory``.

    A NICO with a ``baja`` date is not current. With ``as_of``, a NICO whose ``baja``
    falls after that date is still current. Rows with malformed codes are skipped and
    recorded in ``issues``.
    """
    directory = Path(directory)
    tariff = MxTariff()
    raw = {key: _read(directory / name, cols) for key, (name, cols) in MX_FILES.items()}
    tariff.row_counts = {MX_FILES[k][0]: len(v) for k, v in raw.items()}

    for row in raw["subpartidas"]:
        code = digits(row["subpartida"])
        if len(code) != 6 or code != row["subpartida"]:
            tariff.issues.append(f"subpartidas.csv: bad subpartida {row['subpartida']!r}")
            continue
        if code in tariff.subpartidas:
            tariff.issues.append(f"subpartidas.csv: duplicate subpartida {code}")
            continue
        tariff.subpartidas[code] = row

    for row in raw["fracciones"]:
        code = row["fraccion"]
        if len(code) != 8 or digits(code) != code:
            tariff.issues.append(f"fracciones.csv: bad fraccion {code!r}")
            continue
        if row["subpartida"] != code[:6]:
            tariff.issues.append(
                f"fracciones.csv: fraccion {code} names subpartida {row['subpartida']!r}"
            )
        if code in tariff.fracciones:
            tariff.issues.append(f"fracciones.csv: duplicate fraccion {code}")
            continue
        tariff.fracciones[code] = row

    seen: set[str] = set()
    for row in raw["nicos"]:
        code, fraccion, nico = row["codigo"], row["fraccion"], row["nico"]
        if len(code) != 10 or digits(code) != code or code != fraccion + nico:
            tariff.issues.append(
                f"nicos.csv: codigo {code!r} is not fraccion {fraccion!r} + nico {nico!r}"
            )
            continue
        if code in seen:
            tariff.issues.append(f"nicos.csv: duplicate codigo {code}")
            continue
        seen.add(code)
        if fraccion not in tariff.fracciones:
            tariff.issues.append(f"nicos.csv: codigo {code} has no row in fracciones.csv")
        current = True
        if row["baja"]:
            baja = _parse_date(row["baja"])
            if baja is None:
                tariff.issues.append(f"nicos.csv: codigo {code} has unreadable baja {row['baja']!r}")
                current = False
            else:
                current = as_of is not None and baja > as_of
        tariff.nicos.append({**row, "current": current})

    by_fraccion: dict[str, list[dict]] = {}
    for n in tariff.nicos:
        by_fraccion.setdefault(n["fraccion"], []).append(n)
    def prohibited(fraccion: str) -> bool:
        row = tariff.fracciones.get(fraccion)
        return bool(row) and row["igi_vigente"].casefold() == "prohibida"

    for n in tariff.nicos:
        if n["current"]:
            tariff.lines.append(
                MxLine(n["codigo"], n["fraccion"], n["descripcion"], "nico", prohibited(n["fraccion"]))
            )
    for code, row in tariff.fracciones.items():
        if code not in by_fraccion:
            tariff.lines.append(MxLine(code, code, row["descripcion"], "fraccion", prohibited(code)))
        elif not any(n["current"] for n in by_fraccion[code]):
            tariff.issues.append(f"fracciones.csv: fraccion {code} has only removed NICOs")
    tariff.lines.sort(key=lambda line: line.code)
    return tariff
