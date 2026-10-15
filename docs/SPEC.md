# Exact specification, mapped to modules and tests

Source of truth: `FreightTiger_Intern_CaseStudy.pdf` and `sample_output_format_v2.csv`.
Verified input files and columns:

| File | Columns | Size |
|---|---|---|
| `shipment_records.csv` | shipment_id, origin, destination, route_type, material, quantity_tonnes, distance_km, freight_cost_inr, shipment_date, transporter | 2,940 rows, 7 routes, 104 Mondays (2024-01-01 to 2025-12-22), no gaps, no nulls, no duplicate ids |
| `context_notes.csv` | note_id, date, applies_to, note | 10 notes (N001-N010) |
| `sample_output_format_v2.csv` | route, week_of, cost_per_tonne_km, vs_own_history, vs_similar_routes, flagged, matched_note_id, reason | 3 example rows |

Each route has exactly one `route_type`. Short has 2 routes, Medium 3, Long 2, so a route has only 1-2 peers.

## Requirements checklist

| # | Requirement (source) | Module | Tests (tests/) | Status |
|---|---|---|---|---|
| R1 | Group by route (origin+destination) and given `route_type` (PDF) | metrics.weekly_costs | test_route_type_is_part_of_the_group | done |
| R2 | Monday-Sunday weeks; `week_of` = Monday (PDF) | loader.monday_of | test_monday_based_week (5 cases), test_sunday_and_next_monday_are_different_weeks | done |
| R3 | cost/tonne-km = sum(cost) / sum(t x km), weighted (PDF) | metrics.weekly_costs | test_cost_is_weighted_not_mean_of_ratios, test_multiple_shipments_in_one_route_week_are_aggregated | done |
| R4 | Own history = trailing 8 weeks strictly before; <8 uses all, say so in README (PDF) | metrics.add_history_baseline | test_history_excludes_current_week_and_uses_exactly_eight, test_fewer_than_eight_prior_weeks_uses_all_available, test_no_history_for_first_week, test_missing_weeks_are_not_fabricated | done |
| R5 | Peer = same week, same route_type, other routes only (PDF) | metrics.add_peer_baseline | test_peer_baseline_excludes_the_route_itself, test_no_eligible_peers_gives_nan, test_peers_must_share_route_type, test_peers_compared_in_the_same_week_only | done |
| R6 | % diff = (cur - base)/base x 100; handle bad denominators | metrics.pct_diff | test_pct_diff_formula_and_unavailable_baselines, test_zero_tonne_km_gives_nan_not_inf | done |
| R7 | Flag rising cost that is out of the ordinary vs own history or peers (PDF) | detector.evaluate | test_detector.py (7 tests) | done; thresholds are OUR choice |
| R8 | Check notes before flagging; justified verdict must cite a note that applies to that route AND time (PDF) | notes, retrieval, verdict | test_notes_and_verdict.py (23 tests) | done |
| R9 | Wrong route / wrong window / "costs not affected" does not count (PDF) | verdict.judge | test_route_mismatched..., test_note_outside_its_window..., test_cost_unaffected..., test_no_rate_change..., test_improved... | done |
| R10 | No supporting note -> unexplained, never guess (PDF) | verdict.decide | test_similarity_alone_never_justifies, test_no_nearby_note, test_unexplained_decision_has_no_note... | done |
| R11 | Explanation grounded in the note, dates reflected; id in matched_note_id, blank if unexplained (PDF) | explain, output | test_justified_rows_cite_the_note..., test_verdict_conventions | done |
| R12 | Output CSV matches sample columns/order/types exactly (PDF) | output.validate_output | test_columns_and_order_match..., test_output_validates_against_contract, test_validator_catches_violations, test_official_sample_rows_reproduced_exactly | done |
| R13 | Eval harness / labelled set (PDF) | evalharness + eval/golden_set.csv | `python -m freight_watch eval` | done |
| R14 | 3 identical runs (PDF) | repro | test_three_separate_process_runs_identical, test_two_in_process_runs_are_byte_identical | done |
| R15 | Token/cost log for one run: input, output, calls, cost (PDF) | usage | test_token_log_is_honest_zero | done (all zero, explained) |
| R16 | README, 10-min walkthrough (PDF) | README.md, docs/WALKTHROUGH.md | n/a | done |
| R17 | Stretch: plain-English Q&A using own results (PDF) | ask | test_ask_answers_from_findings_only | done (simple) |
| R18 | Bonus: vector DB / RAG (PDF "great place to use") | retrieval | test_retrieval_order_is_stable | done, local TF-IDF; a vector DB is not justified for 10 notes |

## Output policy decision

The PDF does not say whether to emit every week or only flagged ones. The sample has 3 rows, all with `Yes` or `No (justified)`;
a "normal" week has no verdict in that vocabulary. Decision: emit only candidate rows; keep all rows in the debug file. Test: test_normal_weeks_are_not_emitted.

## Unresolved ambiguities (decisions taken; revisit if HR clarifies)

1. **Anomaly threshold**: not in the brief. 10% own / 20% peer, documented in `config.py`.
2. **Partial explanation**: `Yes`, blank `matched_note_id`, note named in `reason`. Alternative: cite the note with `No (justified)`. I chose the stricter reading because "a confident wrong reason scores worse than couldn't find one".
3. **Peer-only rows with no own rise** (e.g. Mumbai-Pune 2025-11-10): not flagged, because the brief says "cost is rising".
4. **Window of a note with no stated dates**: the note's own Monday-Sunday week (festival-week style); step-change notes ("starting this week"): note week + 8 weeks.
5. **"Closest note" in the reason for unexplained rows**: wording only, within 28 days; never used to justify.
6. **Peer average is a simple mean of other routes' weekly ratios** (not tonne-km pooled). Verified by reproducing the sample's +21.0 / +22.5 / +23.6 exactly.
7. **Official sample CSV has an unquoted comma** in row 3's reason; our file is properly quoted.
