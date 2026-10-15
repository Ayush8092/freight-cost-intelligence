import hashlib
import shutil

import pandas as pd
import pytest

from freight_watch.ask import answer
from freight_watch.output import (OUTPUT_COLUMNS, fmt_pct, sample_columns, validate_output,
                                  OWN_SUFFIX, PEER_SUFFIX)
from freight_watch.pipeline import run_pipeline
from freight_watch.repro import run_repro


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory, data_paths):
    out = tmp_path_factory.mktemp("run")
    res = run_pipeline(data_paths["shipments"], data_paths["notes"], data_paths["sample"], out)
    return out, res


def load(out):
    return pd.read_csv(out / "output.csv", dtype=str, keep_default_na=False)


def test_columns_and_order_match_the_official_sample(run_dir, data_paths):
    out, _ = run_dir
    assert list(load(out).columns) == sample_columns(data_paths["sample"]) == OUTPUT_COLUMNS


def test_verdict_conventions(run_dir):
    df = load(run_dir[0])
    assert set(df["flagged"]) <= {"Yes", "No (justified)"}
    assert (df.loc[df["flagged"] == "Yes", "matched_note_id"] == "").all()
    assert (df.loc[df["flagged"] == "No (justified)", "matched_note_id"] != "").all()


def test_output_validates_against_contract(run_dir, data_paths):
    out, _ = run_dir
    ids = set(pd.read_csv(data_paths["notes"])["note_id"])
    assert validate_output(out / "output.csv", data_paths["sample"], ids) == []


def test_official_sample_rows_reproduced_exactly(run_dir, data_paths):
    df = load(run_dir[0])
    # The official sample is not strictly valid CSV: row 3's `reason` holds an unquoted comma
    # ("N006, 2025-09-22"), so a normal CSV parser sees 9 fields. `reason` is the LAST column,
    # so splitting on the first 7 commas reads every row correctly.
    lines = data_paths["sample"].read_text(encoding="utf-8-sig").splitlines()
    sample = [dict(zip(OUTPUT_COLUMNS, ln.split(",", 7))) for ln in lines[1:] if ln.strip()]
    assert len(sample) == 3
    structured = [c for c in OUTPUT_COLUMNS if c != "reason"]          # reason wording is free-form
    for s in sample:
        got = df[(df["route"] == s["route"]) & (df["week_of"] == s["week_of"])]
        assert len(got) == 1, f"sample row {s['route']} {s['week_of']} missing"
        for col in structured:
            assert got.iloc[0][col] == s[col], f"{s['route']} {s['week_of']} column {col}"


def test_justified_rows_cite_the_note_in_reason_and_unexplained_do_not_invent(run_dir):
    for r in load(run_dir[0]).itertuples(index=False):
        if r.flagged == "No (justified)":
            assert r.matched_note_id in r.reason
        else:
            assert "clear explanation" not in r.reason


def test_validator_catches_violations(tmp_path, data_paths):
    ids = {"N001"}
    good = ("route,week_of,cost_per_tonne_km,vs_own_history,vs_similar_routes,flagged,matched_note_id,reason\n")
    bad_rows = {
        "bad flag": "A-B,2025-01-20,3.29,+1.0% vs this route's past average,+1.0% vs similar-length routes this week,Maybe,,x\n",
        "justified without note": "A-B,2025-01-20,3.29,+1.0% vs this route's past average,+1.0% vs similar-length routes this week,No (justified),,x\n",
        "unexplained with note": "A-B,2025-01-20,3.29,+1.0% vs this route's past average,+1.0% vs similar-length routes this week,Yes,N001,x\n",
        "3 decimals": "A-B,2025-01-20,3.290,+1.0% vs this route's past average,+1.0% vs similar-length routes this week,Yes,,x\n",
        "not a Monday": "A-B,2025-01-21,3.29,+1.0% vs this route's past average,+1.0% vs similar-length routes this week,Yes,,x\n",
    }
    for name, row in bad_rows.items():
        p = tmp_path / "o.csv"; p.write_text(good + row)
        assert validate_output(p, data_paths["sample"], ids), f"validator missed: {name}"
    p.write_text("route,week_of\nA-B,2025-01-20\n")
    assert any("columns/order" in e for e in validate_output(p, data_paths["sample"], ids))


def test_percent_formatting():
    assert fmt_pct(35.5199, OWN_SUFFIX, "x") == "+35.5% vs this route's past average"
    assert fmt_pct(-4.14, PEER_SUFFIX, "x") == "-4.1% vs similar-length routes this week"
    assert fmt_pct(-0.04, OWN_SUFFIX, "x") == "+0.0% vs this route's past average"   # never "-0.0%"
    assert fmt_pct(float("nan"), OWN_SUFFIX, "no prior weeks") == "N/A (no prior weeks)"


def test_normal_weeks_are_not_emitted(run_dir):
    assert len(load(run_dir[0])) == 20 < len(run_dir[1].weekly) == 728


def test_two_in_process_runs_are_byte_identical(tmp_path, data_paths):
    digests = []
    for i in range(2):
        run_pipeline(data_paths["shipments"], data_paths["notes"], data_paths["sample"], tmp_path / f"r{i}")
        digests.append([hashlib.sha256((tmp_path / f"r{i}" / f).read_bytes()).hexdigest()
                        for f in ("output.csv", "weekly_metrics_debug.csv", "token_cost_log.json")])
    assert digests[0] == digests[1]


def test_three_separate_process_runs_identical(data_paths):
    rep = run_repro(data_paths["shipments"], data_paths["notes"], data_paths["sample"], runs=3)
    assert rep["identical_across_runs"] and len(rep["runs"]) == 3


def test_adding_unused_columns_to_inputs_does_not_change_numbers(tmp_path, data_paths):
    """The optional Q&A / reporting layers must not alter the official numbers."""
    a = run_pipeline(data_paths["shipments"], data_paths["notes"], data_paths["sample"], tmp_path / "a")
    findings = pd.read_csv(tmp_path / "a" / "output.csv", dtype=str, keep_default_na=False)
    answer("why did Chennai-Bangalore get pricier in March 2025?", findings)           # ask layer is read-only
    b = run_pipeline(data_paths["shipments"], data_paths["notes"], data_paths["sample"], tmp_path / "b")
    assert (tmp_path / "a" / "output.csv").read_bytes() == (tmp_path / "b" / "output.csv").read_bytes()
    assert a.weekly.equals(b.weekly)


def test_token_log_is_honest_zero(run_dir):
    import json
    log = json.loads((run_dir[0] / "token_cost_log.json").read_text())
    assert log["llm_calls"] == 0 and log["input_tokens"] == 0 and log["output_tokens"] == 0
    assert log["estimated_cost_usd"] == 0.0


def test_ask_answers_from_findings_only(run_dir):
    findings = load(run_dir[0])
    a = answer("why did Chennai-Bangalore get pricier in March 2025?", findings)
    assert "N001" in a and "2025-03-10" in a
    assert "None of my findings" in answer("what happened to Kolkata in 2019?", findings)
    assert "I can answer about" in answer("hello there", findings)
