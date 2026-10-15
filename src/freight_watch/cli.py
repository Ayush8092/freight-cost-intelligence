"""Command line: run | eval | repro | ask."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .errors import FreightWatchError


def _root() -> Path:
    # src/freight_watch/cli.py -> project root is two levels up from src
    return Path(__file__).resolve().parents[2]


def _paths(args) -> dict:
    r = _root()
    return {
        "shipments": args.shipments or r / "data" / "shipment_records.csv",
        "notes": args.notes or r / "data" / "context_notes.csv",
        "sample": args.sample or r / "data" / "sample_output_format_v2.csv",
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="freight_watch", description="Freight cost anomaly assistant")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--shipments"); sp.add_argument("--notes"); sp.add_argument("--sample")

    run = sub.add_parser("run", help="run the pipeline and write output.csv"); common(run)
    run.add_argument("--out-dir"); run.add_argument("--strict", action="store_true",
                                                     help="fail on any invalid shipment row instead of quarantining it")
    run.add_argument("--quiet", action="store_true")
    ev = sub.add_parser("eval", help="score the pipeline against the labelled golden set"); common(ev)
    ev.add_argument("--golden"); ev.add_argument("--report")
    rp = sub.add_parser("repro", help="run 3 times in separate processes and compare"); common(rp)
    rp.add_argument("--runs", type=int, default=3); rp.add_argument("--report")
    ask = sub.add_parser("ask", help="ask a plain-English question about the findings"); common(ask)
    ask.add_argument("question", nargs="?")
    ask.add_argument("--groq", action="store_true", help="use Groq to phrase an answer from matched findings")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = _root()
    paths = _paths(args)
    try:
        if args.command == "run":
            from .pipeline import run_pipeline
            out_dir = Path(args.out_dir) if args.out_dir else root / "outputs"
            res = run_pipeline(paths["shipments"], paths["notes"], paths["sample"], out_dir, strict=args.strict)
            if not args.quiet:
                n_yes = sum(r["flagged"] == "Yes" for r in res.output_rows)
                print(f"Shipments used: {res.quality.rows_used}/{res.quality.rows_read} "
                      f"(quarantined {res.quality.rows_quarantined}, duplicates removed {res.quality.duplicates_removed})")
                print(f"Route-weeks computed: {len(res.weekly)}")
                print(f"Rows written: {len(res.output_rows)}  (Yes: {n_yes}, No (justified): {len(res.output_rows) - n_yes})")
                print(f"Output: {out_dir / 'output.csv'}  | LLM calls: 0, tokens: 0")
            return 0
        if args.command == "eval":
            from .evalharness import run_eval
            report_path = args.report or root / "reports" / "eval_report.json"
            rep = run_eval(paths["shipments"], paths["notes"], paths["sample"],
                           args.golden or root / "eval" / "golden_set.csv", report_path)
            return 0 if rep["all_passed"] else 1
        if args.command == "repro":
            from .repro import run_repro
            rep = run_repro(paths["shipments"], paths["notes"], paths["sample"], args.runs,
                            args.report or root / "reports" / "reproducibility_report.json")
            for r in rep["runs"]:
                print(f"run {r['run']}: output.csv sha256 {r['sha256']['output.csv'][:16]}...")
            print("IDENTICAL across runs" if rep["identical_across_runs"] else "MISMATCH across runs")
            return 0 if rep["identical_across_runs"] else 1
        if args.command == "ask":
            from .ask import answer, answer_with_groq
            from .pipeline import run_pipeline
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                run_pipeline(paths["shipments"], paths["notes"], paths["sample"], tmp)
                findings = pd.read_csv(Path(tmp) / "output.csv", dtype=str, keep_default_na=False)
            if args.question:
                questions = [args.question]
            else:
                print("Ask about a route, month, or year. Type 'exit' to quit.")
                questions = None
            while True:
                question = questions.pop(0) if questions else input("You: ").strip()
                if not question or question.casefold() in {"exit", "quit"}:
                    break
                try:
                    if args.groq:
                        response, usage = answer_with_groq(question, findings)
                        if usage["llm_calls"]:
                            usage_path = _root() / "outputs" / "ask_token_cost_log.json"
                            usage_path.parent.mkdir(parents=True, exist_ok=True)
                            usage_path.write_text(json.dumps(usage, indent=2) + "\n", encoding="utf-8")
                    else:
                        response = answer(question, findings)
                    print(response)
                except RuntimeError as exc:
                    print(f"ERROR: {exc}", file=sys.stderr)
                    return 2
                if questions is not None:
                    break
            return 0
    except FreightWatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
