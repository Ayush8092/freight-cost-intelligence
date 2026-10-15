# Reference submissions: comparison matrix

Reference material only. The official PDF and sample CSV were the source of truth.
All five projects use the **same input data** as the official ZIP (checked by hash, ignoring CRLF line endings).
Directory labels: **tap** = tap_assign.zip, **harshitha** = harshitha_assign.zip, **aiex** = aiex_assign.zip, **sahil** = sahil_assign.zip, **sj** = sj_assign.zip.

## What was actually run (and what was not)

| Project | Commands run | Result |
|---|---|---|
| tap | `python src/metrics_calculator.py`, `src/anomaly_detector.py`, `src/rag_retriever.py` | PASSED (their built-in asserts; the Chroma part of rag_retriever was skipped: no API key) |
| tap | `python main.py run` / `verify` | COULD NOT RUN: `main.py` imports `deepeval` at the top, even for `run`; not installed (dependency gap, not proven code failure) |
| tap | `python src/pipeline.py` (copy in /tmp, no API key -> rule-based fallback) | PASSED: 20 rows; non-reason columns identical to the shipped CSV; its 3-pass determinism check passed |
| tap | tests/ directory | NONE exists; the README's DeepEval 1.00 result was **not attempted** (needs an OpenAI key) |
| harshitha | `python eval/eval_harness.py` | PASSED: 28/28 checks |
| harshitha | `python src/main.py` | PASSED: 728 rows; md5 identical to shipped output and to its repro run_1/2/3 |
| aiex | `python -m unittest discover -s tests -v` | PASSED: 5/5 |
| aiex | `python src/freight_assistant.py ...` | PASSED: 20 rows (works on pandas 3.0 despite its `<3.0` pin) |
| sahil | `python scripts/run_pipeline.py`, `formatcheck.py`, `scripts/verify.py` | PASSED: 19 rows, 0 format errors, "4/4" (but see below: these checks are weak) |
| sahil | `make eval` | Literally prints "Eval harness coming soon..." |
| sj | anything | NOT RUN: needs a ChromaDB server and a local Ollama llama3.2 model. Assessed from source and the shipped CSV only. |

## Matrix

| | tap | harshitha | aiex | sahil | sj |
|---|---|---|---|---|---|
| **Approach** | Python dataclasses; optional LangChain + Chroma + OpenAI | Python pandas + TF-IDF + rule gates | Single-file pandas + TF-IDF | Python package; hand-written JSON "note cards"; TF-IDF | Node/Express + React + ChromaDB + Ollama |
| **Weekly aggregation** | Correct (weighted, verified vs sample) | Correct | Correct | Correct | Numbers correct: all 728 costs match the official formula (checked on the shipped CSV) |
| **Own-history baseline** | Correct | Correct (`shift(1)`+rolling; count shown in text) | Correct | Correct | Correct by code reading (`slice(-8)` of prior weeks) |
| **Peer baseline** | Correct | Correct | Correct | Correct | Correct by code reading |
| **Threshold** | 15% own OR 20% peer | >15% either (no "rising" test for peer) | >=20% either | >15% own spike OR 26-week drift + peer-gap widening >5pp | >20% either (strict) |
| **Note matching** | Route filter, then `if note_id == "N001"` hard-coded dates; others -6..+14 days | Regex window parse; 8-week persistent window; blocklist | Hard-coded per-note windows; `if note_id == "N003": positive = False` | JSON cards written by hand (scope, window, effect, magnitude) | Route + week-start in [note date, note date] only; **never checks what the note says** |
| **Blocks unsupported causes** | Substring blocklist | Substring blocklist | Substring lists | Effect field + magnitude check | **No** |
| **Output schema** | Compliant (8 cols, 20 rows) | Columns OK, but 728 rows with a third verdict `No` | Compliant (20 rows) | Compliant (0 format errors, 19 rows) | **Not compliant**: `flagged` = `1`/blank, raw unrounded floats, no "+x% vs..." text, 728 rows |
| **Tests** | Module `__main__` asserts only | 28-check harness (good) | 5 unittest (thin, real) | `verify.py` post-hoc checks on the CSV; Test 4 only asserts `len>5 and all Yes` | Manual scripts needing live services |
| **Reproducibility** | Own 3-pass check (rule-based path) | md5 of 3 runs identical (re-verified) | SHA-256 report (not re-hashed by me) | No dedicated check | Not demonstrated |
| **Token/cost log** | **Fake**: `len(words)*2` logged as tokens | Honest zero | Honest zero | Zero with a caveat | **Real**: Ollama `prompt_eval_count`/`eval_count` (3 calls) |
| **Dependencies / setup** | Heavy: chromadb, deepeval, langchain, openai, Python 3.12+ | pandas, numpy, sklearn | Same, pins `pandas<3` | Same, pins `pandas==2.1.0` | Node + Chroma server + Ollama |

