# Standardizing ARRIVE 2.0, PREPARE, EQIPD and MNMS into one FAIR Metadata Pipeline

> **Purpose of this document.** This is a self-contained specification of how the four
> life-sciences guidelines/standards — **ARRIVE 2.0**, **PREPARE**, the **EQIPD Quality
> System**, and **MNMS** — are unified, cross-referenced, filled and reported inside
> FAIR‑VCG Mentor. It is written so that a developer can re-implement the *same*
> standardization pipeline in an **independent application** without reading the original
> source. It describes the conceptual model, the unified data schema, the inheritance and
> crosswalk mechanics, the field catalogues, the validation algorithm, and the three
> "fill" channels and three "report" channels.
>
> Everything here is grounded in the working implementation; field ids, prefixes, statuses,
> and algorithms are exact.

---

## 1. The four standards — what each one *is* and what it governs

These four artefacts are **not** competing standards. They sit at different points in the
research lifecycle and at different levels of granularity. Standardizing them means
modelling all four as instances of **one** template schema and then wiring the
relationships between their fields.

| Standard | Lifecycle stage | Granularity | Native shape | Role in the pipeline |
|----------|-----------------|-------------|--------------|----------------------|
| **PREPARE** (Smith et al. 2018, Norecopa) | **Planning** — before the study | Dataset / study level | 15 topics → 38–42 checklist sub‑items | "What you must *plan* before touching an animal." Pre‑study planning checklist. |
| **ARRIVE 2.0** (arriveguidelines.org) | **Reporting** — after the study | Dataset / study level | Essential 10 + Recommended Set, grouped in ~11 sections | "What you must *report* when publishing." Reporting standard. |
| **EQIPD Quality System** (Vollert et al. 2024) | **Cross‑cutting** — the unit's quality system, any time | Unit / lab level | 18 Core Requirements in 7 categories | "What quality controls your *unit* has in place." Research‑led quality framework (lighter than GLP). |
| **MNMS** (Minimum Metadata Schema) | **Data capture** — the CSV itself | **Column** level | ~20 required columns + units + roles | "What columns your *data file* must contain." The only column‑level standard; it is the bridge from a raw CSV to ARRIVE. |

The recommended scientific workflow is **PREPARE → CARE → SHARE → FLAG**; PREPARE plans it,
ARRIVE reports it, EQIPD assures the unit's quality, MNMS is the machine‑readable data
layer that lets a CSV be checked against ARRIVE automatically.

### Why they can be standardized together

1. **They overlap heavily in content.** "Humane endpoints", "sample‑size justification",
   "randomisation", "personnel training", "legislation compliance" appear in *three or four*
   of them under different names. Standardizing = recognising these as the **same concept**
   and filling each only once.
2. **They are filled from the same evidence.** A single study (a paper, a protocol, a CSV +
   metadata) carries enough information to populate parts of all four. So the fill logic and
   the evidence model are shared.
3. **They differ only in two axes**: *where the field lives* (a CSV **column** vs a
   dataset‑level **metadata** field) and *which standard it belongs to*. Both axes are
   captured as attributes on a single field type — so one engine serves all four.

---

## 2. The unifying data model

Everything reduces to one object — a **Template** — with two kinds of fields. Re-implement
these and you can express all four standards (and any future one) as data, not code.

### 2.1 `Template`

```
Template:
  id: str                       # stable slug, e.g. "arrive-v2", "prepare-v1", "eqipd-v1", "mnms-v1"
  name: str                     # display name, e.g. "ARRIVE 2.0"
  version: str
  description: str
  identifier: str | None        # canonical URL of the standard
  conforms_to: list[str]        # parent template ids — drives INHERITANCE (see §3)
  ontology: {iri, prefix}       # namespace for linked-data export
  required_columns:  list[RequiredColumn]    # COLUMN-level compliance tier
  optional_columns:  list[RequiredColumn]
  required_metadata: list[RequiredMetadata]  # DATASET-level compliance tier
  vcg_defaults: {...} | None    # optional: downstream analysis hints (MNMS only)
  predefined_analyses: [...]    # optional: analyses to run when assigned (MNMS only)
  fair_bonus: {dimension, max_points}   # contribution to a FAIR/quality score
  source: "builtin" | "user"
```

