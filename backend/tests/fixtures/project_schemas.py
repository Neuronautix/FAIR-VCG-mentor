from copy import deepcopy


COMPLETE_VCG_READY_SCHEMA = {
    "schema_version": 1,
    "name": "vcg_ready_oncology_project",
    "status": "approved",
    "metadata_fields": {
        "species": {
            "value": "Mus musculus",
            "required": True,
            "source": "paper",
            "evidence": ["ev_paper_1_species", "ev_paper_2_species"],
            "confidence": 0.98,
            "review_status": "approved",
        },
        "model": {
            "value": "xenograft",
            "source": "expert",
            "evidence": ["ev_paper_1_model"],
            "confidence": 0.9,
            "review_status": "approved",
        },
    },
    "columns": [
        {
            "name": "animal_id",
            "label": "Animal ID",
            "semantic_type": "identifier",
            "data_type": "string",
            "required": True,
            "role": "identifier",
            "evidence": ["ev_paper_1_subject_id"],
            "confidence": 0.99,
            "review_status": "approved",
        },
        {
            "name": "treatment_group",
            "semantic_type": "categorical",
            "data_type": "string",
            "required": True,
            "role": "treatment",
            "controlled_values": ["vehicle", "drug_a"],
            "evidence": ["ev_paper_1_treatment", "ev_paper_2_treatment"],
            "confidence": 0.96,
            "review_status": "approved",
        },
        {
            "name": "tumor_volume_mm3",
            "semantic_type": "measurement",
            "data_type": "number",
            "unit": "mm3",
            "required": True,
            "role": "outcome",
            "evidence": ["ev_paper_1_tumor"],
            "confidence": 0.94,
            "review_status": "approved",
        },
        {
            "name": "baseline_weight_g",
            "semantic_type": "measurement",
            "data_type": "number",
            "unit": "g",
            "role": "covariate",
            "evidence": ["ev_paper_2_weight"],
            "confidence": 0.91,
            "review_status": "approved",
        },
        {
            "name": "study_day",
            "semantic_type": "time",
            "data_type": "integer",
            "unit": "day",
            "role": "time",
            "evidence": ["ev_paper_1_tumor"],
            "confidence": 0.88,
            "review_status": "approved",
        },
    ],
    "vcg_roles": {
        "subject_id": "animal_id",
        "treatment_col": "treatment_group",
        "control_value": "vehicle",
        "treatment_value": "drug_a",
        "outcome_cols": ["tumor_volume_mm3"],
        "covariate_cols": ["baseline_weight_g"],
        "time_col": "study_day",
        "exclude_cols": [],
    },
    "units": {
        "tumor_volume_mm3": {
            "canonical_unit": "mm3",
            "accepted_units": ["mm3", "cubic millimeter"],
            "conversion_required": False,
            "evidence": ["ev_paper_1_tumor"],
        },
        "baseline_weight_g": {
            "canonical_unit": "g",
            "accepted_units": ["g", "gram"],
            "conversion_required": False,
            "evidence": ["ev_paper_2_weight"],
        },
    },
    "controlled_values": {
        "treatment_group": {
            "canonical_values": ["vehicle", "drug_a"],
            "aliases": {"control": "vehicle", "compound a": "drug_a"},
            "evidence": ["ev_paper_1_treatment", "ev_paper_2_treatment"],
        },
    },
    "ontology_mappings": {
        "tumor_volume_mm3": {
            "label": "tumor volume",
            "curie": "NCIT:C94537",
            "source": "NCIT",
            "confidence": 0.82,
            "evidence": ["ev_paper_1_tumor"],
        },
    },
    "vcg_readiness": {
        "ready": True,
        "blocking": [],
        "warnings": [],
        "score": 0.95,
    },
    "evidence": [
        {
            "id": "ev_paper_1_species",
            "paper_id": "paper_1",
            "section": "Methods",
            "quote": "Female BALB/c nude mice were used.",
            "supports": ["metadata_fields.species"],
            "confidence": 0.98,
        },
        {
            "id": "ev_paper_2_species",
            "paper_id": "paper_2",
            "section": "Methods",
            "quote": "Experiments were conducted in mice.",
            "supports": ["metadata_fields.species"],
            "confidence": 0.92,
        },
        {
            "id": "ev_paper_1_model",
            "paper_id": "paper_1",
            "section": "Methods",
            "quote": "Tumor xenografts were established before treatment.",
            "supports": ["metadata_fields.model"],
            "confidence": 0.9,
        },
        {
            "id": "ev_paper_1_subject_id",
            "paper_id": "paper_1",
            "section": "Supplement",
            "quote": "Each animal was assigned a unique study identifier.",
            "supports": ["columns.animal_id"],
            "confidence": 0.99,
        },
        {
            "id": "ev_paper_1_treatment",
            "paper_id": "paper_1",
            "section": "Methods",
            "quote": "Animals received vehicle or drug A.",
            "supports": ["columns.treatment_group", "controlled_values.treatment_group"],
            "confidence": 0.96,
        },
        {
            "id": "ev_paper_2_treatment",
            "paper_id": "paper_2",
            "section": "Methods",
            "quote": "The comparator arm was vehicle control.",
            "supports": ["columns.treatment_group", "controlled_values.treatment_group"],
            "confidence": 0.91,
        },
        {
            "id": "ev_paper_1_tumor",
            "paper_id": "paper_1",
            "section": "Results",
            "quote": "Tumor volume was measured in cubic millimeters on each study day.",
            "supports": ["columns.tumor_volume_mm3", "units.tumor_volume_mm3"],
            "confidence": 0.94,
        },
        {
            "id": "ev_paper_2_weight",
            "paper_id": "paper_2",
            "section": "Supplement",
            "quote": "Baseline body weight was recorded in grams.",
            "supports": ["columns.baseline_weight_g", "units.baseline_weight_g"],
            "confidence": 0.91,
        },
    ],
    "expert_decisions": [
        {
            "id": "decision_1",
            "field": "vcg_roles.control_value",
            "decision": "approved",
            "reviewer": "expert",
        }
    ],
}


