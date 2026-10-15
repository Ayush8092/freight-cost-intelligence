"""Validate route, time window, cost effect, scope, and magnitude before accepting a note."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .config import Config, DEFAULT_CONFIG
from .detector import Trigger
from .notes import NoteCard
from .retrieval import NoteRetriever

JUSTIFIED = "justified"
ROUTE_MISMATCH = "route_mismatch"
OUTSIDE_WINDOW = "outside_window"
NO_COST_EFFECT = "no_cost_effect"
LOWERS_COSTS = "lowers_costs"
UNCLEAR_EFFECT = "no_cost_increase_described"
BROAD_NOTE_PEER_GAP = "broad_note_cannot_explain_peer_gap"
PARTIAL = "explains_only_part"
NO_NEARBY_NOTE = "no_nearby_note"


@dataclass(frozen=True)
class Judgement:
    code: str
    detail: str = ""

    @property
    def justified(self) -> bool:
        return self.code == JUSTIFIED


@dataclass(frozen=True)
class Decision:
    justified: bool
    code: str                       # JUSTIFIED, or the code of the closest rejection
    note: Optional[NoteCard]        # the citing note when justified
    rejected: tuple                 # ((NoteCard, Judgement), ...) nearby notes that failed, for the reason text
    similarity: float = 0.0


def judge(card: NoteCard, route: str, week_start: pd.Timestamp, vs_own: float, trigger: Trigger,
          cfg: Config = DEFAULT_CONFIG) -> Judgement:
    week_end = week_start + pd.Timedelta(days=6)
    if not card.applies_to_route(route):
        return Judgement(ROUTE_MISMATCH, f"applies to {card.applies_to}, not {route}")
    if card.effect == "none":
        return Judgement(NO_COST_EFFECT, "states costs were not affected or conditions were stable/normal")
    if card.effect == "lowers":
        return Judgement(LOWERS_COSTS, "describes improved conditions, which would lower costs rather than raise them")
    if card.effect != "raises":
        return Judgement(UNCLEAR_EFFECT, "does not describe a cost increase")
    if card.window_end < week_start or card.window_start > week_end:
        return Judgement(OUTSIDE_WINDOW,
                         f"covers {card.window_start.date()} to {card.window_end.date()}, which does not include the week of {week_start.date()}")
    if card.scope_all and trigger.peer_hit:
        return Judgement(BROAD_NOTE_PEER_GAP,
                         "applies to all routes, so it cannot explain this route being dearer than its peers")
    if card.magnitude and not pd.isna(vs_own):
        lo, hi = card.magnitude
        if vs_own > hi + cfg.magnitude_tolerance_pp:
            rng = f"{lo:g}-{hi:g}%" if lo != hi else f"{hi:g}%"
            return Judgement(PARTIAL, f"cites a rise of roughly {rng} but this week is {vs_own:+.1f}% vs history, beyond what the note covers")
    return Judgement(JUSTIFIED)


def _gap_days(card: NoteCard, week_start: pd.Timestamp) -> int:
    week_end = week_start + pd.Timedelta(days=6)
    if card.window_end < week_start:
        return (week_start - card.window_end).days
    if card.window_start > week_end:
        return (card.window_start - week_end).days
    return 0


def decide(route: str, week_start: pd.Timestamp, vs_own: float, trigger: Trigger,
           retriever: NoteRetriever, cfg: Config = DEFAULT_CONFIG, vs_peer: float | None = None) -> Decision:
    ranked = retriever.rank(route, week_start, vs_own, vs_peer)
    judged = [(c, s, judge(c, route, week_start, vs_own, trigger, cfg)) for c, s in ranked]

    for card, score, j in judged:  # highest similarity first; first note passing every gate wins
        if j.justified:
            return Decision(True, JUSTIFIED, card, (), score)

    # No note justifies. Collect the in-scope notes near this week so the reason can say
    # why the closest ones were rejected (wording only; nothing here can justify).
    nearby = [(c, j) for c, _, j in judged
              if j.code != ROUTE_MISMATCH and _gap_days(c, week_start) <= cfg.near_note_days]
    nearby.sort(key=lambda cj: (_gap_days(cj[0], week_start), cj[0].note_id))
    nearby = tuple(nearby[:2])
    code = nearby[0][1].code if nearby else NO_NEARBY_NOTE
    return Decision(False, code, None, nearby)