### 2.2 `RequiredColumn` — the column-level tier (MNMS uses this)

```
RequiredColumn:
  id: str
  name_patterns: list[str]   # substrings OR regexes matched against CSV header names
  semantic_type: str | None  # e.g. "identifier"
  role: str | None           # subject_id | treatment | outcome | covariate | time | clustering_unit
  arrive_section: str | None # which ARRIVE section this column satisfies (the bridge!)
  unit_required: bool        # must carry a unit
  unit_column: str | None    # companion column that supplies the unit
  required: bool
  severity: high | medium | low
```

### 2.3 `RequiredMetadata` — the dataset-level tier (ARRIVE, PREPARE, EQIPD use this)

```
RequiredMetadata:
  id: str                    # field id; PREPARE ids are prefixed "prepare_", EQIPD "eqipd_", ARRIVE unprefixed
  arrive_section:  str | None   # ARRIVE grouping label
  prepare_section: str | None   # PREPARE topic label, e.g. "3. Ethical issues, harm-benefit assessment and humane endpoints"
  eqipd_section:   str | None   # EQIPD category, e.g. "Data integrity"
  guidance:  str | None         # inline drafting hint (EQIPD: the verbatim Core Requirement + a hint)
  crosswalk: list[str]          # sibling field_ids that, if filled, AUTO-SATISFY this field (see §4)
  severity:  high | medium | low
```

**The three `*_section` keys are the heart of standardization.** A single metadata field can
declare its membership in ARRIVE *and* PREPARE *and* EQIPD simultaneously. That is how one
filled value reports against multiple standards at once.

> **Field-id prefix convention (load-bearing — do not unify):**
> - ARRIVE field ids are **unprefixed**: `species`, `humane_endpoints`, `sample_size_justification`.
> - PREPARE field ids use the **`prepare_`** prefix: `prepare_humane_endpoints`.
> - EQIPD field ids use the **`eqipd_`** prefix: `eqipd_personnel_training`.
> The engine distinguishes standards by id prefix and by which `*_section` key is set. Keep
> them separate even when they describe the same concept; the crosswalk (not id‑merging) is
> what links them.

---

## 3. Inheritance — `conforms_to` (vertical composition)

`conforms_to` lets one template **inherit the entire field set** of one or more parents. This
is how the pipeline expresses "MNMS conforms to ARRIVE" and "the crosswalk template is
ARRIVE + PREPARE".

### 3.1 The merge rule

When a template declares `conforms_to: [P1, P2, …]`:

1. Resolve each parent first (recursively; **cycles are an error**, missing parent is an error).
2. For each parent, copy every `required_column` and every `required_metadata` whose `id` is
   **not already present** in the child. **Child wins on id collision** (a child may override
   a parent field by redefining the same id).
3. The result is a flat, fully‑merged field list on the child.

Pseudocode:

```
resolve(t):
    for parent_id in t.conforms_to:
        p = resolve(parent_id)              # recursive, cycle-checked
        for col in p.required_columns:
            if col.id not in t.required_columns: t.required_columns.append(col)
        for m in p.required_metadata:
            if m.id not in t.required_metadata: t.required_metadata.append(m)
    return t
```

### 3.2 The actual inheritance graph

```
        arrive-v2 (51 metadata fields, 0 columns)
        ▲        ▲
        │        │
   mnms-v1   arrive-prepare-crosswalk-v1
 (20 cols,    (conforms_to: [arrive-v2, prepare-v1])
  conforms_to        ▲
  arrive-v2)         │
                 prepare-v1 (42 metadata fields, 0 columns)

   eqipd-v1  ── standalone, NO conforms_to (18 Core Requirements)
```

- **`mnms-v1` → `arrive-v2`.** MNMS is column‑level; ARRIVE is metadata‑level. Inheriting
  ARRIVE's `required_metadata` means an MNMS‑validated CSV can *also* be scored against
  ARRIVE's dataset‑level expectations. The link between an MNMS **column** and an ARRIVE
  **section** is the column's `arrive_section` attribute (e.g. the `outcome` column declares
  `arrive_section: "Outcome and statistics / Outcome measures"`).