## Bugs, edge cases, misleading claims found

- **tap**: README says "312 route-weeks"; the data has **728**. N001 dates hard-coded by ID. Token counts are word-count guesses presented as usage. `main.py run` needs `deepeval`. "DeepEval hallucination 1.00" depends on an LLM judge that was not run here.
- **harshitha**: marks **Mumbai-Pune 2025-06-23** `No (justified)` via N003, but that row is +20.6% vs peers and N003 hit all routes 7 weeks earlier. A spot-check would call that fabricated. 728-row output with an invented `No` verdict.
- **aiex**: per-note-ID windows and a special case that makes N003 never justify anything. Reasons for unexplained rows are one boilerplate sentence with no reference to the near-miss notes the sample row mentions.
- **sahil**: README "4/4 tests PASSED" overstates; they check the output file, not behaviour. Justifies **Mumbai-Delhi 2025-05-12** (+11.6%) with N003 (5-7%) using a 5-point tolerance. Pinned old library versions.
- **sj**: output contract violated; no semantic check of note text (a "costs not affected" note in-window would justify); cannot run without two external services.

## What I adopted, improved, or avoided

| Idea | Source | Decision |
|---|---|---|
| Pure pandas core, TF-IDF retrieval, zero LLM, zero keys, honest zero token log | harshitha, aiex | **Adopted** |
| Own-history count surfaced when <8 weeks | harshitha | **Adopted** (shown in `reason`) |
| Structured note card: scope, window, effect, magnitude | sahil | **Adopted, improved**: derived from note text by rules instead of hand-written JSON, so there are no note-ID literals |
| Magnitude gate ("5-7%" cannot explain +11.6%) | sahil | **Adopted, tightened** (2 pp tolerance, not 5) |
| Rising-cost requirement for peer rule; structural peer gap awareness | sahil's README | **Adopted** (simple form) |
| Peer-gap-widening / 26-week drift detector | sahil | **Deferred**: extra complexity; peer rule already catches Mumbai-Pune creep |
| "Closest rejected note" wording in `reason` | harshitha, tap, official sample | **Adopted**, window-aware |
| Real provider token usage logging | sj | **Adopted as design** (`UsageTracker`); unused because no LLM |
| Broad ("All Routes") note cannot explain a peer gap | none (own reasoning, from harshitha's bug) | **New** |
| Hard-coded per-note windows / special cases | tap, aiex | **Avoided** |
| Substring blocklist only | tap, harshitha, aiex | **Improved**: regex with word boundaries (so "slower" is not "lower"), plus structured effect |
| Emitting all weeks with an extra verdict | harshitha, sj | **Avoided** (breaks the contract) |
| ChromaDB / LangChain / OpenAI / DeepEval / Node stack / dashboard | tap, sj | **Rejected**: not justified for 10 notes; adds cost, setup risk and non-determinism |
| Word-count token estimates | tap | **Rejected** as dishonest |

## Ranking (for this assignment)

1. **harshitha**: cleanest honest engineering, real verification, best README reasoning. Loses points on output policy and the N003 justification bug.
2. **sahil**: best *ideas* (note cards, magnitude, peer-gap awareness) but thin verification and weak claims.
3. **aiex**: compliant and correct numbers, but hard-coded rules and thin tests.
4. **tap**: compliant output, but misleading claims, fake token counts, heavy dependencies.
5. **sj**: numbers right, but not contract-compliant, no evidence validation, and unrunnable without services.
