# Project knowledge base (commit wiki)

A versioned, regenerable record of **what** changed in this repo over time and, where it
matters, **how and why** — so anyone can look back at a feature, merge, or PR months later
and understand the reasoning, not just the diff.

## What's here

| File | Generated? | Purpose |
|------|------------|---------|
| [`commit-ledger.md`](commit-ledger.md) | ✅ auto | Every commit, newest first: hash, date, author, scope, files changed, message body, and any curated Why/How/Impact note. |
| [`by-scope.md`](by-scope.md) | ✅ auto | The same commits grouped by `scope:` prefix (`vcg`, `frontend`, `templates`, `eval`, …) — a topic index. |
| [`prs.md`](prs.md) | ✅ auto | Merge & PR timeline (PR number, source branch, date). |
| [`annotations.yaml`](annotations.yaml) | ✍️ **hand-written** | Curated Why/How/Impact/Tags keyed by commit hash. The only file you edit by hand. |
| `index.md` | ✍️ hand-written | This guide. |

> The three `.md` ledgers carry an `AUTO-GENERATED` header and are overwritten on every run.
> **Never edit them by hand** — your notes go in `annotations.yaml`, which the generator
> merges in but never overwrites. This is what makes regeneration safe and the history durable.

## How it works

`scripts/gen_wiki.py` reads the full `git log` of the current branch, parses each commit
(scope from the `<scope>:` prefix, PR number from merge subjects, file counts from
`--numstat`, trailers stripped), merges any curated notes from `annotations.yaml`, and
writes the three ledgers. Because it regenerates from the entire history, the ledger always
reflects every commit — there is no incremental state to drift.

## Maintaining it — the routine

After each meaningful merge or PR (and before you forget the context):

```bash
# 1. Regenerate the ledgers from the current branch
python scripts/gen_wiki.py

# 2. (optional) Add a curated note for any commit worth explaining.
#    Edit docs/wiki/annotations.yaml, keyed by the short hash:
#
#    abc1234:
#      why:    Why this change was needed.
#      how:    How it was done (approach, key files).
#      impact: What it unblocks / changes downstream.
#      tags:   [grant, vcg, frontend]
#
# 3. Re-run so the note lands in the ledger, then commit both:
python scripts/gen_wiki.py
git add docs/wiki scripts/gen_wiki.py
git commit -m "docs: refresh commit knowledge base"
```

### LLM-assisted drafting (optional, "wiki style")

To draft Why/How/Impact for commits that don't have a note yet, using the repo's **own**
provider-agnostic LLM layer (Anthropic *or* a local LM-Studio model — no separate dependency):

```bash
python scripts/gen_wiki.py --llm
```

It writes drafts into `annotations.yaml` flagged `draft: true` for you to review, edit, and
un-flag. It degrades gracefully (prints a notice and still generates the deterministic
ledger) when no model is configured. Running it against a **local** model keeps the whole
knowledge-base workflow offline — consistent with the grant's no-external-API goal.

## Conventions that make this work

- **Commit messages** follow `<scope>: <imperative summary>` with an optional body that
  explains *why, not what* (see `CLAUDE.md`). The richer the body, the less curation needed.
- **Scopes** seen so far: `vcg`, `vcg-agents`, `vcg-chat`, `templates`, `eval`, `knowledge`,
  `frontend`, `backend`, `api`, `scoring`, `profiler`, `tests`, `docs`, `config`, `feat`, `fix`.
- **Tags** in `annotations.yaml` are free-form; use them to trace cross-cutting threads
  (e.g. `grant`, `milestone-B`, `3rs`, `offline-llm`).