- **`arrive-prepare-crosswalk-v1` → `[arrive-v2, prepare-v1]`.** This template owns **zero**
  fields of its own; it is purely the union of ARRIVE's 51 reporting fields and PREPARE's 42
  planning fields. Assign it to fill *both* standards in one metadata pass. The
  cross‑annotations (a field carrying both `arrive_section` and `prepare_section`) live on the
  PREPARE entries.
- **`eqipd-v1` is standalone.** A quality system is orthogonal to any single study's plan or
  report, so it inherits nothing. It reaches the other standards purely through **crosswalks**
  (§4), not inheritance.

---

## 4. Crosswalks — `crosswalk` (horizontal auto-satisfaction)

Inheritance composes whole field‑sets. **Crosswalks** link *individual equivalent concepts
across standards* so the user fills a concept **once** and every standard that shares it is
credited automatically. This is the second, and more important, half of standardization.

### 4.1 Semantics

A `RequiredMetadata` field may carry `crosswalk: [other_field_id, …]`. Meaning:

> "If any field id in this list already has a value, consider **me** satisfied too,
>  and record *which* sibling satisfied me."

Two crucial properties:

1. **Directional.** Only the field that *declares* a crosswalk list is auto‑satisfied. The
   reverse is **not** inferred. (`prepare_humane_endpoints` crosswalks to ARRIVE's
   `humane_endpoints`; filling the PREPARE field does **not** retroactively satisfy the ARRIVE
   field.) This keeps a reporting standard honest — you cannot claim you *reported* something
   merely because you *planned* it.
2. **Cross‑standard via shared metadata.** A crosswalk target counts as satisfied when it is
   either (a) a satisfied **sibling field in the same merged template**, **or** (b) any key
   with a non‑empty value in the **shared session metadata dict**. Property (b) is what lets a
   *standalone* standard (EQIPD) borrow values from ARRIVE/PREPARE fields that are not in its
   own template — because all standards write into one shared metadata dict keyed by field id.

### 4.2 The two crosswalk directions actually wired

**(A) PREPARE → ARRIVE** (planning concept borrows from the reporting field of the same idea).
Most PREPARE fields declare an `arrive_section` *and* a `crosswalk` list pointing at ARRIVE
field ids. Representative links (full list lives in `prepare-v1`):

| PREPARE field | crosswalks to ARRIVE field(s) | shared concept |
|---|---|---|
| `prepare_clear_hypothesis` | `outcome_measures`, `primary_outcome` | hypothesis / primary outcome |
| `prepare_legislation_compliance` | `protocol_numbers`, `project_licence` | legal authorisation |
| `prepare_severity_classification` | `severity_classification` | severity |
| `prepare_humane_endpoints` | `humane_endpoints` | humane endpoints |
| `prepare_pilot_power_significance` | `sample_size_justification`, `sample_size_per_group`, `analysis_plan` | power / sample size |
| `prepare_experimental_unit` | `experimental_unit`, `total_n` | experimental unit |
| `prepare_randomisation_blinding_criteria` | `randomisation_method`, `blinding_strategy`, `inclusion_criteria`, `exclusion_criteria` | bias control |
| `prepare_staff_competence` | `personnel_training` | training |
| `prepare_risk_assessment` | `personnel_risks`, `emergency_procedures` | risk |
| `prepare_animal_characteristics` | `species`, `strain`, `sex`, `age`, `weight`, `supplier` | animals |
| `prepare_refined_substance_anaesthesia` | `anaesthesia`, `analgesia`, `surgical_procedures` | refinement |

**(B) EQIPD → ARRIVE/PREPARE** (a quality requirement borrows from a study‑level field the
user already filled). Exactly **five** of EQIPD's 18 Core Requirements have an honest
equivalent elsewhere and declare crosswalks; the other 13 (data integrity, storage,
traceability, incident management, sustainability, …) have no equivalent and stay
manual/LLM‑filled:

