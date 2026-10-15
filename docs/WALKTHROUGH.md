# 10-minute walkthrough script

Goal: show you understand it. Say "my assumption" for the thresholds. Never say "the brief requires" for them.

## 0:00-1:00  The problem and the one-sentence answer
"Transport cost per tonne-km can creep up for real reasons or for none. My assistant computes weekly cost per route, flags
unusual rises, and explains a flag only when a note genuinely supports it. If not, it says 'unexplained'. It uses no LLM, and gives the same output every run."

## 1:00-3:00  The numbers (open `metrics.py`)
- Weekly cost = total cost / total (tonnes x km). Weighted, because a 22-tonne load should count more than a 5-tonne one.
- Own-history baseline = mean of the previous 8 *observed* weeks, current week excluded. Peer baseline = other routes of the same type, same week.
- Proof: "the official sample gives +35.5/+21.0, +29.5/+22.5, +9.2/+23.6. My code reproduces all three exactly."

## 3:00-4:30  When to flag (open `config.py`, `detector.py`)
- "The brief gives no threshold, so I chose 10% vs own history, or 20% vs peers *while rising*. These are my assumptions."
- Why 20% for peers: Mumbai-Pune is always ~12% dearer than its only peer. 20% sits above that. Without "rising", it would be flagged forever.
- 20 of 728 route-weeks flagged.

## 4:30-7:00  The trust part (open `notes.py`, `verdict.py`)
Walk the gate: scope -> effect -> window -> breadth -> magnitude. Use three live examples from `outputs/output.csv`:
1. **Chennai-Bangalore 03-03 vs 03-10**: same flood, but N001's window ends Mar 8, so 03-03 is justified and 03-10 is not. Show N009 says "back to normal".
2. **Mumbai-Delhi 05-12**: diesel note says 5-7%, the week is +11.6%, so only partly explained -> stays `Yes`.
3. **Mumbai-Pune 06-23**: a note about *all* routes cannot explain being dearer than *peers*. (One reference submission got this wrong.)
Say: "TF-IDF only orders notes. It can't justify anything. With 10 notes, a vector DB would add complexity and no correctness."

## 7:00-8:30  How I know it's right
- 69 tests; show one synthetic edge-case test and the mutation check (broke the code 6 ways, suite caught all 6).
- `python -m freight_watch eval`: 17 labelled cases. Be candid: cases 1-8 come from the official sample/brief/notes; 9-12 are my judgement.
- `python -m freight_watch repro`: three separate processes, identical SHA-256.

## 8:30-9:30  Cost and honesty
- LLM calls 0, tokens 0, cost $0, and why. If an LLM were added it would only phrase validated results; counts would come from provider metadata.
- I studied five other submissions, verified instead of trusting READMEs; one logs word-count guesses as tokens; one's output breaks the format.

## 9:30-10:00  Limits
Thresholds are assumptions; rule-based note parsing fits this note style; no dedicated creep detector.

## Likely questions (prepare answers in your own words)
1. *Why is Mumbai-Pune 2025-11-10 not flagged though +21% vs peers?* Not rising (-0.1% vs own history). One-line change if wanted (`detector.py`).
2. *Why 8 weeks?* It's the brief's definition, not my choice.
3. *Why not an LLM for explanations?* Reproducibility and hallucination risk; templates quote the note verbatim.
4. *How would you scale to 10,000 notes?* Embedding retrieval (local sentence-transformers) for ranking; the gate stays identical.
5. *What if a note's wording is unusual?* Ambiguity resolves to "no effect" -> unexplained (safe side). An LLM extractor could fill the card, but its output must pass the same gate.
6. *Why is the peer average a simple mean?* The brief says "average cost per tonne-km across other routes"; it reproduces the sample values exactly.
7. *What does `hist_weeks_used` do?* Records how many prior weeks formed the baseline; <8 is mentioned in `reason`.
8. *What is the weakest part?* The threshold choice and the golden cases that are my own judgement.
