"""Parse context notes into route, date, effect, and magnitude fields."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .config import Config, DEFAULT_CONFIG
from .loader import monday_of

ALL_ROUTES = "all routes"

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9

# Order matters: "no effect" wording is checked first, so ambiguity is non-justifying.
_NEUTRAL = [r"not\s+(?:significantly\s+)?affected", r"no\s+(?:significant|major)\s+disruptions?",
            r"remained\s+(?:stable|normal)", r"returned\s+to\s+normal", r"not\s+part\s+of\s+this\s+dataset",
            r"without\s+a\s+rate\s+change", r"absorbed", r"no\s+(?:impact|change)"]
_LOWERS = [r"\bimproved\b", r"\breduc\w*", r"\blower(?:ed|s)?\b", r"\bdecreas\w*", r"\bcheaper\b", r"\beased?\b"]
_RAISES = [r"\bsurcharges?\b", r"\bhigher\b", r"\bpush(?:ing|ed)?\s+up\b", r"\brose\b", r"\brise[sn]?\b",
           r"\bincreas\w*", r"\bhikes?\b", r"\braised\b"]

_RANGE_RE = re.compile(
    r"(?:from\s+)?\b([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*(?:to|through|until|-|\u2013)\s*(?:([A-Za-z]{3,9})\.?\s+)?(\d{1,2})\b",
    re.IGNORECASE)
_PERSISTENT_RE = re.compile(r"\bstarting\s+(?:this|from)\b|\bfrom\s+this\s+week\b|\bwith\s+effect\s+from\b", re.IGNORECASE)
_MAGNITUDE_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|\u2013|to)\s*(\d+(?:\.\d+)?)\s*%")
_MAGNITUDE_SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@dataclass(frozen=True)
class NoteCard:
    note_id: str
    date: pd.Timestamp
    applies_to: str
    text: str
    scope_all: bool
    scope_routes: tuple
    effect: str                      # "raises" | "lowers" | "none" | "unclear"
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    window_source: str               # how the window was derived (for transparency)
    magnitude: Optional[tuple]       # (low_pct, high_pct) or None

    def applies_to_route(self, route: str) -> bool:
        return self.scope_all or route.strip().casefold() in self.scope_routes


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def classify_effect(text: str) -> str:
    if _matches_any(_NEUTRAL, text):
        return "none"
    if _matches_any(_LOWERS, text):
        return "lowers"
    if _matches_any(_RAISES, text):
        return "raises"
    return "unclear"


def parse_magnitude(text: str) -> Optional[tuple]:
    m = _MAGNITUDE_RANGE_RE.search(text)
    if m:
        lo, hi = sorted((float(m.group(1)), float(m.group(2))))
        return lo, hi
    m = _MAGNITUDE_SINGLE_RE.search(text)
    if m:
        v = float(m.group(1))
        return v, v
    return None


def _explicit_range(text: str, note_date: pd.Timestamp):
    for m in _RANGE_RE.finditer(text):
        mon1, day1, mon2, day2 = m.groups()
        n1 = _MONTHS.get(mon1.lower())
        n2 = _MONTHS.get((mon2 or mon1).lower())
        if n1 is None or n2 is None:
            continue
        try:
            start = pd.Timestamp(year=note_date.year, month=n1, day=int(day1))
            end = pd.Timestamp(year=note_date.year + (1 if n2 < n1 else 0), month=n2, day=int(day2))
        except ValueError:
            continue
        if end >= start:
            return start, end
    return None


def derive_window(text: str, note_date: pd.Timestamp, cfg: Config = DEFAULT_CONFIG):
    """Return (start, end, source). Priority: explicit dates > step-change > the note's own week."""
    rng = _explicit_range(text, note_date)
    if rng:
        return rng[0], rng[1], "explicit date range in note text"
    week_start = monday_of(note_date)
    if _PERSISTENT_RE.search(text):
        end = week_start + pd.Timedelta(weeks=cfg.persistent_note_weeks) - pd.Timedelta(days=1)
        return week_start, end, f"step change: note week + {cfg.persistent_note_weeks} weeks"
    return week_start, week_start + pd.Timedelta(days=6), "note's own Monday-Sunday week"


def build_card(note_id: str, date: pd.Timestamp, applies_to: str, text: str,
               cfg: Config = DEFAULT_CONFIG) -> NoteCard:
    scope_all = applies_to.strip().casefold() == ALL_ROUTES
    routes = () if scope_all else tuple(r.strip().casefold() for r in re.split(r"[;,]", applies_to) if r.strip())
    start, end, source = derive_window(text, pd.Timestamp(date), cfg)
    effect = classify_effect(text)
    return NoteCard(
        note_id=note_id, date=pd.Timestamp(date), applies_to=applies_to.strip(), text=text.strip(),
        scope_all=scope_all, scope_routes=routes, effect=effect,
        window_start=start, window_end=end, window_source=source,
        magnitude=parse_magnitude(text) if effect == "raises" else None,
    )


def build_cards(notes_df: pd.DataFrame, cfg: Config = DEFAULT_CONFIG) -> list[NoteCard]:
    return [build_card(r.note_id, r.date, r.applies_to, r.note, cfg) for r in notes_df.itertuples(index=False)]
