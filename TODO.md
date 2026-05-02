# Fix List — FAIR CSV Mentor

Generated from code review on 2026-05-02.

## Backend

### Critical bugs
- [ ] `vcg/agents/vcg_bootstrap.py:80` — Zero-variance columns produce NaN in Spearman matrix → degenerate copula; fall back to identity for those columns
- [ ] `vcg/agents/standardization_agent.py:94` — `mode().iloc[0]` throws IndexError on all-NaN categorical column; guard with `len(m) > 0`
- [ ] `main.py:95` — `_load_session` silently returns None on exception; add logging before returning
- [ ] `vcg/vcg_engine.py:52` — Misleading error when control group is empty due to type mismatch (int vs string); coerce `control_value` type before filtering

### Error handling
- [ ] `vcg/agents/stats_agent.py:71` — Replace `if p == p` NaN check with `not np.isnan(p)`
- [ ] `uri_suggester.py` — Validate `base_uri` before using it in URI construction
- [ ] `export_engine.py:30` — Deduplicate normalised column names to prevent silent collisions
- [ ] `standardization_agent.py:84` — Document the 50% threshold for numeric vs categorical imputation decision

### Design / duplication
- [ ] `csv_profiler.py` + `vcg/vcg_wizard.py` — Extract shared `IDENTIFIER_PATTERNS` and control-value keywords to `vcg/constants.py`
- [ ] `vcg/orchestrator.py` — Add `_parse_yes_no()` helper to consolidate free-text parsing across all 8 state handlers
- [ ] `context_model.py` — Replace manual `dict_to_*` conversion functions with `dataclasses.asdict()` / `dataclasses.replace()`
- [ ] `fair_engine.py` — Extract inline `has()` helper to module level so individual criteria can be unit-tested

### Performance
- [ ] `main.py` (`_prepare_exports`) — `compute_fair_score()` and `suggest_uris()` recomputed on every export call; memoize against session state

## Frontend

### Bugs
- [ ] `VCGWizardPage.tsx:273` — When `bioColumns.length === 0`, all columns shown instead of empty state (inverted condition)
- [ ] `VCGResultsPage.tsx:81` — Polling calls API without guarding `datasetId === null`; add early return
- [ ] `VCGPage.tsx:50` — `addChatMessage`/`setVCGStatus` missing from `useEffect` dependency array; causes stale closures
- [ ] `FAIRScorePage.tsx:44` — `load` missing from effect dependency array
- [ ] `MetadataWizardPage.tsx:99` — Remove `setFairScore(null as never)` cast; use proper `FAIRScore | null` union

### Missing states / UX
- [ ] `ExportPage.tsx:110` — Replace `alert()` on export failure with MUI `Snackbar`/`Alert`
- [ ] `OverviewPage.tsx` — Add null guard before `.map()` on `tableStructure.detected_*` arrays
- [ ] `MetadataWizardPage.tsx:80` — Surface error to user when `getMetadata()` fails
- [ ] `CovariateBalanceTable.tsx:45` — Render `"—"` instead of `"Infinity"` / `"NaN"` for non-finite SMD values

### Type safety
- [ ] `Layout.tsx:92` — Replace `(item as any).vcgItem` with a typed optional field on the nav item interface
- [ ] `useStore.ts` — Clear `base_uri` default on `reset()` so it doesn't persist across uploads

### Accessibility
- [ ] `ChatInterface.tsx:150` — Add `aria-label="Message input"` to the message TextField
- [ ] `ColumnProfilePage.tsx:309` — Improve Snackbar accessibility (longer duration or persistent until dismissed)
