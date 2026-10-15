"""End-to-end orchestration: load -> metrics -> detect -> retrieve+validate -> explain -> write."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import Config, DEFAULT_CONFIG
from .explain import build_reason
from .loader import DataQualityReport, load_notes, load_shipments
from .metrics import build_metrics
from .notes import build_cards
from .output import (FLAG_JUSTIFIED, FLAG_UNEXPLAINED, OWN_SUFFIX,
                     PEER_SUFFIX, fmt_cost, fmt_pct, validate_output, write_output)
from .retrieval import NoteRetriever
from .usage import UsageTracker
from .wrapper import DeterministicAIWrapper


@dataclass
class PipelineResult:
    output_rows: list
    weekly: pd.DataFrame          # every route-week with baselines, trigger and decision (debug view)
    quality: DataQualityReport
    shipments_rows: int
    cards: list


def build_findings(weekly: pd.DataFrame, cards: list, cfg: Config = DEFAULT_CONFIG):
    """Build flagged output rows and an annotated metrics table."""
    assistant = DeterministicAIWrapper(NoteRetriever(cards), cfg)
    trigger_label, decision_code, matched, similarity = [], [], [], []
    rows = []
    for r in weekly.itertuples(index=False):
        trig, d = assistant.assess(r.route, r.week_of, r.vs_own_pct, r.vs_peer_pct)
        if not trig.flagged:
            trigger_label.append(""); decision_code.append(""); matched.append(""); similarity.append(float("nan"))
            continue
        trigger_label.append(trig.label); decision_code.append(d.code)
        matched.append(d.note.note_id if d.justified else ""); similarity.append(d.similarity)
        rows.append({
            "route": r.route,
            "week_of": r.week_of.strftime("%Y-%m-%d"),
            "cost_per_tonne_km": fmt_cost(r.cost_per_tonne_km),
            "vs_own_history": fmt_pct(r.vs_own_pct, OWN_SUFFIX, "no prior weeks"),
            "vs_similar_routes": fmt_pct(r.vs_peer_pct, PEER_SUFFIX, "no other routes of this type"),
            "flagged": FLAG_JUSTIFIED if d.justified else FLAG_UNEXPLAINED,
            "matched_note_id": d.note.note_id if d.justified else "",
            "reason": build_reason(d, int(r.hist_weeks_used), cfg.history_weeks, r.vs_own_pct, r.vs_peer_pct),
        })
    annotated = weekly.copy()
    annotated["trigger"] = trigger_label
    annotated["decision_code"] = decision_code
    annotated["matched_note_id"] = matched
    annotated["note_similarity"] = similarity
    return rows, annotated


def run_pipeline(shipments_path, notes_path, sample_path, out_dir, cfg: Config = DEFAULT_CONFIG,
                 strict: bool = False, tracker: UsageTracker | None = None) -> PipelineResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shipments, quality = load_shipments(shipments_path, strict=strict)
    notes_df = load_notes(notes_path)
    cards = build_cards(notes_df, cfg)
    weekly = build_metrics(shipments, cfg)
    rows, annotated = build_findings(weekly, cards, cfg)
    rows.sort(key=lambda r: (r["route"], r["week_of"]))

    out_path = out_dir / "output.csv"
    write_output(rows, out_path)
    errors = validate_output(out_path, sample_path, set(notes_df["note_id"]))
    if errors:
        raise AssertionError("Output violates the contract:\n" + "\n".join(errors[:10]))

    debug_cols = ["route", "route_type", "week_of", "n_shipments", "total_cost_inr", "total_tonne_km",
                  "cost_per_tonne_km", "hist_weeks_used", "own_history_avg", "peer_count", "peer_avg",
                  "vs_own_pct", "vs_peer_pct", "trigger", "decision_code", "matched_note_id", "note_similarity"]
    dbg = annotated[debug_cols].copy()
    dbg["week_of"] = dbg["week_of"].dt.strftime("%Y-%m-%d")
    dbg.round(6).to_csv(out_dir / "weekly_metrics_debug.csv", index=False, lineterminator="\n")

    tracker = tracker or UsageTracker()
    (out_dir / "token_cost_log.json").write_text(
        json.dumps(tracker.to_dict(len(shipments), len(weekly), len(rows)), indent=2) + "\n", encoding="utf-8")
    return PipelineResult(rows, annotated, quality, len(shipments), cards)


def file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