| EQIPD Core Requirement (field) | crosswalks to | shared concept |
|---|---|---|
| CR4 `eqipd_legislation_compliance` | `ethics_statement`, `prepare_legislation_compliance` | compliance |
| CR10 `eqipd_knowledge_claim_declaration` | `prepare_clear_hypothesis` | exploratory vs confirmatory |
| CR11 `eqipd_personnel_training` | `personnel_training`, `prepare_staff_competence` | training & competence |
| CR12 `eqipd_protocols_available` | `procedures_description` | protocols/SOPs |
| CR15 `eqipd_risk_assessment` | `prepare_risk_assessment` | risk assessment |

Note CR4 and CR11 point at field ids from **two different standards** at once (ARRIVE *and*
PREPARE) — the first one filled wins.

### 4.3 Net effect

A user who fills ARRIVE once can have large parts of PREPARE auto‑satisfied; a user who fills
ARRIVE+PREPARE can have 5 of EQIPD's 18 requirements auto‑satisfied. The remaining EQIPD
requirements (the genuinely quality‑system‑specific ones) are surfaced as the real, unique
work EQIPD asks for.

---

## 5. The field catalogues (what to encode)

You do not need to memorise every field, but you need the **shape** and the **section
vocabularies**. Encode each standard as a YAML/JSON list of the field type in §2.

### 5.1 ARRIVE 2.0 — `required_metadata` only (no columns)

~51 metadata fields grouped under these `arrive_section` labels:

```
Study details · Experimental animals · Experimental procedures ·
Animal care & monitoring · Study design & sample size · Inclusion/exclusion ·
Randomisation & blinding · Outcome & statistics · Risk assessment · Personnel
```

High‑severity (Essential‑10‑aligned) fields include: `study_title`, `species`, `sex`, `age`,
`total_n`, `experimental_groups`, `sample_size_justification`, `randomisation_method`,
`blinding_strategy`, `outcome_measures`.

### 5.2 PREPARE — `required_metadata` only, 42 sub-items across 15 topics

`prepare_section` vocabulary (the 15 topics, declaration order preserved):

```
(A) Formulation of the study
  1. Literature searches
  2. Legal issues
  3. Ethical issues, harm-benefit assessment and humane endpoints
  4. Experimental design and statistical analysis
(B) Dialogue between scientists and the animal facility
  5. Objectives and timescale, funding and division of labour
  6. Facility evaluation
  7. Education and training
  8. Health risks, waste disposal and decontamination
(C) Quality control of the components in the study
  9.  Test substances and procedures
  10. Experimental animals
  11. Quarantine and health monitoring
  12. Housing and husbandry
  13. Experimental procedures
  14. Humane killing, release, reuse or rehoming
  15. Necropsy
```

Each PREPARE field also carries a one‑line **planning prompt** (used when filling — see §7).
~26 of the 42 fields additionally carry an `arrive_section` + `crosswalk` (§4.2A).

### 5.3 EQIPD — 18 Core Requirements, `eqipd_section` in 7 categories

`eqipd_section` vocabulary and the Core Requirements that map to it:

```
Research team           → CR1 process owner, CR2 communication process
Quality culture         → CR3 quality objectives, CR4 legislation compliance*, CR5 misconduct procedure
Data integrity          → CR6 data-record documentation, CR7 storage security, CR8 outcome traceability, CR9 repetition disclosure
Research processes      → CR10 knowledge-claim declaration*, CR11 personnel training*, CR12 protocols available*,
                          CR13 sample/material handling, CR14 equipment suitability
Continuous improvement  → CR15 risk assessment*, CR16 incident management, CR17 performance monitoring
Sustainability          → CR18 sustaining resources
(* = carries a crosswalk to ARRIVE/PREPARE, §4.2B)
```

Every EQIPD field carries a `guidance` string = the verbatim Core Requirement text + a short
drafting hint. EQIPD has **no `required_columns`** — it is filled entirely through the
metadata fill workspace, and it benefits from (but degrades gracefully without) an LLM.

### 5.4 MNMS — `required_columns` (the only column-level standard)

~20 required + 2 optional columns. Each column carries `name_patterns` (header matching),
optionally a `role` (for downstream analysis), optional `unit_required`/`unit_column`, and —
critically — an `arrive_section` that maps the **column** to an ARRIVE reporting section, e.g.:

