"""Apply the configured own-history and peer thresholds to weekly metrics."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import Config, DEFAULT_CONFIG


@dataclass(frozen=True)
class Trigger:
    own_hit: bool
    peer_hit: bool

    @property
    def flagged(self) -> bool:
        return self.own_hit or self.peer_hit

    @property
    def label(self) -> str:
        if self.own_hit and self.peer_hit:
            return "both"
        if self.own_hit:
            return "own_history"
        if self.peer_hit:
            return "peer_premium"
        return ""


def evaluate(vs_own: float, vs_peer: float, cfg: Config = DEFAULT_CONFIG) -> Trigger:
    own_known = not pd.isna(vs_own)
    peer_known = not pd.isna(vs_peer)
    own_hit = own_known and vs_own >= cfg.own_history_flag_pct
    rising = (vs_own > 0) if own_known else True
    peer_hit = peer_known and vs_peer >= cfg.peer_flag_pct and rising
    return Trigger(bool(own_hit), bool(peer_hit))
