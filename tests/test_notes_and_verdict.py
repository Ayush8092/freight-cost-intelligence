"""Evidence-gate tests: every way a note can fail to justify, plus the ways it can."""
import pandas as pd
import pytest

from freight_watch.detector import Trigger
from freight_watch import verdict as V
from freight_watch.notes import build_card, classify_effect, parse_magnitude
from freight_watch.retrieval import NoteRetriever

WEEK = pd.Timestamp("2025-02-24")           # a Monday
OWN = Trigger(own_hit=True, peer_hit=False)
PEER = Trigger(own_hit=False, peer_hit=True)
ROUTE = "Chennai-Bangalore"


def card(text, applies="Chennai-Bangalore", date="2025-02-24", nid="T1"):
    return build_card(nid, pd.Timestamp(date), applies, text)


FLOOD = "Heavy flooding disrupted truck movement from Feb 24 to Mar 8, forcing detours and higher trip costs."


def test_effect_classification():
    assert classify_effect(FLOOD) == "raises"
    assert classify_effect("Costs were not significantly affected.") == "none"
    assert classify_effect("Roads improved after resurfacing.") == "lowers"
    assert classify_effect("Compliance costs were absorbed without a rate change.") == "none"
    assert classify_effect("The committee met on Tuesday.") == "unclear"
    assert classify_effect("Slower trucks were seen.") == "unclear"      # 'slower' must not match 'lower'


def test_ambiguity_resolves_to_non_justifying():
    assert classify_effect("Prices rose but costs were not significantly affected.") == "none"


def test_window_rules():
    c = card(FLOOD)
    assert (c.window_start, c.window_end) == (pd.Timestamp("2025-02-24"), pd.Timestamp("2025-03-08"))
    step = card("Diesel prices rose nationwide starting this week.", "All Routes", "2025-05-07")
    assert step.window_start == pd.Timestamp("2025-05-05")                          # Monday of the note week
    assert step.window_end == pd.Timestamp("2025-06-29")                            # + 8 weeks, then Sunday
    one_week = card("A festival surcharge applied.", date="2025-01-22")             # a Wednesday
    assert (one_week.window_start, one_week.window_end) == (pd.Timestamp("2025-01-20"), pd.Timestamp("2025-01-26"))


def test_year_wrapping_range():
    c = card("Closure from Dec 28 to Jan 4 raised costs.", date="2024-12-28")
    assert c.window_end == pd.Timestamp("2025-01-04")


def test_magnitude_parsing():
    assert parse_magnitude("roughly 5-7% higher") == (5.0, 7.0)
    assert parse_magnitude("a 3% rise") == (3.0, 3.0)
    assert parse_magnitude("no numbers here") is None


def test_valid_note_justifies():
    assert V.judge(card(FLOOD), ROUTE, WEEK, 30.0, OWN).justified


def test_route_mismatched_note_rejected():
    j = V.judge(card(FLOOD, applies="Delhi-Jaipur"), ROUTE, WEEK, 30.0, OWN)
    assert j.code == V.ROUTE_MISMATCH


def test_route_match_is_case_insensitive_and_multi_route():
    assert card(FLOOD, applies="chennai-bangalore").applies_to_route(ROUTE)
    assert card(FLOOD, applies="Delhi-Jaipur; Chennai-Bangalore").applies_to_route(ROUTE)


@pytest.mark.parametrize("week", ["2025-03-10", "2025-02-17"])   # just after / just before the window
def test_note_outside_its_window_rejected(week):
    j = V.judge(card(FLOOD), ROUTE, pd.Timestamp(week), 30.0, OWN)
    assert j.code == V.OUTSIDE_WINDOW


def test_week_overlapping_the_window_by_one_day_is_accepted():
    # window ends Sat Mar 8; week of Mar 3 (Mar 3-9) overlaps it
    assert V.judge(card(FLOOD), ROUTE, pd.Timestamp("2025-03-03"), 30.0, OWN).justified


