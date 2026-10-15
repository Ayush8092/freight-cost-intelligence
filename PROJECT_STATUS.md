# FreightLens — project status

Last verified: 2026-10-15.

## Current implementation

`loader` -> `metrics` -> `detector` -> `retrieval` -> `wrapper` / `verdict` -> `explain` -> `output`.
The batch path uses local TF-IDF retrieval, rule-based evidence validation, and deterministic reason templates. `ask.py` supports local findings queries and optional Groq phrasing. Groq is not required for the official CSV or test suite.

## Verification

| Check | Latest result |
|---|---|
| `python -m pytest -q` | 72 passed |
| `python -m freight_watch eval` | 17/17 golden cases; 3 justified rows spot-checked |
| `python -m freight_watch repro` | 3 separate processes; output, debug CSV, and token log hashes identical |
| `python -m freight_watch run` | 2,940 shipments, 728 route-weeks, 20 candidate rows; 17 unexplained and 3 justified |
| Batch LLM usage | 0 calls, 0 tokens, $0 model cost |

The latest reproducibility hashes are recorded in `reports/reproducibility_report.json`. The local verification was run in this environment; Windows execution has not been independently verified.

## Design decisions

- Weekly cost is `sum(freight_cost_inr) / sum(quantity_tonnes * distance_km)`.
- Own-history baseline uses the previous up to eight observed weeks and excludes the current week.
- Peer baseline uses other routes of the same route type in the same week.
- Thresholds (10% own history, 20% peer premium, 2 percentage-point magnitude tolerance) are documented project choices; the assignment does not prescribe numeric thresholds.
- Similarity ranks notes only. Route scope, effect, effective window, peer context, and magnitude must pass the evidence gate before a note can justify an increase.
- Groq Q&A is optional and does not affect batch outputs. Temperature zero is not treated as a guarantee of model determinism.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install -r requirements-dev.txt
python -m pytest -q
python -m freight_watch run
python -m freight_watch eval
python -m freight_watch repro
```

For optional Groq Q&A, install `requirements-groq.txt`, then add `GROQ_API_KEY` to `.env`. Do not commit a real API key.