```
subject_id   → "Experimental animals / Total number"     role: subject_id
species      → "Experimental animals / Species"
sex          → "Experimental animals / Sex"
weight_start → "Experimental animals / Weight"   unit_required, unit_column: Weight_Unit
xp_group     → "Study design and sample size / Experimental groups incl. controls"  role: treatment
dvc_cage     → "Study design and sample size / Experimental unit"  role: clustering_unit
outcome      → "Outcome and statistics / Outcome measures"  unit_required, role: outcome
randomisation→ "Study design and sample size / Randomisation"
blinding     → "Study design and sample size / Blinding"
```

MNMS also (optionally) carries `vcg_defaults` and `predefined_analyses` for downstream
statistical use; these are not part of the standardization core and can be omitted in a
re‑implementation focused on FAIR metadata.

---

## 6. The validation algorithm (the engine)

Given an assigned template (already merged via §3), a list of CSV columns, and the shared
metadata dict, produce a **conformance report**: one entry per field with a status.

### 6.1 Conformance entry shape (stable contract)

```
{
  standard:        str,      # template.name
  section:         str,      # arrive_section → prepare_section → eqipd_section (first non-null)
  arrive_section:  str|None,
  prepare_section: str|None,
  eqipd_section:   str|None,
  field_id:        str,
  status:          "satisfied" | "partial" | "missing",
  satisfied_by:    {column: name} | {metadata: id} | {metadata: id, via_crosswalk: true} | None,
  severity:        high|medium|low,
  is_column_field: bool
}
```

### 6.2 Algorithm

**Pass 1 — columns** (`required_columns`): for each spec, find a CSV header whose name matches
any `name_patterns` entry (case‑insensitive substring, or regex if the pattern contains regex
metacharacters).
- no match → `missing`.
- match, and `unit_required` is false → `satisfied` (`satisfied_by={column}`).
- match, and `unit_required` is true → `satisfied` **iff** the matched column has a unit
  (`user_unit`/`unit_guess`) *or* the companion `unit_column` is present; else `partial`.

**Pass 2 / Step A — metadata direct** (`required_metadata`): for each spec, read
`metadata[field_id]`. Non‑empty (`not in (None, "", [], {})`) → `satisfied`
(`satisfied_by={metadata: field_id}`); else `missing`.

**Pass 2 / Step B — metadata crosswalk** (the cross‑standard step): for each metadata spec
that declares a `crosswalk` and is still **not** satisfied, walk its crosswalk ids in order.
A target satisfies it when **either** that target is a satisfied sibling field **or**
`metadata[target]` is non‑empty. On the first hit, flip the entry to `satisfied` with
`satisfied_by = {metadata: target, via_crosswalk: true}` and stop.

```
for meta in required_metadata where meta.crosswalk and entry.status != "satisfied":
    for target in meta.crosswalk:
        if field_satisfied[target] or metadata[target] not empty:
            entry.status = "satisfied"
            entry.satisfied_by = {metadata: target, via_crosswalk: true}
            break
```

That's the whole engine. Note Step B only ever *upgrades* status; it never demotes, and it
only fires for fields that explicitly declare a crosswalk (preserving directionality, §4.1).

### 6.3 Turning conformance into issues / score

- Every non‑`satisfied` entry becomes an **issue** with `category="template_compliance"` and a
  stable id `template_{template_id}_{field_id}` (so they can be stripped on un‑assign).
  `partial` and `missing` get different problem/fix text; column vs metadata get different fix
  text. Severity is carried from the field.
- A compliance/FAIR **score** contribution (`fair_bonus`, here `dimension: R`, `max_points: 5`)
  scales with the **percentage of satisfied fields** — e.g. 0 / 1 / 3 / 5 points at increasing
  satisfaction bands. Missing fields **degrade** the score; they never **block** anything
  downstream.

---

## 7. Filling the standards (three channels)

A field's value can arrive through three channels, all writing into the **same shared
metadata dict** (which is what makes crosswalks cross‑standard, §4.1). Channel order of
preference is direct > crosswalk‑borrowed > paper > LLM.

### 7.1 Channel 1 — manual / wizard

