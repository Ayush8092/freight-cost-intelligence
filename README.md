# FreightLens — Freight Cost Anomaly Assistant

FreightLens turns shipment-level freight data and operational context notes into a small, auditable list of unusual weekly route costs. It keeps calculations and verdicts deterministic; retrieval helps find candidate notes, while explicit evidence checks decide whether a note can justify a flagged increase.

## What it delivers

- `outputs/output.csv` — assignment-format findings for candidate route-weeks.
- `outputs/weekly_metrics_debug.csv` — route-week calculations and detector/evidence decisions for review.
- `outputs/token_cost_log.json` — provider usage and cost record for the batch pipeline.
- `reports/reproducibility_report.json` — SHA-256 comparison across separate runs.
- `reports/eval_report.json` — results from the labelled evaluation set.

## Architecture

[FreightWatch Architecture Diagram](architecture_diagram.svg)

The package is split by responsibility: `loader.py` validates inputs, `metrics.py` computes weekly values and baselines, `detector.py` identifies candidates, `retrieval.py` ranks notes, `verdict.py` applies evidence rules, `explain.py` writes reasons, and `wrapper.py` keeps the batch decision path deterministic. `ask.py` reads the finished findings and cannot alter the batch output.

## Calculation rules

### Weekly cost

Shipment dates are grouped into Monday-to-Sunday weeks. `week_of` stores the Monday date. For each origin, destination, route type, and week:

\[
\text{cost per tonne-km} = \frac{\sum \text{freight cost INR}}{\sum (\text{quantity tonnes} \times \text{distance km})}
\]

This is a weighted ratio, not the average of per-shipment ratios.

### Own-history comparison

The current route-week is compared with the mean of its previous **up to eight observed route-weeks**. The current week is excluded. If fewer than eight prior weeks exist, the available weeks are used; missing weeks are not fabricated. The first observed week has no own-history baseline.

### Similar-route comparison

The current cost is compared with the mean for other routes of the same `route_type` in the same week. The current route is excluded. If no peer exists, the comparison is unavailable.

Percent difference is `(current - baseline) / baseline × 100`. Missing, zero, or invalid baselines are reported as unavailable rather than producing infinite values.

### Candidate thresholds

The assignment specifies the baselines but not numeric flag thresholds. FreightLens documents these implementation choices in `src/freight_watch/config.py`:

- own-history rise: at least **10%**;
- peer premium: at least **20%**, with a positive own-history change when that baseline exists;
- note magnitude tolerance: **2 percentage points**.

These are project assumptions, not official FreightTiger thresholds. Only candidate weeks are emitted in the assignment CSV; the debug file contains all computed route-weeks.

## Retrieval and evidence grounding

`retrieval.py` uses local TF-IDF text similarity to rank context notes. It requires no embedding service, vector database, API key, or network access. The query includes route, week, and comparison context to improve candidate ordering.

A high similarity score is **not** evidence that a note explains an increase. Before `matched_note_id` can be set, `verdict.py` checks:

1. **Route scope** — the note applies to the affected route or is explicitly global.
2. **Effect** — the note describes rising costs; notes about improved conditions, unaffected costs, or no rate change are rejected.
3. **Time window** — the note's effective dates overlap the Monday-to-Sunday week.
4. **Peer context** — a broad cost increase cannot explain why one route is unusually expensive relative to peers.
5. **Magnitude** — when a note quantifies an increase, the observed rise must be within the configured tolerance.

If no note passes every check, the finding remains unexplained (`Yes`) and its `matched_note_id` is blank. The reason can mention rejected nearby notes, but it does not treat them as justification. Reasons are generated from computed metrics and validated note fields; the batch pipeline does not ask an LLM to invent causes.

## Plain-English Q&A

The default `ask` command answers from the generated findings only. It supports route, month, and year filters and can be used interactively:

```bash
python -m freight_watch ask
python -m freight_watch ask "Why did Chennai-Bangalore get pricier in March 2025?"
```

For optional Groq-powered phrasing, create `.env` in the project root and set `GROQ_API_KEY`. Install the optional packages with `pip install -r requirements-groq.txt`, then run:

```bash
python -m freight_watch ask --groq "Why did Chennai-Bangalore get pricier in March 2025?"
```

The Groq layer receives only matching finding rows and is instructed not to infer unsupported causes. It is outside the batch pipeline. `temperature=0` reduces sampling variation but does not guarantee identical model responses; the deterministic batch output does not depend on Groq.

## Reproducibility and usage tracking

The batch path uses stable sorting, local retrieval, rule-based evidence checks, and templated explanations. It makes no LLM calls. `python -m freight_watch repro` launches separate Python processes and compares SHA-256 hashes for `output.csv`, `weekly_metrics_debug.csv`, and `token_cost_log.json`. Run this command to refresh the report for the current code and environment; reproducibility should be reported from that run, not assumed from a temperature setting.

`outputs/token_cost_log.json` records zero model calls, zero input/output tokens, and `$0` model cost for the batch run. These are actual zeros because no provider is called. Optional Groq Q&A writes provider-reported token counts to `outputs/ask_token_cost_log.json`; its cost is left unestimated rather than inventing a rate. Local CPU time and package installation are not included.

## Setup

Python 3.10 or newer is required. From the `freightlens` directory:

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
pip install -r requirements-dev.txt
python -m pytest -q
python -m freight_watch run
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
pip install -r requirements-dev.txt
python -m pytest -q
python -m freight_watch run
```

The run command writes files to `outputs/`. Useful audit commands:

```bash
python -m freight_watch eval
python -m freight_watch repro
python -m freight_watch ask "Why did Chennai-Bangalore get pricier in March 2025?"
```

To fail on any invalid shipment row instead of quarantining it, add `--strict`. To choose another output directory, use `python -m freight_watch run --out-dir path/to/output`.

## Project layout

```text
data/                  assignment input CSVs
src/freight_watch/     loader, metrics, detector, retrieval, evidence gate, explanations, CLI
tests/                 unit and integration tests
eval/golden_set.csv    labelled evaluation cases
outputs/               generated CSVs and usage logs
reports/               evaluation and reproducibility reports
docs/                  case study, specification, walkthrough, reference comparison
.env.example           optional Groq configuration template
```

## Scope and limitations

- The batch decision thresholds are documented assumptions because the brief does not prescribe numeric thresholds.
- Note scope, effects, and effective dates are extracted with deterministic rules suited to the supplied note format. Ambiguous notes fail closed and should be reviewed.
- TF-IDF is a lightweight text-retrieval method, not a hosted embedding model. For this small note set it keeps the run offline, cheap, and reproducible.
- Groq is optional and used only for interactive phrasing. It is not needed to generate the required CSV or run the tests.
