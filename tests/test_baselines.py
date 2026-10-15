import numpy as np
import pandas as pd
import pytest

from conftest import weekly_series
from freight_watch.metrics import build_metrics, pct_diff


def row(m, route, week_index, start="2024-01-01"):
    week = pd.Timestamp(start) + pd.Timedelta(weeks=week_index)
    return m[(m["route"] == route) & (m["week_of"] == week)].iloc[0]


def test_pct_diff_formula_and_unavailable_baselines():
    assert pct_diff(150, 100) == pytest.approx(50.0)
    assert pct_diff(80, 100) == pytest.approx(-20.0)
    for bad in (0, -1, np.nan, None):
        assert np.isnan(pct_diff(100, bad))


def test_history_excludes_current_week_and_uses_exactly_eight(make_shipments):
    vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 100]          # 10th week is a huge spike
    m = build_metrics(weekly_series(make_shipments, {"A-B": vals}))
    r = row(m, "A-B", 9)
    assert r.own_history_avg == pytest.approx(np.mean([2, 3, 4, 5, 6, 7, 8, 9]))   # weeks 2..9, spike excluded
    assert r.hist_weeks_used == 8
    assert r.vs_own_pct == pytest.approx((100 - 5.5) / 5.5 * 100)


def test_fewer_than_eight_prior_weeks_uses_all_available(make_shipments):
    m = build_metrics(weekly_series(make_shipments, {"A-B": [2, 4, 6, 20]}))
    r = row(m, "A-B", 3)
    assert r.hist_weeks_used == 3 and r.own_history_avg == pytest.approx(4.0)


def test_no_history_for_first_week(make_shipments):
    m = build_metrics(weekly_series(make_shipments, {"A-B": [2, 4]}))
    r = row(m, "A-B", 0)
    assert r.hist_weeks_used == 0 and np.isnan(r.own_history_avg) and np.isnan(r.vs_own_pct)


def test_missing_weeks_are_not_fabricated(make_shipments):
    # observed weeks 0,1,2 then 5: baseline for week 5 is the 3 observed values, no padding
    m = build_metrics(weekly_series(make_shipments, {"A-B": [1, 2, 3, 10]}, weeks=[0, 1, 2, 5]))
    r = row(m, "A-B", 5)
    assert r.hist_weeks_used == 3 and r.own_history_avg == pytest.approx(2.0)


def test_peer_baseline_excludes_the_route_itself(make_shipments):
    m = build_metrics(weekly_series(make_shipments, {"A-B": [10], "C-D": [20], "E-F": [40]}))
    a = row(m, "A-B", 0)
    assert a.peer_avg == pytest.approx(30.0) and a.peer_count == 2     # mean(20, 40), not mean(10, 20, 40)
    assert a.vs_peer_pct == pytest.approx((10 - 30) / 30 * 100)


def test_no_eligible_peers_gives_nan(make_shipments):
    m = build_metrics(weekly_series(make_shipments, {"A-B": [10]}))
    r = row(m, "A-B", 0)
    assert r.peer_count == 0 and np.isnan(r.peer_avg) and np.isnan(r.vs_peer_pct)


def test_peers_must_share_route_type(make_shipments, tmp_path):
    short = weekly_series(make_shipments, {"A-B": [10]}, rtype="Short")
    long_ = weekly_series(make_shipments, {"C-D": [99]}, rtype="Long")
    both = pd.concat([short, long_], ignore_index=True)
    m = build_metrics(both)
    assert row(m, "A-B", 0).peer_count == 0     # the Long route is not a peer of a Short route


def test_peers_compared_in_the_same_week_only(make_shipments):
    m = build_metrics(weekly_series(make_shipments, {"A-B": [10, 10], "C-D": [20, 40]}))
    assert row(m, "A-B", 0).peer_avg == pytest.approx(20) and row(m, "A-B", 1).peer_avg == pytest.approx(40)