A metadata form keyed by `field_id`. For PREPARE the form shows the one‑line **planning
prompt**; for EQIPD it shows the Core Requirement **guidance**; for ARRIVE the section label.
Crosswalk‑satisfied fields are shown as already‑green with a "satisfied by *sibling*" note so
the user is not asked twice.

### 7.2 Channel 2 — paper / document extraction (deterministic)

Given a structured extraction of a source paper (an `arrive` block of detected concepts, a
`dataset_metadata` block, a topic‑level `prepare` block, and `vcg_hints`), a deterministic
mapping fills fields whose current value is empty:

- ARRIVE‑native fields map directly from the `arrive` extraction block.
- PREPARE‑only fields map from the topic‑level `prepare` block (13 extracted topics fan out to
  the 42 sub‑items via a hint map), with ARRIVE‑concept fallbacks for the items that have a
  crosswalk.
- Each fill records its **source path** (e.g. `arrive.outcome_measures`,
  `prepare.literature_searches`, `dataset_metadata.title`) and a truncated preview, so the UI
  can show *what was filled and from where*. Only empty fields are filled — never overwrite.

A paper extraction is *also* used to **rank which template to assign** (a scoring function
boosts ARRIVE/PREPARE on extracted‑field coverage + in‑vivo species, MNMS on cage/DVC
keywords, EQIPD modestly on quality/rigour/SOP keywords + an in‑vivo bonus). EQIPD, having no
columns, surfaces only as a **low‑ranked** candidate and never auto‑assigns.

### 7.3 Channel 3 — LLM draft (for fields with no deterministic source)

For fields that paper extraction can't fill (most EQIPD requirements, free‑text PREPARE
items), build a per‑field prompt payload carrying: `field_id`, label, the `*_section` context,
severity, the PREPARE planning **prompt** or EQIPD **guidance**, the `crosswalk` sibling ids as
**context_keys**, and the *existing values* of any filled context keys. The model drafts a
grounded candidate per field. The system prompt is standard‑agnostic (it just names the
assigned template), so the same code drafts for any of the four standards. EQIPD effectively
*requires* this channel for its 13 unique requirements; without an API key the workspace still
loads and those fields are filled manually.

---

## 8. Reporting the standards (three outputs)

Standardization pays off at report time: one filled dataset emits compliance for all four
standards. Three report shapes:

1. **Conformance report** (§6.1) — the live per‑field status list, surfaced as issues and as
   the FAIR R‑dimension score. This is the machine‑readable compliance record.

2. **Completion report** — an enriched per‑field roll‑up for the fill workspace:
   `totals` (satisfied_direct / satisfied_via_crosswalk / partial / missing), `by_severity`,
   and `by_section` — where a field appears under **each** of its ARRIVE/PREPARE/EQIPD sections
   simultaneously (so the same value reports in three section trees at once). Each field record
   carries its current value, the satisfying sibling (if via crosswalk), and — when not yet
   satisfied — the planning prompt / guidance and the paper hint.

3. **Human‑readable standard documents** — e.g. the PREPARE export is a zip of:
   - `prepare_study_plan.md` — the 15 topics, each sub‑item rendered with its planning prompt
     and the resolved value (resolving via crosswalk and annotating "*(from ARRIVE: field)*"
     when borrowed), plus a sign‑off table.
   - `prepare_checklist.md` — a 38‑row status table (✅ Planned / ⚠️ Partial / ❌ Missing, with
     "via ARRIVE: *field*" notes) + an action‑items list of everything still missing.

   An equivalent renderer can be written per standard (an ARRIVE reporting document, an EQIPD
   quality‑system declaration) over the same conformance report.

---

## 9. Reference pipeline for an independent re-implementation

To build this in another app, implement these eight steps. None of them depend on the host
application's web framework, database, or UI.

1. **Define the schema** (§2): `Template`, `RequiredColumn`, `RequiredMetadata`. Back it with a
   JSON‑Schema validator so templates can be authored as data and validated on load.

