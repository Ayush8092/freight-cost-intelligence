"""Load CSV inputs, quarantine invalid shipments, and report data quality."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .errors import DataValidationError

SHIPMENT_COLUMNS = [
    "shipment_id", "origin", "destination", "route_type", "material",
    "quantity_tonnes", "distance_km", "freight_cost_inr", "shipment_date", "transporter",
]
NOTE_COLUMNS = ["note_id", "date", "applies_to", "note"]
_REQUIRED_TEXT = ["shipment_id", "origin", "destination", "route_type"]


@dataclass
class DataQualityReport:
    rows_read: int = 0
    rows_used: int = 0
    duplicates_removed: int = 0
    quarantined: dict = field(default_factory=dict)  # reason -> count
    quarantined_ids: list = field(default_factory=list)

    @property
    def rows_quarantined(self) -> int:
        return sum(self.quarantined.values())

    def to_dict(self) -> dict:
        return {
            "rows_read": self.rows_read,
            "rows_used": self.rows_used,
            "duplicates_removed": self.duplicates_removed,
            "rows_quarantined": self.rows_quarantined,
            "quarantined_by_reason": dict(sorted(self.quarantined.items())),
            "quarantined_ids_first_20": self.quarantined_ids[:20],
        }


def monday_of(ts: pd.Series | pd.Timestamp):
    """Monday of the Monday-to-Sunday week containing each date (time stripped)."""
    if isinstance(ts, pd.Series):
        ts = ts.dt.normalize()
        return ts - pd.to_timedelta(ts.dt.weekday, unit="D")
    ts = pd.Timestamp(ts).normalize()
    return ts - pd.Timedelta(days=ts.weekday())


def _read_csv(path: str | Path, required: list[str], what: str) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise DataValidationError(f"{what} file not found: {path}")
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception as exc:  # unreadable / empty file
        raise DataValidationError(f"Could not read {what} file {path}: {exc}") from exc
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataValidationError(f"{what} file {path.name} is missing columns: {missing}")
    return df


def load_shipments(path: str | Path, strict: bool = False) -> tuple[pd.DataFrame, DataQualityReport]:
    raw = _read_csv(path, SHIPMENT_COLUMNS, "shipment")
    report = DataQualityReport(rows_read=len(raw))
    df = raw.copy()
    for col in _REQUIRED_TEXT + ["material", "transporter"]:
        df[col] = df[col].str.strip()

    df["quantity_tonnes"] = pd.to_numeric(df["quantity_tonnes"], errors="coerce")
    df["distance_km"] = pd.to_numeric(df["distance_km"], errors="coerce")
    df["freight_cost_inr"] = pd.to_numeric(df["freight_cost_inr"], errors="coerce")
    df["shipment_date"] = pd.to_datetime(df["shipment_date"].str.strip(), format="%Y-%m-%d", errors="coerce")

    # Duplicates first: a repeated shipment_id is the same shipment, counted once.
    dup = df.duplicated(subset="shipment_id", keep="first") & (df["shipment_id"] != "")
    report.duplicates_removed = int(dup.sum())
    df = df[~dup]

    reasons = pd.Series("", index=df.index)

    def mark(mask: pd.Series, reason: str) -> None:
        nonlocal reasons
        hit = mask & (reasons == "")  # first failing reason wins
        reasons = reasons.mask(hit, reason)

    mark((df[_REQUIRED_TEXT] == "").any(axis=1), "missing_text_field")
    mark(df["shipment_date"].isna(), "missing_or_malformed_date")
    mark(df[["quantity_tonnes", "distance_km", "freight_cost_inr"]].isna().any(axis=1), "missing_or_non_numeric_value")
    mark((df["quantity_tonnes"] <= 0) | (df["distance_km"] <= 0), "non_positive_quantity_or_distance")
    mark(df["freight_cost_inr"] <= 0, "non_positive_cost")

    bad = reasons != ""
    if bad.any():
        counts = reasons[bad].value_counts().to_dict()
        report.quarantined = {k: int(v) for k, v in counts.items()}
        report.quarantined_ids = df.loc[bad, "shipment_id"].tolist()
        if strict:
            raise DataValidationError(f"{int(bad.sum())} invalid shipment rows (strict mode): {report.quarantined}")
    df = df[~bad].copy()

    df["route"] = df["origin"] + "-" + df["destination"]
    df["tonne_km"] = df["quantity_tonnes"] * df["distance_km"]
    df["week_of"] = monday_of(df["shipment_date"])
    df = df.sort_values(["route", "shipment_date", "shipment_id"], kind="mergesort").reset_index(drop=True)
    report.rows_used = len(df)
    return df, report


def load_notes(path: str | Path) -> pd.DataFrame:
    df = _read_csv(path, NOTE_COLUMNS, "context-notes")
    for col in NOTE_COLUMNS:
        df[col] = df[col].str.strip()
    if (df["note_id"] == "").any() or (df["note"] == "").any():
        raise DataValidationError("context notes must all have a note_id and note text")
    if df["note_id"].duplicated().any():
        raise DataValidationError(f"duplicate note_id values: {df.loc[df['note_id'].duplicated(), 'note_id'].tolist()}")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    if df["date"].isna().any():
        raise DataValidationError(f"malformed note dates for: {df.loc[df['date'].isna(), 'note_id'].tolist()}")
    return df.sort_values("note_id", kind="mergesort").reset_index(drop=True)
