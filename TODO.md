# Fix List — FAIR CSV Mentor

Generated from code review on 2026-05-02.

## Roadmap — Column Understanding (Small + Fast)

Goal: improve automatic column/data understanding while keeping latency and complexity low.

### Stage 0 — Baseline and acceptance gates (no model)
- [ ] Create a repeatable benchmark from `test_data/*.csv` using expected mappings for key roles:
	- identifier, treatment/group, outcome, covariate, date/time, metadata/provenance
- [ ] Add a script/report that prints precision/recall and per-column confidence distribution
- [ ] Define release gate for "good enough without LLM":
	- >= 0.85 precision on key roles
	- >= 0.80 recall on key roles
	- <= 5% columns flagged "ambiguous" in known templates

### Stage 1 — Heuristic uplift (deterministic)
- [ ] Expand synonym dictionaries for life-science terms:
	- ALT/AST variants, dose/unit aliases, control/group labels, sex/strain/age forms
- [ ] Add value-shape validators:
	- ID regexes, date parsing, numeric+unit coupling, categorical cardinality checks
- [ ] Emit `inferred_role` + `confidence` + `reason_codes` per column
- [ ] Add unit tests covering all current CSV examples in `test_data/`

### Stage 2 — User-in-the-loop disambiguation (still no LLM)
- [ ] Add low-confidence prompts in wizard/chat:
	- ask only for columns below threshold (e.g., confidence < 0.65)
- [ ] Save confirmed mappings as reusable templates by dataset profile/signature
- [ ] Re-apply templates automatically on upload before running advanced logic
- [ ] Track correction rate and time-to-confirm metrics

### Stage 3 — Lightweight semantic layer (optional, non-LLM)
- [ ] Add optional embedding match against curated label bank/ontology aliases
- [ ] Use this only for unresolved columns after Stage 1+2
- [ ] Keep strict latency budget (e.g., < 200 ms per 100 columns on warm cache)
- [ ] Add fallback to deterministic heuristics if semantic layer unavailable

### Stage 4 — LLM assist (gated rollout)
- [ ] Add LLM path behind feature flag and only for hard/ambiguous cases
- [ ] Restrict LLM output to structured JSON schema (role, confidence, rationale)
- [ ] Log disagreement between heuristic and LLM predictions for audit
- [ ] Add timeout + safe fallback to non-LLM path

### When LLM becomes critical
- [ ] Treat LLM as critical only when all are true for >= 2 iterations:
	- Stage 1-3 plateau below target (cannot reach >= 0.90 precision and >= 0.85 recall)
	- Ambiguity remains > 10% on newly ingested partner datasets
	- Manual correction burden stays high (> 2-3 clarifications per dataset)
	- New schema diversity outpaces rule/template maintenance capacity

### Recommended implementation order
- [ ] First implement Stage 0 and Stage 1 (highest ROI, lowest risk)
- [ ] Then Stage 2 template memory (largest UX gain)
- [ ] Add Stage 3 only if ambiguity remains materially high
- [ ] Add Stage 4 (LLM) last, as selective escalation rather than default path

## Backend

### Critical bugs
- [x] `vcg/agents/vcg_bootstrap.py:80` — Zero-variance columns produce NaN in Spearman matrix → degenerate copula; fall back to identity for those columns
- [x] `vcg/agents/standardization_agent.py:94` — `mode().iloc[0]` throws IndexError on all-NaN categorical column; guard with `len(m) > 0`
- [x] `main.py:95` — `_load_session` silently returns None on exception; add logging before returning
- [x] `vcg/vcg_engine.py:52` — Misleading error when control group is empty due to type mismatch (int vs string); coerce `control_value` type before filtering

### Error handling
- [x] `vcg/agents/stats_agent.py:71` — Replace `if p == p` NaN check with `not np.isnan(p)`
- [x] `uri_suggester.py` — Validate `base_uri` before using it in URI construction
- [x] `export_engine.py:30` — Deduplicate normalised column names to prevent silent collisions
- [x] `standardization_agent.py:84` — Document the 50% threshold for numeric vs categorical imputation decision

### Design / duplication
- [x] `csv_profiler.py` + `vcg/vcg_wizard.py` — Extract shared `IDENTIFIER_PATTERNS` and control-value keywords to `vcg/constants.py`
- [x] `vcg/orchestrator.py` — Add `_parse_yes_no()` helper to consolidate free-text parsing across all 8 state handlers
- [x] `context_model.py` — Replace manual `dict_to_*` conversion functions with `dataclasses.asdict()` / `dataclasses.replace()`
- [x] `fair_engine.py` — Extract inline `has()` helper to module level so individual criteria can be unit-tested

### Performance
- [x] `main.py` (`_prepare_exports`) — `compute_fair_score()` and `suggest_uris()` recomputed on every export call; memoize against session state

## Frontend

### Bugs
- [x] `VCGWizardPage.tsx:273` — When `bioColumns.length === 0`, all columns shown instead of empty state (inverted condition)
- [x] `VCGResultsPage.tsx:81` — Polling calls API without guarding `datasetId === null`; add early return
- [x] `VCGPage.tsx:50` — `addChatMessage`/`setVCGStatus` missing from `useEffect` dependency array; causes stale closures
- [x] `FAIRScorePage.tsx:44` — `load` missing from effect dependency array
- [x] `MetadataWizardPage.tsx:99` — Remove `setFairScore(null as never)` cast; use proper `FAIRScore | null` union

### Missing states / UX
- [x] `ExportPage.tsx:110` — Replace `alert()` on export failure with MUI `Snackbar`/`Alert`
- [x] `OverviewPage.tsx` — Add null guard before `.map()` on `tableStructure.detected_*` arrays
- [x] `MetadataWizardPage.tsx:80` — Surface error to user when `getMetadata()` fails
- [x] `CovariateBalanceTable.tsx:45` — Render `"—"` instead of `"Infinity"` / `"NaN"` for non-finite SMD values

### Type safety
- [x] `Layout.tsx:92` — Replace `(item as any).vcgItem` with a typed optional field on the nav item interface
- [x] `useStore.ts` — Clear `base_uri` default on `reset()` so it doesn't persist across uploads

### Accessibility
- [x] `ChatInterface.tsx:150` — Add `aria-label="Message input"` to the message TextField
- [x] `ColumnProfilePage.tsx:309` — Improve Snackbar accessibility (longer duration or persistent until dismissed)
