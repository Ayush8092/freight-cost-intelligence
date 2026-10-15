"""Score the pipeline against the labelled evaluation set."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pandas as pd

from .loader import load_notes
from .pipeline import run_pipeline

_NON_CAUSAL = re.compile(r"not\s+(?:significantly\s+)?affected|no\s+(?:major|significant)\s+disruption|"
                         r"without\s+a\s+rate\s+change|returned\s+to\s+normal|improved|not\s+part\s+of\s+this\s+dataset|"
                         r"remained\s+(?:stable|normal)", re.IGNORECASE)


def _spot_check_justified(rows: pd.DataFrame, notes: pd.DataFrame) -> list[str]:
    problems = []
    by_id = notes.set_index("note_id")
    for r in rows[rows["flagged"] == "No (justified)"].itertuples(index=False):
        tag = f"{r.route} {r.week_of} cites {r.matched_note_id}"
        if r.matched_note_id not in by_id.index:
            problems.append(f"{tag}: note does not exist"); continue
        n = by_id.loc[r.matched_note_id]
        if n["applies_to"].strip().lower() not in ("all routes", r.route.lower()):
            problems.append(f"{tag}: note applies to {n['applies_to']}")
        if n["note"] not in r.reason:
            problems.append(f"{tag}: note text not quoted verbatim in reason")
        if str(n["date"].date()) not in r.reason:
            problems.append(f"{tag}: note date missing from reason")
        if _NON_CAUSAL.search(n["note"]):
            problems.append(f"{tag}: note wording says no cost effect")
        if n["date"] > pd.Timestamp(r.week_of) + pd.Timedelta(days=6):
            problems.append(f"{tag}: note is dated after the week it explains")
    return problems


def run_eval(shipments, notes, sample, golden_path, report_path=None, verbose: bool = True) -> dict:
    golden = pd.read_csv(golden_path, dtype=str, keep_default_na=False)
    with tempfile.TemporaryDirectory() as tmp:
        run_pipeline(shipments, notes, sample, tmp)
        out = pd.read_csv(Path(tmp) / "output.csv", dtype=str, keep_default_na=False)
    notes_df = load_notes(notes)
    cases = []
    for g in golden.itertuples(index=False):
        hit = out[(out["route"] == g.route) & (out["week_of"] == g.week_of)]
        if g.expect_in_output == "N":
            ok = hit.empty
            got = "not emitted" if hit.empty else f"{hit.iloc[0]['flagged']} {hit.iloc[0]['matched_note_id']}".strip()
            expected = "not emitted"
        else:
            expected = f"{g.expect_flagged} {g.expect_note_id}".strip()
            if hit.empty:
                ok, got = False, "not emitted"
            else:
                row = hit.iloc[0]
                ok = row["flagged"] == g.expect_flagged and row["matched_note_id"] == g.expect_note_id
                got = f"{row['flagged']} {row['matched_note_id']}".strip()
        cases.append({"case_id": g.case_id, "route": g.route, "week_of": g.week_of,
                      "expected": expected, "got": got, "passed": bool(ok), "why": g.why})
    spot = _spot_check_justified(out, notes_df)
    passed = sum(c["passed"] for c in cases)
    report = {
        "golden_cases": len(cases), "golden_passed": passed,
        "spot_check_justified_rows": int((out["flagged"] == "No (justified)").sum()),
        "spot_check_problems": spot,
        "all_passed": passed == len(cases) and not spot,
        "cases": cases,
    }
    if verbose:
        for c in cases:
            print(f"[{'PASS' if c['passed'] else 'FAIL'}] {c['case_id']} {c['route']} {c['week_of']}: "
                  f"expected {c['expected']!r}, got {c['got']!r}")
        print(f"\nGolden set: {passed}/{len(cases)} passed")
        print(f"Spot-check of {report['spot_check_justified_rows']} justified rows: "
              f"{'no problems' if not spot else spot}")
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
