"""Small text helpers shared by both sides."""

from __future__ import annotations

import re

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
_WHITESPACE = re.compile(r"\s+")
_NON_DIGIT = re.compile(r"\D")


def clean(value: object) -> str:
    """Collapse whitespace runs, trim, and drop zero-width characters.

    Nothing else is changed: wording, punctuation and rate text stay as published.
    """
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", str(value).translate(_ZERO_WIDTH)).strip()


def digits(value: object) -> str:
    """Return only the digits of a code such as ``0101.21.00.10``."""
    if value is None:
        return ""
    return _NON_DIGIT.sub("", str(value))