CONFLICTING_ALIASES_UNITS_SCHEMA_DRAFT = {
    "name": "conflicting_aliases_units_draft",
    "status": "draft",
    "metadata_fields": {
        "species": {
            "value": "Mus musculus",
            "source": "llm",
            "evidence": ["ev_draft_species"],
            "confidence": 0.7,
            "review_status": "needs_review",
        }
    },
    "columns": [
        {
            "name": "animal_id",
            "role": "identifier",
            "data_type": "string",
            "evidence": ["ev_draft_subject"],
            "confidence": 0.82,
        },
        {
            "name": "treatment_group",
            "role": "treatment",
            "data_type": "string",
            "allowed_values": ["vehicle", "drug_a", "drug_b"],
            "evidence": ["ev_draft_treatment"],
            "confidence": 0.68,
        },
        {
            "name": "dose_mg_per_kg",
            "role": "covariate",
            "data_type": "number",
            "unit": "mg/kg",
            "evidence": ["ev_draft_dose", "ev_missing_dose_column"],
            "confidence": 0.62,
        },
        {
            "name": "tumor_volume",
            "role": "outcome",
            "data_type": "number",
            "unit": "mm3",
            "evidence": ["ev_draft_tumor"],
            "confidence": 0.74,
        },
    ],
    "vcg_roles": {
        "control_value": "vehicle",
        "treatment_value": "drug_a",
    },
    "units": {
        "dose_mg_per_kg": {
            "canonical_unit": "mg/kg",
            "accepted_units": ["mg/kg", "mg kg-1", "mg"],
            "conversion_required": True,
            "evidence": ["ev_draft_dose", "ev_missing_dose_unit"],
        },
        "drug_concentration": {
            "canonical_unit": "mg/mL",
            "accepted_units": ["mg/ml", "mg"],
            "conversion_required": True,
            "evidence": ["ev_draft_dose"],
        },
    },
    "controlled_values": {
        "treatment_group": {
            "canonical_values": ["vehicle", "drug_a", "drug_b"],
            "aliases": {
                "control": "vehicle",
                "veh": "vehicle",
                "vehicle": "drug_a",
                "compound a": "drug_a",
            },
            "evidence": ["ev_draft_treatment", "ev_missing_alias_source"],
        }
    },
    "evidence": [
        {
            "id": "ev_draft_species",
            "paper_id": "paper_1",
            "section": "Methods",
            "quote": "The study used mice.",
            "supports": ["metadata_fields.species"],
            "confidence": 0.7,
        },
        {
            "id": "ev_draft_subject",
            "paper_id": "paper_1",
            "section": "Supplement",
            "quote": "Animal identifiers were recorded.",
            "supports": ["columns.animal_id"],
            "confidence": 0.82,
        },
        {
            "id": "ev_draft_treatment",
            "paper_id": "paper_1",
            "section": "Methods",
            "quote": "Treatment labels included vehicle and active compounds.",
            "supports": ["columns.treatment_group", "controlled_values.treatment_group"],
            "confidence": 0.68,
        },
        {
            "id": "ev_draft_dose",
            "paper_id": "paper_2",
            "section": "Methods",
            "quote": "Dose was reported as mg/kg.",
            "supports": ["columns.dose_mg_per_kg", "units.dose_mg_per_kg"],
            "confidence": 0.62,
        },
        {
            "id": "ev_draft_tumor",
            "paper_id": "paper_2",
            "section": "Results",
            "quote": "Tumor volume was tabulated.",
            "supports": ["columns.tumor_volume"],
            "confidence": 0.74,
        },
    ],
}


