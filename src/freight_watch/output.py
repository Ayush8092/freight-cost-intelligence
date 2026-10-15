"""Write and validate the assignment CSV schema."""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd

OUTPUT_COLUMNS = ["route", "week_of", "cost_per_tonne_km", "vs_own_history", "vs_similar_routes",
                  "flagged", "matched_note_id", "reason"]
FLAG_UNEXPLAINED = "Yes"
FLAG_JUSTIFIED = "No (justified)"
OWN_SUFFIX = "vs this route's past average"
PEER_SUFFIX = "vs similar-length routes this week"
_OWN_RE = re.compile(r"^[+-]\d+\.\d% vs this route's past average$|^N/A")
_PEER_RE = re.compile(r"^[+-]\d+\.\d% vs similar-length routes this week$|^N/A")


def fmt_pct(value: float, suffix: str, na_note: str) -> str:
    if value is None or pd.isna(value):
        return f"N/A ({na_note})"
    rounded = round(float(value), 1)
    if rounded == 0:
        rounded = 0.0  # avoid "-0.0%"
    return f"{rounded:+.1f}% {suffix}"


def fmt_cost(value: float) -> str:
    return f"{float(value):.2f}"


def sample_columns(sample_path: str | Path) -> list[str]:
    with open(sample_path, newline="", encoding="utf-8-sig") as fh:
        return next(csv.reader(fh))


def write_output(rows: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r[c] for c in OUTPUT_COLUMNS})


def validate_output(path: str | Path, sample_path: str | Path, note_ids: set[str]) -> list[str]:
    """Return a list of contract violations (empty list == compliant)."""
    errors: list[str] = []
    expected = sample_columns(sample_path)
    if expected != OUTPUT_COLUMNS:
        errors.append(f"sample header {expected} differs from the contract constant {OUTPUT_COLUMNS}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(df.columns) != expected:
        errors.append(f"columns/order {list(df.columns)} != {expected}")
        return errors
    if df.duplicated(["route", "week_of"]).any():
        errors.append("duplicate (route, week_of) rows")
    for i, r in df.iterrows():
        tag = f"row {i + 2} ({r['route']} {r['week_of']})"
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["week_of"]) or pd.Timestamp(r["week_of"]).weekday() != 0:
            errors.append(f"{tag}: week_of must be a YYYY-MM-DD Monday")
        if not re.fullmatch(r"\d+\.\d{2}", r["cost_per_tonne_km"]):
            errors.append(f"{tag}: cost_per_tonne_km must have 2 decimals")
        if not _OWN_RE.match(r["vs_own_history"]):
            errors.append(f"{tag}: bad vs_own_history text")
        if not _PEER_RE.match(r["vs_similar_routes"]):
            errors.append(f"{tag}: bad vs_similar_routes text")
        if r["flagged"] not in (FLAG_UNEXPLAINED, FLAG_JUSTIFIED):
            errors.append(f"{tag}: flagged must be 'Yes' or 'No (justified)', got {r['flagged']!r}")
        if r["flagged"] == FLAG_JUSTIFIED and r["matched_note_id"] not in note_ids:
            errors.append(f"{tag}: justified row must cite a real note id")
        if r["flagged"] == FLAG_UNEXPLAINED and r["matched_note_id"] != "":
            errors.append(f"{tag}: unexplained row must have a blank matched_note_id")
        if r["flagged"] == FLAG_JUSTIFIED and r["matched_note_id"] not in r["reason"]:
            errors.append(f"{tag}: reason must name the cited note id")
        if not r["reason"].strip():
            errors.append(f"{tag}: empty reason")
    return errors