def test_improved_conditions_note_rejected():
    c = card("Authorities announced improved road conditions after resurfacing.", date="2025-02-24")
    assert V.judge(c, ROUTE, WEEK, 30.0, OWN).code == V.LOWERS_COSTS


def test_cost_unaffected_note_rejected():
    c = card("Maintenance caused minor delays; costs were not significantly affected.")
    assert V.judge(c, ROUTE, WEEK, 30.0, OWN).code == V.NO_COST_EFFECT


def test_no_rate_change_note_rejected():
    c = card("A tracking mandate was introduced; compliance costs were absorbed by transporters without a rate change.",
             applies="All Routes")
    assert V.judge(c, ROUTE, WEEK, 30.0, OWN).code == V.NO_COST_EFFECT


def test_broad_note_applies_to_every_route():
    c = card("Diesel prices rose nationwide starting this week, pushing up costs by roughly 5-7%.", "All Routes")
    for r in ("Chennai-Bangalore", "Mumbai-Pune", "Delhi-Jaipur"):
        assert V.judge(c, r, WEEK, 8.0, OWN).justified


def test_broad_note_cannot_explain_a_peer_gap():
    c = card("Diesel prices rose nationwide starting this week, pushing up costs by roughly 5-7%.", "All Routes")
    assert V.judge(c, ROUTE, WEEK, 8.0, PEER).code == V.BROAD_NOTE_PEER_GAP


def test_partial_explanation_rejected_and_boundary():
    c = card("Diesel prices rose nationwide starting this week, pushing up costs by roughly 5-7%.", "All Routes")
    assert V.judge(c, ROUTE, WEEK, 11.6, OWN).code == V.PARTIAL
    assert V.judge(c, ROUTE, WEEK, 9.0, OWN).justified           # exactly 7% + 2pp tolerance
    assert V.judge(c, ROUTE, WEEK, 9.01, OWN).code == V.PARTIAL


def test_unclear_note_rejected():
    assert V.judge(card("A meeting was held."), ROUTE, WEEK, 30.0, OWN).code == V.UNCLEAR_EFFECT


def test_similarity_alone_never_justifies():
    # Text is extremely similar to the retrieval query but says costs were NOT affected.
    c = card("Chennai-Bangalore freight cost increase surcharge disruption: costs were not significantly affected.")
    d = V.decide(ROUTE, WEEK, 30.0, OWN, NoteRetriever([c]))
    assert not d.justified and d.note is None


def test_decide_picks_the_valid_note_over_a_more_similar_invalid_one():
    bad = card("Chennai-Bangalore freight cost increase surcharge disruption higher costs: not significantly affected.", nid="A_BAD")
    good = card(FLOOD, nid="Z_GOOD")
    d = V.decide(ROUTE, WEEK, 30.0, OWN, NoteRetriever([bad, good]))
    assert d.justified and d.note.note_id == "Z_GOOD"


def test_unexplained_decision_has_no_note_and_reports_nearby_rejections():
    neutral = card("Conditions remained normal.", date="2025-03-03", nid="N_NEUTRAL")
    d = V.decide(ROUTE, WEEK, 30.0, OWN, NoteRetriever([neutral]))
    assert not d.justified and d.note is None
    assert d.rejected and d.rejected[0][0].note_id == "N_NEUTRAL"


def test_no_nearby_note():
    far = card(FLOOD, date="2023-01-02", nid="OLD")
    d = V.decide(ROUTE, WEEK, 30.0, OWN, NoteRetriever([far]))
    assert d.code == V.NO_NEARBY_NOTE and d.rejected == ()


def test_retrieval_order_is_stable():
    cards = [card("freight cost", nid=f"N{i}") for i in range(3)]       # identical text -> identical scores
    ids = [c.note_id for c, _ in NoteRetriever(cards).rank(ROUTE)]
    assert ids == sorted(ids)
