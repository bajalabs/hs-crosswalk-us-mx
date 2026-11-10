"""Parse the USITC export of the Harmonized Tariff Schedule of the United States.

The export is a flat list of rows. Each row has an ``indent``; a row's parent is the
nearest earlier row with a smaller indent. Rows without an HTS number are grouping
rows: they are kept as context (they appear in ``full_path``) and never become codes.
When the indent jumps by more than one level the jump is taken as published: no
ancestor is invented for the missing level.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .text import clean, digits

US_NATIONAL_CHAPTERS = frozenset({"98", "99"})
CODE_LEVELS = (4, 6, 8, 10)
PATH_SEPARATOR = " > "
CSV_HEADER = (
    "HTS Number",
    "Indent",
    "Description",
    "Unit of Quantity",
    "General Rate of Duty",
    "Special Rate of Duty",
    "Column 2 Rate of Duty",
    "Quota Quantity",
    "Additional Duties",
)
CHECK_FIELDS = (
    "htsno",
    "indent",
    "description",
    "units",
    "general",
    "special",
    "column2",
    "quota_quantity",
    "additional_duties",
)


class HtsFormatError(ValueError):
    """The export does not have the shape this builder expects."""


@dataclass(frozen=True)
class Footnote:
    marker: str
    columns: tuple[str, ...]
    kind: str
    text: str

    def render(self) -> str:
        head = f"({self.marker}) " if self.marker else ""
        cols = ", ".join(self.columns)
        return f"{head}[{cols}] {self.text}" if cols else f"{head}{self.text}"


@dataclass
class UsRow:
    source_row: int
    htsno: str
    code: str
    indent: int
    description: str
    units: tuple[str, ...]
    general: str
    special: str
    column2: str
    quota_quantity: str
    additional_duties: str
    footnotes: tuple[Footnote, ...]
    parent: int | None = None
    end: int = 0
    has_coded_descendant: bool = False
    full_path: str = ""
    rate_line: str = ""

    @property
    def level(self) -> int:
        return len(self.code)

    @property
    def chapter(self) -> str:
        return self.code[:2]

    @property
    def is_national(self) -> bool:
        return self.chapter in US_NATIONAL_CHAPTERS

    @property
    def hs6(self) -> str:
        if len(self.code) >= 6 and not self.is_national:
            return self.code[:6]
        return ""

    @property
    def is_leaf(self) -> bool:
        return bool(self.code) and not self.has_coded_descendant

    @property
    def has_rate(self) -> bool:
        return bool(self.general or self.special or self.column2)


@dataclass(frozen=True)
class Hs6Title:
    hs6: str
    title: str
    kind: str
    path: str
    source_row: int


class UsSchedule:
    """The parsed schedule: every source row, in source order, with its tree links."""

    def __init__(self, rows: list[UsRow]):
        self.rows = rows

    @property
    def coded(self) -> list[UsRow]:
        return [r for r in self.rows if r.code]

    @property
    def leaves(self) -> list[UsRow]:
        return [r for r in self.rows if r.is_leaf]

    def hs6_codes(self) -> set[str]:
        return {r.hs6 for r in self.rows if r.hs6}

    def indent_gaps(self) -> int:
        gaps = 0
        for r in self.rows:
            parent_indent = self.rows[r.parent].indent if r.parent is not None else -1
            if r.indent > parent_indent + 1:
                gaps += 1
        return gaps

    def hs6_titles(self) -> dict[str, Hs6Title]:
        """English HS-6 titles taken from the schedule's own rows.

        ``kind`` says which row the title comes from:
        ``subheading_row`` (a published 6-digit row), ``national_line`` (the only
        national line of the subheading), ``heading_row`` (a heading with a single
        subheading, ``xxxx00``), ``grouping_row`` (an uncoded row that covers exactly
        the subheading), ``first_line`` (no row covers the whole subheading; the
        first national line is used and is narrower than the subheading).
        """
        groups: dict[str, list[int]] = {}
        for i, r in enumerate(self.rows):
            if r.hs6:
                groups.setdefault(r.hs6, []).append(i)
        titles: dict[str, Hs6Title] = {}
        for hs6, idxs in groups.items():
            pick, kind = self._title_row(hs6, idxs)
            row = self.rows[pick]
            titles[hs6] = Hs6Title(hs6, row.description, kind, row.full_path, row.source_row)
        return titles

    def _title_row(self, hs6: str, idxs: list[int]) -> tuple[int, str]:
        rows = self.rows
        for i in idxs:
            if rows[i].level == 6:
                return i, "subheading_row"
        first = rows[idxs[0]]
        eights = {rows[i].code[:8] for i in idxs}
        tens = [i for i in idxs if rows[i].level == 10]
        if len(eights) == 1 and (first.level == 8 or len(tens) == 1):
            return idxs[0], "national_line"
        last = idxs[-1]
        cand = first.parent
        while cand is not None and rows[cand].end <= last:
            cand = rows[cand].parent
        if cand is not None:
            anc = rows[cand]
            inside = all(
                rows[k].code.startswith(hs6) for k in range(cand + 1, anc.end) if rows[k].code
            )
            if inside and not anc.code:
                return cand, "grouping_row"
            if inside and anc.code == hs6[:4] and hs6.endswith("00"):
                return cand, "heading_row"
        return idxs[0], "first_line"

    def stats(self) -> dict:
        coded = self.coded
        levels = Counter(r.level for r in coded)
        leaves = [r for r in coded if r.is_leaf]
        goods = [r for r in leaves if not r.is_national]
        goods_levels = Counter(r.level for r in goods)
        return {
            "rows": len(self.rows),
            "grouping_rows": len(self.rows) - len(coded),
            "coded_rows": len(coded),
            "coded_rows_by_level": {str(k): levels.get(k, 0) for k in CODE_LEVELS},
            "leaves": len(leaves),
            "goods_leaves": len(goods),
            "goods_leaves_by_level": {str(k): goods_levels.get(k, 0) for k in CODE_LEVELS},
            "national_leaves": len(leaves) - len(goods),
            "chapters": len({r.chapter for r in coded}),
            "hs6": len(self.hs6_codes()),
            "indent_gaps": self.indent_gaps(),
        }


def load_json(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise HtsFormatError(f"{Path(path).name}: expected a JSON array of rows")
    return data


def _footnotes(value: object) -> tuple[Footnote, ...]:
    out = []
    for f in value or []:
        if not isinstance(f, dict):
            continue
        text = clean(f.get("value"))
        if not text:
            continue
        out.append(
            Footnote(
                marker=clean(f.get("marker")),
                columns=tuple(clean(c) for c in (f.get("columns") or []) if clean(c)),
                kind=clean(f.get("type")),
                text=text,
            )
        )
    return tuple(out)


def _indent(value: object, pos: int) -> int:
    try:
        indent = int(str(value).strip())
    except (TypeError, ValueError):
        raise HtsFormatError(f"row {pos}: indent {value!r} is not an integer") from None
    if indent < 0:
        raise HtsFormatError(f"row {pos}: negative indent {indent}")
    return indent


def _additional(rec: dict) -> str:
    # The export carries the column twice; one spelling has three i's.
    return clean(rec.get("additionalDuties")) or clean(rec.get("addiitionalDuties"))


def parse_records(records: list[dict]) -> UsSchedule:
    rows: list[UsRow] = []
    stack: list[int] = []
    for pos, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise HtsFormatError(f"row {pos + 1}: expected an object")
        htsno = clean(rec.get("htsno"))
        code = digits(htsno)
        if code and len(code) not in CODE_LEVELS:
            raise HtsFormatError(f"row {pos + 1}: HTS number {htsno!r} has {len(code)} digits")
        row = UsRow(
            source_row=pos + 1,
            htsno=htsno,
            code=code,
            indent=_indent(rec.get("indent"), pos + 1),
            description=clean(rec.get("description")),
            units=tuple(clean(u) for u in (rec.get("units") or []) if clean(u)),
            general=clean(rec.get("general")),
            special=clean(rec.get("special")),
            column2=clean(rec.get("other")),
            quota_quantity=clean(rec.get("quotaQuantity")),
            additional_duties=_additional(rec),
            footnotes=_footnotes(rec.get("footnotes")),
        )
        while stack and rows[stack[-1]].indent >= row.indent:
            rows[stack.pop()].end = pos
        row.parent = stack[-1] if stack else None
        if row.parent is None:
            row.full_path = row.description
        else:
            row.full_path = rows[row.parent].full_path + PATH_SEPARATOR + row.description
        rows.append(row)
        stack.append(pos)
    for i in stack:
        rows[i].end = len(rows)

    for row in rows:
        if not row.code:
            continue
        p = row.parent
        while p is not None and not rows[p].has_coded_descendant:
            rows[p].has_coded_descendant = True
            p = rows[p].parent

    # Rates are published on the 8-digit legal line (or on a 10-digit line whose
    # 8-digit line is not printed). Statistical lines point at the line that carries them.
    for row in rows:
        if not row.code:
            continue
        if row.has_rate:
            row.rate_line = row.htsno
            continue
        p = row.parent
        while p is not None and not rows[p].code:
            p = rows[p].parent
        if p is not None and row.code.startswith(rows[p].code):
            row.rate_line = rows[p].rate_line
    return UsSchedule(rows)


def load_schedule(path: str | Path) -> UsSchedule:
    return parse_records(load_json(path))


def _units_text(units: object) -> str:
    return "; ".join(clean(u) for u in (units or []) if clean(u))


def _csv_indent(value: str) -> str:
    # The CSV sometimes zero-pads the indent ("03"); compare it as a number.
    text = clean(value)
    return str(int(text)) if text.isdigit() else text


def _csv_units(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return clean(value)
    if isinstance(parsed, list):
        return _units_text(parsed)
    return clean(parsed)


def compare_with_csv(records: list[dict], csv_path: str | Path) -> dict:
    """Check the JSON export against the CSV export of the same revision.

    Values are compared after whitespace normalisation only. Returns counts and the
    first disagreements; ``mismatches == 0`` means the two exports agree.
    """
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None or tuple(clean(h) for h in header[: len(CSV_HEADER)]) != CSV_HEADER:
            raise HtsFormatError(f"{Path(csv_path).name}: unexpected header {header!r}")
        csv_rows = list(reader)
    problems: list[dict] = []
    if len(csv_rows) != len(records):
        problems.append({"row": None, "field": "row_count", "json": len(records), "csv": len(csv_rows)})
    for pos, (rec, row) in enumerate(zip(records, csv_rows), start=1):
        row = list(row) + [""] * (len(CSV_HEADER) - len(row))
        json_view = (
            clean(rec.get("htsno")),
            str(_indent(rec.get("indent"), pos)),
            clean(rec.get("description")),
            _units_text(rec.get("units")),
            clean(rec.get("general")),
            clean(rec.get("special")),
            clean(rec.get("other")),
            clean(rec.get("quotaQuantity")),
            _additional(rec),
        )
        csv_view = (
            clean(row[0]),
            _csv_indent(row[1]),
            clean(row[2]),
            _csv_units(row[3]),
            clean(row[4]),
            clean(row[5]),
            clean(row[6]),
            clean(row[7]),
            clean(row[8]),
        )
        for name, a, b in zip(CHECK_FIELDS, json_view, csv_view):
            if a != b:
                problems.append({"row": pos, "field": name, "json": a, "csv": b})
    return {
        "json_rows": len(records),
        "csv_rows": len(csv_rows),
        "mismatches": len(problems),
        "examples": problems[:20],
    }
