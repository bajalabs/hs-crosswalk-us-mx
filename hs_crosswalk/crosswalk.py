"""Join US lines and Mexican lines on the shared 6-digit HS subheading.

A match means both lines sit in the same international subheading. It does not mean
the national lines cover the same goods or carry comparable duties.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .mx_tigie import MxTariff
from .us_hts import UsSchedule

MATCH_LEVELS = ("hs6", "us_only", "mx_only", "national")
CROSSWALK_COLUMNS = ("us_hts10", "mx_codigo10", "hs6", "match_level", "notes")
HS6_COLUMNS = (
    "hs6",
    "title_en",
    "title_es",
    "in_us",
    "in_mx",
    "us_lines",
    "mx_lines",
    "title_en_kind",
    "title_en_path",
)


@dataclass(frozen=True)
class CrosswalkRow:
    us_hts10: str
    mx_codigo10: str
    hs6: str
    match_level: str
    notes: str

    def as_tuple(self) -> tuple[str, ...]:
        return (self.us_hts10, self.mx_codigo10, self.hs6, self.match_level, self.notes)


def _note(*parts: str) -> str:
    return "; ".join(p for p in parts if p)


def _cardinality(n_us: int, n_mx: int) -> str:
    left = "1" if n_us == 1 else "n"
    right = "1" if n_mx == 1 else "n"
    return f"{left}:{right}"


def build(us: UsSchedule, mx: MxTariff) -> tuple[list[CrosswalkRow], list[dict], dict]:
    """Return crosswalk rows, HS-6 rows and coverage figures."""
    us_lines = us.leaves
    us_by6: dict[str, list] = {}
    for r in us_lines:
        if r.hs6:
            us_by6.setdefault(r.hs6, []).append(r)
    mx_by6: dict[str, list] = {}
    for line in mx.lines:
        if line.hs6:
            mx_by6.setdefault(line.hs6, []).append(line)

    us6 = us.hs6_codes()
    mx6 = mx.hs6_codes()
    titles = us.hs6_titles()
    universe = sorted(us6 | mx6)

    rows: list[CrosswalkRow] = []
    cardinality: Counter = Counter()
    for hs6 in universe:
        u = sorted(us_by6.get(hs6, []), key=lambda r: r.code)
        m = mx_by6.get(hs6, [])
        if u and m:
            card = _cardinality(len(u), len(m))
            cardinality[card] += 1
            shape = f"{card} at HS-6 (US {len(u)}, MX {len(m)})"
            for ur in u:
                for ml in m:
                    rows.append(
                        CrosswalkRow(
                            ur.code,
                            ml.code,
                            hs6,
                            "hs6",
                            _note(
                                shape,
                                "US line without statistical suffix" if ur.level == 8 else "",
                                "MX fraccion without NICO" if ml.kind == "fraccion" else "",
                                "MX import duty reads Prohibida" if ml.prohibited else "",
                            ),
                        )
                    )
        elif u:
            why = (
                "HS-6 not in the Mexican tariff files"
                if hs6 not in mx6
                else "HS-6 listed in Mexico but without a current national line"
            )
            for ur in u:
                rows.append(
                    CrosswalkRow(
                        ur.code,
                        "",
                        hs6,
                        "us_only",
                        _note(why, "US line without statistical suffix" if ur.level == 8 else ""),
                    )
                )
        elif m:
            why = (
                "HS-6 not in this HTSUS revision"
                if hs6 not in us6
                else "HS-6 present in the US without a goods line"
            )
            for ml in m:
                rows.append(
                    CrosswalkRow(
                        "",
                        ml.code,
                        hs6,
                        "mx_only",
                        _note(
                            why,
                            "MX fraccion without NICO" if ml.kind == "fraccion" else "",
                            "MX import duty reads Prohibida" if ml.prohibited else "",
                        ),
                    )
                )

    for r in sorted((r for r in us_lines if r.is_national), key=lambda r: r.code):
        rows.append(
            CrosswalkRow(
                r.code,
                "",
                "",
                "national",
                f"US chapter {r.chapter}: national provision, outside the HS",
            )
        )
    for line in (line for line in mx.lines if line.is_national):
        rows.append(
            CrosswalkRow(
                "",
                line.code,
                "",
                "national",
                f"MX chapter {line.chapter}: national provision, outside the HS",
            )
        )

    hs6_rows = []
    for hs6 in universe:
        t = titles.get(hs6)
        sub = mx.subpartidas.get(hs6)
        hs6_rows.append(
            {
                "hs6": hs6,
                "title_en": t.title if t else "",
                "title_es": sub["descripcion"] if sub else "",
                "in_us": 1 if hs6 in us6 else 0,
                "in_mx": 1 if hs6 in mx6 else 0,
                "us_lines": len(us_by6.get(hs6, [])),
                "mx_lines": len(mx_by6.get(hs6, [])),
                "title_en_kind": t.kind if t else "",
                "title_en_path": t.path if t else "",
            }
        )

    coverage = _coverage(us, mx, universe, us6, mx6, rows, cardinality, titles)
    return rows, hs6_rows, coverage


def _coverage(us, mx, universe, us6, mx6, rows, cardinality, titles) -> dict:
    both = sorted(us6 & mx6)
    us_only = sorted(us6 - mx6)
    mx_only = sorted(mx6 - us6)
    chapters: dict[str, Counter] = {}
    for hs6 in universe:
        c = chapters.setdefault(hs6[:2], Counter())
        c["hs6"] += 1
        c["both" if hs6 in us6 and hs6 in mx6 else "us_only" if hs6 in us6 else "mx_only"] += 1
    us_lines = Counter(r.chapter for r in us.leaves)
    mx_lines = Counter(line.chapter for line in mx.lines)
    by_chapter = []
    for ch in sorted(set(chapters) | set(us_lines) | set(mx_lines)):
        c = chapters.get(ch, Counter())
        by_chapter.append(
            {
                "chapter": ch,
                "hs6": c["hs6"],
                "both": c["both"],
                "us_only": c["us_only"],
                "mx_only": c["mx_only"],
                "us_lines": us_lines.get(ch, 0),
                "mx_lines": mx_lines.get(ch, 0),
            }
        )
    return {
        "hs6": {
            "total": len(universe),
            "both": len(both),
            "us_only": len(us_only),
            "mx_only": len(mx_only),
            "us_only_codes": us_only,
            "mx_only_codes": mx_only,
            "matched_shapes": {k: cardinality.get(k, 0) for k in ("1:1", "1:n", "n:1", "n:n")},
            "title_en_kinds": dict(sorted(Counter(t.kind for t in titles.values()).items())),
        },
        "crosswalk": {
            "rows": len(rows),
            "by_match_level": {k: sum(1 for r in rows if r.match_level == k) for k in MATCH_LEVELS},
            "us_lines": len(us.leaves),
            "mx_lines": len(mx.lines),
        },
        "by_chapter": by_chapter,
    }


def coverage_us_only(us: UsSchedule) -> dict:
    titles = us.hs6_titles()
    lines = Counter(r.chapter for r in us.leaves)
    return {
        "hs6": {
            "total": len(titles),
            "title_en_kinds": dict(sorted(Counter(t.kind for t in titles.values()).items())),
        },
        "by_chapter": [{"chapter": ch, "us_lines": n} for ch, n in sorted(lines.items())],
    }
