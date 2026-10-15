"""Build concise explanations from metrics and validated note evidence."""
from __future__ import annotations

import math

from .verdict import (BROAD_NOTE_PEER_GAP, Decision, LOWERS_COSTS, NO_COST_EFFECT,
                      NO_NEARBY_NOTE, OUTSIDE_WINDOW, PARTIAL, UNCLEAR_EFFECT)

_SHORT_REASON = {
    NO_COST_EFFECT: "it says costs were unaffected or conditions were stable",
    LOWERS_COSTS: "it describes improved conditions, not a cost increase",
    UNCLEAR_EFFECT: "it does not describe a cost increase",
    OUTSIDE_WINDOW: "its effective period does not cover this week",
}


def _rejection_clause(card, judgement) -> str:
    base = f"{card.note_id} ({card.date.date()})"
    if judgement.code in (PARTIAL, BROAD_NOTE_PEER_GAP, OUTSIDE_WINDOW):
        return f"{base}: {judgement.detail}"
    return f"{base}: {_SHORT_REASON.get(judgement.code, judgement.detail)}"


def _signal_text(vs_own: float | None, vs_peer: float | None) -> str:
    parts = []
    for value, label in ((vs_own, "own history"), (vs_peer, "similar routes")):
        if value is not None and not math.isnan(float(value)):
            parts.append(f"{float(value):+.1f}% vs {label}")
    return "Signals: " + "; ".join(parts) + ". " if parts else ""


def build_reason(decision: Decision, hist_weeks_used: int, history_weeks: int = 8,
                 vs_own: float | None = None, vs_peer: float | None = None) -> str:
    signal = _signal_text(vs_own, vs_peer)
    if decision.justified:
        card = decision.note
        text = (f"{signal}Matches note {card.note_id} dated {card.date.date()} "
                f"(applies to {card.applies_to}; effective {card.window_start.date()} to "
                f"{card.window_end.date()}): {card.text} The cost rise has a clear explanation.")
    elif decision.code == NO_NEARBY_NOTE or not decision.rejected:
        text = signal + "No matching note found for this route or date range. Cost rise is unexplained and needs human review."
    else:
        clauses = "; ".join(_rejection_clause(card, judgement) for card, judgement in decision.rejected)
        label = "The closest note" if len(decision.rejected) == 1 else "The closest notes"
        text = signal + f"{label} did not justify the rise: {clauses}. No valid justification found; flagged for review."
    if hist_weeks_used < history_weeks:
        text += f" Own-history baseline uses {hist_weeks_used} prior week(s)."
    return text