HALLUCINATED_ROLE_REFERENCE_SCHEMA = {
    "name": "hallucinated_role_reference_draft",
    "status": "needs_review",
    "columns": [
        {
            "name": "animal_id",
            "role": "identifier",
            "data_type": "string",
            "evidence": ["ev_hallucinated_subject"],
            "confidence": 0.86,
        },
        {
            "name": "treatment_group",
            "role": "treatment",
            "data_type": "string",
            "evidence": ["ev_hallucinated_treatment"],
            "confidence": 0.8,
        },
        {
            "name": "tumor_volume",
            "role": "outcome",
            "data_type": "number",
            "unit": "mm3",
            "evidence": ["ev_hallucinated_outcome"],
            "confidence": 0.83,
        },
    ],
    "vcg_roles": {
        "subject_id": "mouse_identifier_from_llm",
        "treatment_col": "treatment_group",
        "control_value": "vehicle",
        "treatment_value": "drug_a",
        "outcome_cols": ["tumor_volume", "imagined_response_score"],
        "covariate_cols": ["baseline_weight_from_unseen_table"],
    },
    "evidence": [
        {
            "id": "ev_hallucinated_subject",
            "paper_id": "paper_1",
            "section": "Supplement",
            "quote": "The supplement included animal-level rows.",
            "supports": ["columns.animal_id"],
            "confidence": 0.86,
        },
        {
            "id": "ev_hallucinated_treatment",
            "paper_id": "paper_1",
            "section": "Methods",
            "quote": "Animals were assigned to vehicle or drug A.",
            "supports": ["columns.treatment_group"],
            "confidence": 0.8,
        },
        {
            "id": "ev_hallucinated_outcome",
            "paper_id": "paper_2",
            "section": "Results",
            "quote": "Tumor volume was measured after treatment.",
            "supports": ["columns.tumor_volume"],
            "confidence": 0.83,
        },
    ],
}


def complete_vcg_ready_schema():
    return deepcopy(COMPLETE_VCG_READY_SCHEMA)


def conflicting_aliases_units_schema_draft():
    return deepcopy(CONFLICTING_ALIASES_UNITS_SCHEMA_DRAFT)


def hallucinated_role_reference_schema():
    return deepcopy(HALLUCINATED_ROLE_REFERENCE_SCHEMA)
