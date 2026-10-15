import pandas as pd
import pytest

from conftest import ship
from freight_watch.loader import monday_of
from freight_watch.metrics import weekly_costs


@pytest.mark.parametrize("day,monday", [
    ("2024-01-01", "2024-01-01"),   # Monday maps to itself
    ("2024-01-07", "2024-01-01"),   # Sunday belongs to the week that started the previous Monday
    ("2024-01-08", "2024-01-08"),   # next Monday starts a new week
    ("2024-01-03", "2024-01-01"),
    ("2025-01-01", "2024-12-30"),   # crosses a year boundary
])
def test_monday_based_week(day, monday):
    assert monday_of(pd.Timestamp(day)) == pd.Timestamp(monday)


def test_sunday_and_next_monday_are_different_weeks(make_shipments):
    df, _ = make_shipments(ship("S1", date="2024-01-07"), ship("S2", date="2024-01-08"))
    assert sorted(df["week_of"].dt.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-01-08"]


def test_cost_is_weighted_not_mean_of_ratios(make_shipments):
    # ratios are 1.0 and 5.0 (mean 3.0) but the weighted answer is 1500 / (1000 + 100)
    df, _ = make_shipments(ship("S1", qty=10, km=100, cost=1000), ship("S2", qty=1, km=100, cost=500))
    w = weekly_costs(df)
    assert len(w) == 1
    assert w.loc[0, "cost_per_tonne_km"] == pytest.approx(1500 / 1100)
    assert w.loc[0, "cost_per_tonne_km"] != pytest.approx(3.0)


def test_multiple_shipments_in_one_route_week_are_aggregated(make_shipments):
    df, _ = make_shipments(ship("S1", date="2024-01-01"), ship("S2", date="2024-01-03"), ship("S3", date="2024-01-07"))
    w = weekly_costs(df)
    assert len(w) == 1 and w.loc[0, "n_shipments"] == 3 and w.loc[0, "total_cost_inr"] == 3


def test_duplicate_shipment_ids_counted_once(make_shipments):
    df, rep = make_shipments(ship("S1", cost=100), ship("S1", cost=100), ship("S2", cost=50))
    assert rep.duplicates_removed == 1 and len(df) == 2
    assert weekly_costs(df).loc[0, "total_cost_inr"] == 150


def test_route_type_is_part_of_the_group(make_shipments):
    df, _ = make_shipments(ship("S1", rtype="Short"), ship("S2", rtype="Long"))
    assert len(weekly_costs(df)) == 2


def test_zero_tonne_km_gives_nan_not_inf():
    df = pd.DataFrame({"origin": ["A"], "destination": ["B"], "route_type": ["Short"],
                       "week_of": [pd.Timestamp("2024-01-01")], "shipment_id": ["S1"],
                       "freight_cost_inr": [100.0], "tonne_km": [0.0]})
    w = weekly_costs(df)
    assert pd.isna(w.loc[0, "cost_per_tonne_km"])
