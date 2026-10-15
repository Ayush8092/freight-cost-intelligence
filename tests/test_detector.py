import numpy as np
import pytest

from freight_watch.config import Config
from freight_watch.detector import evaluate

nan = float("nan")


def test_own_history_threshold_boundary_is_inclusive():
    assert evaluate(10.0, 0.0).own_hit
    assert not evaluate(9.999, 0.0).own_hit


def test_peer_threshold_boundary_is_inclusive_when_rising():
    assert evaluate(1.0, 20.0).peer_hit
    assert not evaluate(1.0, 19.999).peer_hit


def test_peer_rule_requires_cost_to_be_rising():
    assert not evaluate(-0.1, 40.0).flagged     # dearer than peers but falling: structural, not creep
    assert not evaluate(0.0, 40.0).flagged
    assert evaluate(0.1, 40.0).flagged


def test_decreases_are_never_flagged():
    assert not evaluate(-35.0, -35.0).flagged


def test_no_history_falls_back_to_peer_comparison():
    assert evaluate(nan, 25.0).peer_hit
    assert not evaluate(nan, nan).flagged
    assert not evaluate(nan, 5.0).flagged


def test_trigger_labels():
    assert evaluate(12, 5).label == "own_history"
    assert evaluate(5, 25).label == "peer_premium"
    assert evaluate(12, 25).label == "both"
    assert evaluate(1, 1).label == ""


def test_thresholds_are_configurable():
    cfg = Config(own_history_flag_pct=5.0)
    assert evaluate(6.0, 0.0, cfg).own_hit and not evaluate(6.0, 0.0).own_hit
