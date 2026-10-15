import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freight_watch.loader import load_shipments  # noqa: E402

DATA = ROOT / "data"
HEADER = "shipment_id,origin,destination,route_type,material,quantity_tonnes,distance_km,freight_cost_inr,shipment_date,transporter\n"


@pytest.fixture(scope="session")
def data_paths():
    return {"shipments": DATA / "shipment_records.csv", "notes": DATA / "context_notes.csv",
            "sample": DATA / "sample_output_format_v2.csv"}


def ship(sid, origin="A", dest="B", rtype="Short", qty=1, km=1, cost=1, date="2024-01-01"):
    return f"{sid},{origin},{dest},{rtype},Steel,{qty},{km},{cost},{date},T1\n"


@pytest.fixture
def make_shipments(tmp_path):
    """Write rows (lines from ship()) to a CSV and load them through the real loader."""
    def _make(*lines, strict=False):
        p = tmp_path / "ships.csv"
        p.write_text(HEADER + "".join(lines), encoding="utf-8")
        return load_shipments(p, strict=strict)
    return _make


def weekly_series(make_shipments, route_values, rtype="Short", start="2024-01-01", weeks=None):
    """One shipment per route-week with qty=1, km=1 so cost_per_tonne_km == the value given.
    route_values: {"A-B": [v1, v2, ...]}; weeks (optional) = list of week offsets to use."""
    lines, n = [], 0
    base = pd.Timestamp(start)
    for route, vals in route_values.items():
        o, d = route.split("-")
        offsets = weeks if weeks is not None else range(len(vals))
        for off, v in zip(offsets, vals):
            n += 1
            lines.append(ship(f"S{n:04d}", o, d, rtype, 1, 1, v, str((base + pd.Timedelta(weeks=off)).date())))
    return make_shipments(*lines)[0]
