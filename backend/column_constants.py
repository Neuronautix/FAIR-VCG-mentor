"""
Shared vocabulary constants used by both the profiler inference layer
and the VCG wizard / orchestrator.  Import from here; do not redefine.

These dictionaries drive the deterministic, name-pattern-based stage of
column inference (Stage 1 of the column-understanding roadmap).  They
intentionally bias toward life-sciences naming conventions used by
ARRIVE/preclinical study templates.
"""

# ── Treatment / control vocabulary ──────────────────────────────────────────

CONTROL_KEYWORDS = [
    "vehicle", "ctrl", "control", "saline", "placebo",
    "sham", "wt", "wildtype", "wild-type", "wild_type",
    "veh", "untreated", "naive", "naïve", "mock",
    "baseline", "pbs", "no-treatment", "no_treatment",
]

TREATMENT_KEYWORDS = [
    "treated", "treatment", "drug", "compound", "active",
    "exposed", "dose", "dosed", "administered", "agonist",
    "antagonist", "inhibitor", "stimulus", "test", "experimental",
]

# ── Identifier patterns ─────────────────────────────────────────────────────

IDENTIFIER_PATTERNS = [
    r'.*_id$', r'.*_ID$', r'^id$', r'^ID$', r'.*identifier.*',
    r'.*subject.*id.*', r'.*animal.*id.*', r'.*sample.*id.*',
    r'.*mouse.*id.*', r'.*rat.*id.*', r'.*patient.*id.*',
    r'.*\bdoi\b.*', r'.*\buid\b$', r'.*control_record_id$',
    r'.*\baccession\b.*', r'.*record_id$', r'.*cohort_id$',
    r'.*experiment_id$', r'.*assay_run_id$', r'.*analysis_id$',
    r'.*outcome_id$', r'.*event_id$', r'.*\brun_id\b.*',
    r'.*\bbarcode\b.*', r'.*\brrid\b.*',
]

# Regexes that match the *values* of an identifier-style column
# (e.g. "SD-001", "MOCK_WT_SCRNA_001", "10.1186/s40478-025-02013-z").
IDENTIFIER_VALUE_PATTERNS = [
    r'^[A-Za-z]{1,5}[-_]?\d{2,}$',           # SD-001, A001, P-12
    r'^[A-Z]{2,}_[A-Z0-9_]+_\d+$',            # MOCK_WT_SCRNA_001
    r'^10\.\d{4,9}/.+$',                      # DOI
    r'^[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{12}$',  # UUID
    r'^[A-Z]+:\d+$',                          # ontology IDs e.g. NCBITaxon:10090
    r'^RRID:[A-Z]+_\d+$',                     # RRID
]

# ── Measurement patterns (numeric outcomes) ─────────────────────────────────

MEASUREMENT_PATTERNS = [
    r'.*_g$', r'.*_mg.*', r'.*_kg$', r'.*_cm$', r'.*_mm$', r'.*_ml.*',
    r'.*_s$', r'.*_sec$', r'.*_min$', r'.*_h$', r'.*_hr$',
    r'.*weight.*', r'.*distance.*', r'.*latency.*', r'.*duration.*',
    r'(^count$|.*_count$|count_.*)', r'.*score.*', r'(^level$|.*_level$)', r'.*concentration.*',
    r'.*amount.*', r'.*volume.*', r'.*ratio.*', r'.*index.*',
    r'_pct$', r'.*_percent$', r'.*response.*', r'.*reading.*',
    # Clinical-chemistry / common preclinical assay markers
    r'^alt(_.*)?$', r'^ast(_.*)?$', r'^ggt(_.*)?$', r'^alp(_.*)?$',
    r'^ldh(_.*)?$', r'^bun(_.*)?$', r'^crp(_.*)?$',
    r'.*creatinine.*', r'.*urea.*', r'.*glucose.*', r'.*albumin.*',
    r'.*bilirubin.*', r'.*haematocrit.*', r'.*hematocrit.*',
    r'.*haemoglobin.*', r'.*hemoglobin.*', r'.*cholesterol.*',
    r'.*triglyceride.*', r'.*platelet.*',
    # Common units suffixed onto names
    r'.*_u_l$', r'.*_iu_l$', r'.*_mmol_l$', r'.*_umol_l$', r'.*_µmol_l$',
    r'.*_ng_ml$', r'.*_pg_ml$', r'.*_ug_ml$', r'.*_µg_ml$',
    r'.*_bpm$', r'.*_mmhg$', r'.*_kpa$',
    # Outcome / endpoint conventions used in ARRIVE-style schemas
    r'^outcome\.value$', r'^outcome\.primary_outcome$',
    r'.*outcome_value$', r'.*\.value$',
]

# ── Biological descriptors ──────────────────────────────────────────────────

