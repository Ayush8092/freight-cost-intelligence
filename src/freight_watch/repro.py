"""Reproducibility check: run the pipeline N times in SEPARATE processes and compare bytes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .pipeline import file_sha256

COMPARED_FILES = ["output.csv", "weekly_metrics_debug.csv", "token_cost_log.json"]


def run_repro(shipments, notes, sample, runs: int = 3, report_path=None) -> dict:
    results, digests = [], []
    # Make the package importable in the child process even if it was never pip-installed.
    src_dir = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": src_dir + os.pathsep + os.environ.get("PYTHONPATH", "")}
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(1, runs + 1):
            out = Path(tmp) / f"run_{i}"
            cmd = [sys.executable, "-m", "freight_watch", "run", "--shipments", str(shipments),
                   "--notes", str(notes), "--sample", str(sample), "--out-dir", str(out), "--quiet"]
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            if proc.returncode != 0:
                raise RuntimeError(f"run {i} failed:\n{proc.stderr}")
            hashes = {f: file_sha256(out / f) for f in COMPARED_FILES}
            digests.append(hashes)
            results.append({"run": i, "sha256": hashes})
    identical = all(d == digests[0] for d in digests)
    report = {"runs": results, "identical_across_runs": identical,
              "files_compared": COMPARED_FILES,
              "method": "each run is a fresh Python process; files compared by SHA-256 (byte-identical)"}
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
