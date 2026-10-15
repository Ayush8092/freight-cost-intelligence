"""Deterministic orchestration for detection and evidence validation."""
from __future__ import annotations

import pandas as pd

from . import detector
from .config import Config, DEFAULT_CONFIG
from .detector import Trigger
from .retrieval import NoteRetriever
from .verdict import Decision, decide


class DeterministicAIWrapper:
    """Keep numeric decisions and evidence checks local, stable, and auditable."""

    def __init__(self, retriever: NoteRetriever, cfg: Config = DEFAULT_CONFIG):
        self.retriever = retriever
        self.cfg = cfg

    def assess(self, route: str, week_start: pd.Timestamp, vs_own: float,
               vs_peer: float) -> tuple[Trigger, Decision | None]:
        trigger = detector.evaluate(vs_own, vs_peer, self.cfg)
        if not trigger.flagged:
            return trigger, None
        decision = decide(route, week_start, vs_own, trigger, self.retriever, self.cfg, vs_peer)
        return trigger, decision