BIOLOGICAL_PATTERNS = [
    r'^sex$', r'^gender$', r'^genotype$', r'^strain$', r'^species$',
    r'^age.*', r'^breed.*', r'^phenotype.*', r'^background.*',
    r'.*\.sex$', r'.*\.genotype$', r'.*\.strain.*', r'.*\.species.*',
    r'.*\.age_.*', r'.*\.zygosity$', r'.*\.transgene.*',
    r'.*\.genetic_background$', r'.*\.line_rrid_mgi$',
]

SEX_KEYWORDS = ["male", "female", "m", "f", "mixed", "both"]

STRAIN_KEYWORDS = [
    "c57bl", "balb", "sprague-dawley", "sprague_dawley", "wistar",
    "fischer", "long-evans", "long_evans", "fvb", "129", "dba",
    "cd-1", "cd1", "swiss", "nude", "scid",
]

# ── Experimental conditions ─────────────────────────────────────────────────

CONDITION_PATTERNS = [
    r'^group$', r'^treatment.*', r'^dose.*', r'^exposure.*',
    r'^arm$', r'^cohort.*', r'^condition.*', r'^intervention.*',
    r'^drug.*', r'^compound.*', r'^vehicle.*',
    r'.*\.factor_.*', r'.*\.dose$', r'.*\.route$',
    r'.*group_name$', r'.*group_role$',
]

DOSE_PATTERNS = [
    r'.*dose.*', r'.*dosage.*', r'.*concentration.*',
    r'.*_mg_kg$', r'.*_mpk$', r'.*_mg_per_kg$',
    r'.*_mg_l$', r'.*_mg_ml$',
]

# ── Time variables ──────────────────────────────────────────────────────────

TIME_PATTERNS = [
    r'^day.*', r'^timepoint.*', r'^time.*', r'^week.*', r'^hour.*',
    r'^visit.*', r'^session.*', r'^date.*', r'^timestamp.*', r'^period.*',
    r'^baseline.*', r'^followup.*', r'^follow.*up.*', r'.*date$', r'.*created_at$',
    r'.*\.start_date$', r'.*\.end_date$',
    r'.*age_at_.*',
]

# ── Free-text notes ─────────────────────────────────────────────────────────

NOTE_PATTERNS = [
    r'^comment.*', r'^note.*', r'^observation.*', r'^remark.*',
    r'^description.*', r'^details.*', r'^annotation.*',
    r'^definition$', r'^objective$', r'.*\.notes$', r'.*\.objective$',
    r'.*\.curator_notes$',
]

# ── Metadata fields ─────────────────────────────────────────────────────────

METADATA_PATTERNS = [
    r'^operator.*', r'^device.*', r'^instrument.*', r'^protocol.*',
    r'^experimenter.*', r'^technician.*', r'^lab.*', r'^batch.*',
    r'^run.*', r'^plate.*', r'^cage.*', r'^rack.*',
    r'^field_label$', r'^data_type$', r'^unit$', r'^required_for_vcg$',
    r'^vcg_role$', r'^arrive_mapping$', r'^allowed_values_or_format$',
    r'^source_status$', r'^future_value_to_fill$', r'^current_publication_value_or_example$',
    r'.*\.facility$', r'.*\.room$', r'.*\.protocol_.*',
    r'.*\.software.*', r'.*\.platform_instrument$',
    r'.*\.created_by$', r'.*\.source_reference$',
]

# ── Unit aliases (column-name suffix → canonical unit) ──────────────────────

UNIT_MAP = {
    'g': ['_g', 'weight_g', 'mass_g', 'bw_g'],
    'mg': ['_mg', '_milligram'],
    'kg': ['_kg', '_kilogram'],
    'mg/kg': ['_mg_kg', 'dose_mg', 'mpk', '_mg_per_kg'],
    'cm': ['_cm', '_centimeter'],
    'mm': ['_mm', '_millimeter'],
    'µm': ['_um', '_micron', '_micrometer'],
    'm': ['_meter', 'dist_m'],
    'mL': ['_ml', '_milliliter', '_mL'],
    'µL': ['_ul', '_microliter', '_µl'],
    's': ['_s', '_sec', '_second'],
    'min': ['_min', '_minute'],
    'h': ['_h', '_hr', '_hour'],
    '%': ['_pct', '_percent', '_%'],
    'µg/mL': ['_ug_ml', '_µg_ml', 'conc_ug'],
    'ng/mL': ['_ng_ml', 'conc_ng'],
    'pg/mL': ['_pg_ml'],
    'mmol/L': ['_mmol_l', '_mmol_per_l'],
    'µmol/L': ['_umol_l', '_µmol_l', '_umol_per_l'],
    'IU/L': ['_iu_l'],
    'U/L': ['_u_l'],
    'bpm': ['_bpm'],
    'mmHg': ['_mmhg'],
    'kPa': ['_kpa'],
    'years': ['_years', '_yrs', '_yr'],
    'months': ['_months', '_mo'],
    'weeks': ['_weeks', 'age_weeks'],
    'days': ['_days', '_day'],
}
