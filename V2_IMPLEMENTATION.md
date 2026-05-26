# V2 Implementation Tracker

Branch: `v2-local-llm-hitl-planning`

## Coordination

- [x] Create v2 planning branch
- [x] Add v2 roadmap to `TODO.md`
- [x] Start specialized subagents
  - [x] Worker A: backend LLM provider abstraction
  - [x] Worker B: backend study corpus foundation
  - [x] Worker C: backend scientific HITL loop
  - [x] Explorer D: frontend integration map
- [x] Integrate worker changes
- [x] Run backend tests
- [x] Run frontend type-check

## LLM Provider Layer

- [x] Add provider-neutral LLM interface
- [x] Add Anthropic adapter preserving current Haiku behavior
- [x] Add OpenAI-compatible adapter for Ollama/OpenAI-compatible endpoints
- [x] Add provider factory and healthcheck
- [x] Add provider status endpoint
- [x] Add local-provider PDF text extraction path for paper import
- [x] Add tests with mocked providers

## Multi-Paper Corpus

- [x] Add `StudyCorpus` session model
- [x] Add formal `ProjectSchema` contract for consensus schemas
- [x] Normalize legacy/simple field drafts into project-schema shape
- [x] Validate VCG role references against declared columns
- [x] Add paper source lifecycle
- [x] Add article-schema candidate storage with evidence spans
- [x] Add consensus schema, conflicts, expert decisions, and schema versions
- [x] Add corpus API routes
- [x] Add project-schema validation API route
- [x] Persist corpus in existing SQLite session JSON
- [x] Add corpus tests

## Scientific HITL Loop

- [x] Add v2 schema/HITL categories
- [x] Add payload validation for schema and VCG-assumption suggestions
- [x] Add confidence semantics: `auto_accept`, `needs_review`, `must_ask`, `reject`
- [x] Add question ranking helper
- [x] Add agent-loop stopping rules
- [x] Add HITL tests

## Frontend / UX

- [x] Extend API client types and methods for corpus routes
- [x] Add Study Corpus page
- [x] Add route and nav entry
- [x] Add evidence-backed schema review surface
- [x] Add model/provider status surface
- [x] Add schema approval workflow

## VCG Readiness

- [ ] Connect consensus schema to column profiling
- [ ] Connect consensus schema to template suggestions
- [x] Define normalized VCG role contract for downstream wizard defaults
- [x] Connect consensus schema to VCG wizard defaults
- [x] Add FAIR-to-VCG readiness consequences
- [x] Add deterministic VCG readiness API/helper
- [ ] Add reviewer/ethics committee report export

## Validation

- [x] Add provider contract tests
- [x] Add project-schema contract tests
- [x] Add multi-paper/project-schema fixtures
- [x] Add hallucinated role-reference regression tests
- [ ] Add invalid-unit conflict diagnostics
- [ ] Add local-model benchmark plan/fixture
- [ ] Compare Qwen3-14B, Qwen3-8B, Llama 3.1 8B, and opt-in cloud models

## Verification Log

- [x] `python -m py_compile backend\llm_providers.py backend\llm_service.py backend\study_corpus.py backend\corpus_router.py backend\schema_agent_loop.py backend\hitl.py backend\llm_fair_scorer.py backend\paper_extractor.py backend\project_schema.py backend\vcg\llm_orchestrator.py`
- [x] Focused backend tests: `37 passed`
- [x] Frontend type-check: `npm run type-check` passed
