"""Aggregate weighted weekly costs and calculate history and peer baselines."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config, DEFAULT_CONFIG

GROUP_KEYS = ["origin", "destination", "route_type"]


def pct_diff(current: float, baseline: float) -> float:
    """(current - baseline) / baseline * 100; NaN if the baseline is missing, zero or negative."""
    if current is None or baseline is None or pd.isna(current) or pd.isna(baseline) or baseline <= 0:
        return float("nan")
    return (current - baseline) / baseline * 100.0


def weekly_costs(shipments: pd.DataFrame) -> pd.DataFrame:
    """One row per (origin, destination, route_type, week_of) with the weighted unit cost."""
    g = (
        shipments.groupby(GROUP_KEYS + ["week_of"], sort=True)
        .agg(
            n_shipments=("shipment_id", "count"),
            total_cost_inr=("freight_cost_inr", "sum"),
            total_tonne_km=("tonne_km", "sum"),
        )
        .reset_index()
    )
    g["route"] = g["origin"] + "-" + g["destination"]
    denom = g["total_tonne_km"].where(g["total_tonne_km"] > 0)  # zero denominator -> NaN, never inf
    g["cost_per_tonne_km"] = g["total_cost_inr"] / denom
    return g.sort_values(["route", "route_type", "week_of"], kind="mergesort").reset_index(drop=True)


def add_history_baseline(weekly: pd.DataFrame, window: int = 8) -> pd.DataFrame:
    weekly = weekly.sort_values(["route", "route_type", "week_of"], kind="mergesort").copy()
    prior = weekly.groupby(["route", "route_type"])["cost_per_tonne_km"].shift(1)  # excludes current week
    grouped = prior.groupby([weekly["route"], weekly["route_type"]])
    weekly["own_history_avg"] = grouped.transform(lambda s: s.rolling(window, min_periods=1).mean())
    weekly["hist_weeks_used"] = grouped.transform(lambda s: s.rolling(window, min_periods=1).count()).astype(int)
    weekly["vs_own_pct"] = [pct_diff(c, b) for c, b in zip(weekly["cost_per_tonne_km"], weekly["own_history_avg"])]
    return weekly


def add_peer_baseline(weekly: pd.DataFrame) -> pd.DataFrame:
    """Mean unit cost of the OTHER routes with the same route_type in the same week."""
    weekly = weekly.copy()
    peer_avg = pd.Series(np.nan, index=weekly.index, dtype=float)
    peer_n = pd.Series(0, index=weekly.index, dtype=int)
    for _, idx in weekly.groupby(["route_type", "week_of"]).groups.items():
        sub = weekly.loc[idx]
        for i in idx:
            others = sub.loc[(sub["route"] != sub.at[i, "route"]), "cost_per_tonne_km"].dropna()
            peer_n.at[i] = len(others)
            if len(others):
                peer_avg.at[i] = float(others.mean())
    weekly["peer_avg"] = peer_avg
    weekly["peer_count"] = peer_n
    weekly["vs_peer_pct"] = [pct_diff(c, b) for c, b in zip(weekly["cost_per_tonne_km"], weekly["peer_avg"])]
    return weekly


def build_metrics(shipments: pd.DataFrame, cfg: Config = DEFAULT_CONFIG) -> pd.DataFrame:
    weekly = weekly_costs(shipments)
    weekly = add_history_baseline(weekly, cfg.history_weeks)
    weekly = add_peer_baseline(weekly)
    return weekly.sort_values(["route", "week_of"], kind="mergesort").reset_index(drop=True)