2. **Author the four standards as data** (§5): four YAML/JSON files. ARRIVE and PREPARE and
   EQIPD are `required_metadata` only; MNMS is `required_columns` (+ `conforms_to: [arrive]`).
   Add the `arrive-prepare-crosswalk` template as `conforms_to: [arrive, prepare]` with no own
   fields. Set the `*_section` labels and `crosswalk` lists exactly as in §4–§5.

3. **Implement the loader with `conforms_to` resolution** (§3): recursive, cycle‑checked,
   child‑wins merge. Cache the resolved templates.

4. **Implement template suggestion/assignment** (§7.2): score templates against the dataset
   (column‑pattern coverage 0.7 + metadata coverage 0.3) or against a paper extraction; auto‑
   assign at score ≥ 0.9, otherwise present as candidates. (EQIPD, with no columns, never auto‑
   assigns.)

5. **Implement the validation engine** (§6): Pass 1 columns, Pass 2 Step A direct metadata,
   Step B crosswalk auto‑satisfaction. Emit conformance entries in the stable shape.

6. **Implement the three fill channels** (§7): a metadata store keyed by `field_id` (manual),
   a deterministic paper/document mapper that records source + preview and never overwrites,
   and an LLM per‑field prompt builder that forwards section + prompt/guidance + crosswalk
   context. **All three must write into one shared metadata dict** — that single shared dict is
   the mechanism that makes cross‑standard crosswalks work.

7. **Implement the reports** (§8): conformance → issues + score; a completion roll‑up
   (totals / by‑severity / by‑section with multi‑section membership); and per‑standard
   human‑readable documents that resolve values via crosswalk and annotate the borrow.

8. **Preserve the invariants** (below).

### Invariants to preserve (so the standardization stays correct)

- **One shared metadata dict, keyed by field id.** Crosswalks resolve against it; without
  sharing, a standalone standard (EQIPD) can't borrow from ARRIVE/PREPARE.
- **Crosswalks are directional.** Only the declaring field auto‑satisfies. Never infer the
  reverse — a reporting field is not satisfied because a planning field is filled.
- **Prefix discipline.** `prepare_*` / `eqipd_*` / unprefixed‑ARRIVE ids must stay distinct;
  the engine and the crosswalk targets reference them by exact id.
- **`*_section` keys are additive and never removed.** A field may belong to several standards'
  sections at once; reports rely on each key being present (possibly null).
- **Missing fields degrade, never block.** Non‑compliance lowers the score and raises issues
  but must not stop filling, assignment, or any downstream step.
- **Inheritance is child‑wins, cycle‑checked.** A child may override a parent field by id; a
  cyclic `conforms_to` is a hard error.
- **Status vocabulary is exactly `satisfied | partial | missing`** and `satisfied_by` is one of
  `{column}`, `{metadata}`, `{metadata, via_crosswalk:true}`, or null. Downstream report and
  score code reads these verbatim.

---

## 10. One-screen summary

- **Model:** every standard is a `Template` of `RequiredColumn` (CSV‑level) and
  `RequiredMetadata` (dataset‑level) fields. A field can name an `arrive_section`,
  `prepare_section`, **and** `eqipd_section` at once.
- **Vertical link = `conforms_to`** (inherit a parent's whole field set; child wins on id).
  MNMS⊳ARRIVE; crosswalk‑template⊳{ARRIVE,PREPARE}; EQIPD standalone.
- **Horizontal link = `crosswalk`** (fill an equivalent concept once; auto‑satisfy the
  declaring field, directional, cross‑standard via the shared metadata dict).
  PREPARE→ARRIVE (~26 links) and EQIPD→ARRIVE/PREPARE (5 links).
- **Validate:** columns → direct metadata → crosswalk metadata, producing
  `satisfied|partial|missing` per field.
- **Fill:** manual / paper‑extraction / LLM, all into one shared metadata dict.
- **Report:** conformance list + FAIR score, a completion roll‑up by section/severity, and
  human‑readable per‑standard documents — all from the same filled state.

Implement those four links (the schema, `conforms_to`, `crosswalk`, the shared metadata dict)
and the validation engine, and you have a fully independent FAIR metadata standardization
pipeline that can fill and report ARRIVE 2.0, PREPARE, EQIPD, and MNMS — and any standard you
add later — from a single source of truth.
