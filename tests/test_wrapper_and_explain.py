import pandas as pd

from freight_watch.config import DEFAULT_CONFIG
from freight_watch.explain import build_reason
from freight_watch.notes import build_card
from freight_watch.retrieval import NoteRetriever
from freight_watch.wrapper import DeterministicAIWrapper


def test_wrapper_keeps_detection_and_evidence_decisions_together():
    card = build_card(
        "N001", pd.Timestamp("2025-02-24"), "Chennai-Bangalore",
        "Flooding increased freight costs from Feb 24 to Mar 8.",
    )
    assistant = DeterministicAIWrapper(NoteRetriever([card]))
    trigger, decision = assistant.assess(
        "Chennai-Bangalore", pd.Timestamp("2025-03-03"), 30.0, 2.0,
    )
    assert trigger.flagged
    assert decision is not None and decision.justified
    assert decision.note.note_id == "N001"


def test_wrapper_does_not_retrieve_evidence_for_normal_weeks():
    card = build_card("N001", pd.Timestamp("2025-02-24"), "Chennai-Bangalore", "Flooding increased freight costs.")
    trigger, decision = DeterministicAIWrapper(NoteRetriever([card])).assess(
        "Chennai-Bangalore", pd.Timestamp("2025-03-03"), 1.0, 1.0,
    )
    assert not trigger.flagged
    assert decision is None


def test_explanation_includes_computed_comparison_signals():
    card = build_card("N001", pd.Timestamp("2025-02-24"), "Chennai-Bangalore",
                      "Flooding increased freight costs from Feb 24 to Mar 8.")
    _, decision = DeterministicAIWrapper(NoteRetriever([card]), DEFAULT_CONFIG).assess(
        "Chennai-Bangalore", pd.Timestamp("2025-03-03"), 30.0, 4.0,
    )
    reason = build_reason(decision, 8, 8, 30.0, 4.0)
    assert "Signals: +30.0% vs own history; +4.0% vs similar routes." in reason
    assert "N001" in reason
