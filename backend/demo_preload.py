"""
Preloaded demo session based on Huzard et al. (2025), Translational Psychiatry.

DOI: 10.1038/s41398-025-03461-w

This module returns hardcoded session data that mimics what the LLM paper
extractor would produce for the attached publication, so the demo works
without any API key.
"""

from __future__ import annotations

# ── Representative CSV data (alloknesis + skin deformation experiment) ────────
# Values are consistent with the group means reported in the paper.
# This is labelled as example data for demonstration purposes.

DEMO_CSV = """\
subject_id,genotype,sex,age_weeks,body_weight_g,vf_0.02g_scratch_pct,vf_0.07g_scratch_pct,vf_0.4g_scratch_pct,sd_scratch_duration_s,sd_scratch_bouts,c_ltmr_threshold_mn
WT-01,Shank3+/+,M,12,26.3,20,20,30,18.5,8,2.1
WT-02,Shank3+/+,M,14,27.1,20,25,35,25.2,11,2.8
WT-03,Shank3+/+,M,13,25.8,0,20,40,22.7,9,2.4
WT-04,Shank3+/+,M,15,28.4,20,20,20,19.3,7,2.0
WT-05,Shank3+/+,M,12,26.7,20,25,40,24.1,10,2.6
WT-06,Shank3+/+,F,13,22.5,20,20,20,21.5,9,2.3
WT-07,Shank3+/+,F,14,23.1,0,20,40,18.9,8,2.2
WT-08,Shank3+/+,F,12,22.8,20,25,20,26.4,12,2.7
WT-09,Shank3+/+,M,16,27.9,20,20,40,20.8,9,2.5
WT-10,Shank3+/+,M,13,26.4,20,25,20,23.6,10,2.4
KO-01,Shank3ΔC/ΔC,M,12,24.1,60,60,80,40.2,19,5.3
KO-02,Shank3ΔC/ΔC,M,14,25.0,40,60,80,45.7,22,5.8
KO-03,Shank3ΔC/ΔC,M,13,23.8,60,80,100,38.9,18,4.9
KO-04,Shank3ΔC/ΔC,M,15,24.6,60,60,60,42.3,20,5.1
KO-05,Shank3ΔC/ΔC,M,12,24.2,40,60,80,44.8,21,5.4
KO-06,Shank3ΔC/ΔC,F,13,20.3,60,60,80,39.5,19,5.0
KO-07,Shank3ΔC/ΔC,F,14,21.0,60,80,100,48.1,23,6.1
KO-08,Shank3ΔC/ΔC,F,12,20.7,40,60,80,41.6,20,5.2
KO-09,Shank3ΔC/ΔC,M,16,24.9,60,60,80,43.9,21,5.3
KO-10,Shank3ΔC/ΔC,M,13,24.5,60,80,60,46.2,22,5.7
""".encode("utf-8")

DEMO_FILENAME = "huzard_2025_shank3_alloknesis_example.csv"

# ── Metadata extracted from the paper (mimics LLM output) ────────────────────

DEMO_METADATA: dict = {
    # ── Core dataset metadata ──
    "title": "Shank3ΔC/ΔC mouse model — mechanical itch hypersensitivity (example data)",
    "description": (
        "Example dataset from Huzard et al. (2025) Translational Psychiatry 15:259. "
        "Behavioural, electrophysiological, and transcriptomic study of somatosensory "
        "deficits in a Shank3ΔC/ΔC mouse model of autism spectrum disorder, examining "
        "mechanical itch hypersensitivity (alloknesis), C-LTMR function, and TAFA4 expression. "
        "Note: values are representative example data for demo purposes."
    ),
    "keywords": "autism, ASD, Shank3, alloknesis, mechanical itch, C-LTMR, TAFA4, somatosensory",
    "license": "CC BY 4.0",
    "version": "1.0.0",
    "language": "en",
    # ── ARRIVE fields ──
    "study_title": (
        "Primary sensory neuron dysfunction underlying mechanical itch hypersensitivity "
        "in a Shank3 mouse model of autism"
    ),
    "grant_code": "Not reported",
    "start_date": "2022",
    "end_date": "2025",
    "project_licence": (
        "Approved under agreements 2017100915448101 and 2022120112076042, "
        "Herault department Veterinary Direction, France, and the French ministry "
        "for higher education, research and innovation."
    ),
    "protocol_numbers": "2017100915448101; 2022120112076042",
    "severity_classification": (
        "Mild to moderate. Behavioural testing (Von Frey, alloknesis) and minimally "
        "invasive procedures (intradermal injections). Ex vivo preparations from "
        "terminally anaesthetised animals."
    ),
    "primary_contact": "Amaury François — amaury.francois@igf.cnrs.fr",
    "species": "Mus musculus",
    "strain": (
        "Shank3ΔC/ΔC and Shank3+/+ littermates on C57BL/6J background "
        "(>5 back-cross generations)"
    ),
    "sex": (
        "Both sexes for behavioural experiments; males only for qPCR, "
        "electrophysiology and pharmacological studies."
    ),
    "age": "8–20 weeks for behaviour; P100–140 for electrophysiology",
    "weight": "Not individually recorded at time of experiment",
    "supplier": "Shank3ΔC line gifted by Dr. Julie Perroy",
    "total_n": "Behaviour n = 28–31 per genotype; electrophysiology n = 4 per genotype",
    "housing_density": (
        "2–4 animals of similar genotype per ventilated cage (Tecniplast, Italy); "
        "weekly cage changes; food and water ad libitum."
    ),
    "procedures_description": (
        "Von Frey filament testing (hind paw and nape of neck); alloknesis protocol "
        "with 0.02, 0.07 and 0.4 g filaments; skin deformation via 50 µl intradermal "
        "NaCl injection; 20-min video recording and offline BORIS scoring; "
        "ex vivo skin-nerve single-fibre recordings; RT-qPCR of DRG tissue; "
        "pharmacological interventions (lidocaine, flagellin, TAFA4)."
    ),
    "surgical_procedures": (
        "Terminal: transcardial perfusion for immunohistology. "
        "Minimally invasive: intradermal injections (50 µl, 31G) under brief restraint."
    ),
    "anaesthesia": "Ketamine and xylazine for perfusion. No anaesthesia for behavioural tests.",
    "analgesia": "Not applicable for behaviour. Lidocaine/QX-314 used as pharmacological tool.",
    "locations": "Institut de Génomique Fonctionnelle (IGF), Université de Montpellier, France",
    "acclimatisation": (
        "≥30 min in test room before all behavioural experiments; "
        "2-day habituation to Von Frey boxes; gentle-touch training over 10 days."
    ),
    "adverse_events": "Not explicitly reported",
    "humane_endpoints": (
        "Not explicitly pre-specified. Behavioural protocols are non-invasive; "
        "BORIS scoring used offline by blinded experimenter."
    ),
    "welfare_monitoring": (
        "Weekly cage changes; continuous monitoring of food/water intake; "
        "veterinary oversight under approved ethics protocols."
    ),
    "clinical_assessment_form": "Not reported",
    "housing_changes": "No housing changes induced during the study",
    "vet_restrictions": "None reported",
    "experimental_groups": (
        "Two genotype groups: Shank3+/+ (wild-type littermates) and Shank3ΔC/ΔC "
        "(homozygous knockout). Pharmacological sub-groups: NaCl vehicle, lidocaine, "
        "flagellin, TAFA4 (subcutaneous and intradermal)."
    ),
    "experimental_unit": "Individual mouse",
    "sample_size_per_group": (
        "Behaviour: n = 28–31 per genotype (alloknesis); n = 12 per genotype "
        "(skin deformation). Electrophysiology: n = 4 per genotype. qPCR: triplicates."
    ),
    "sample_size_justification": "Not explicitly reported; based on prior experience with model",
    "eda_workflow": "Not reported",
    "inclusion_criteria": (
        "Age 8–20 weeks; Mendelian genotype assignment; both sexes (behaviour). "
        "Males only for qPCR, electrophysiology, pharmacology."
    ),
    "exclusion_criteria": "ROUT method (Q = 1%) used to identify and remove outliers",
    "expected_attrition": "Not reported",
    "randomisation_method": (
        "Roman numeral + number cage labelling; testing order randomised daily; "
        "animals placed so all same-numbered animals tested side by side."
    ),
    "confounder_minimisation": (
        "Experiments conducted 8 am–1 pm under 150–180 lux; animals moved to "
        "test room ≥30 min before testing."
    ),
    "blinding_strategy": (
        "Behavioural testing, recording and analysis performed blind to genotype. "
        "Genotype assignment revealed by co-experimenter after analysis. "
        "Electrophysiology analysis blind until pooling."
    ),
    "outcome_measures": (
        "Scratching percentage (alloknesis); scratching duration and bouts "
        "(skin deformation); Von Frey withdrawal threshold (paw); C-LTMR mechanical "
        "threshold and spike counts; TAFA4, Piezo2, and other DRG gene expression "
        "(RT-qPCR); skin innervation filament length (immunohistology)."
    ),
    "primary_outcome": (
        "Alloknesis scratching percentage in response to Von Frey filaments "
        "applied to the nape of the neck."
    ),
    "analysis_plan": (
        "GraphPad Prism v8/v10. Normality: Shapiro-Wilk. Normal data: "
        "unpaired t-test, 1-way ANOVA, repeated-measures 2-way ANOVA + Sidak. "
        "Non-normal: Mann-Whitney U. qPCR: 2-way ANOVA with FDR correction "
        "(Benjamini-Krieger-Yekutieli). Significance level: p < 0.05."
    ),
    "emergency_procedures": "Not reported",
    "personnel_risks": "Not reported",
    "personnel_names": "Huzard D, Oliva G, Marias M, Granat C, Soubeyre V, Pereira GN, Negm A, Grellier G, Devaux J, Bourinet E, François A",
    "personnel_procedures": "See author contributions in the original publication",
    "personnel_training": "All experimenters blinded; competency implied by institutional affiliation",
    # ── PREPARE fields ──
    "prepare_clear_hypothesis": (
        "Hypothesis: Shank3ΔC/ΔC mice show hypersensitivity to mechanical itch "
        "due to peripheral somatosensory dysfunction, specifically C-LTMR hyporesponsivity."
    ),
    "prepare_systematic_reviews": (
        "Multiple clinical reports of touch differences in ASD patients cited; "
        "animal model literature on peripheral and central somatosensory alterations reviewed."
    ),
    "prepare_search_strategy": "Narrative literature review; no formal systematic review reported",
    "prepare_species_relevance": (
        "Shank3ΔC/ΔC mice carry a mutation linked to Phelan-McDermid syndrome and ASD "
        "in humans; C57BL/6J background standard for ASD mouse models."
    ),
    "prepare_reproducibility_translatability": (
        "Validated ASD behavioural phenotype (social preference, marble burying, "
        "repetitive grooming) replicated from prior literature."
    ),
    "prepare_legislation_compliance": (
        "All procedures complied with European Community welfare guidelines; "
        "approved under agreements 2017100915448101 and 2022120112076042."
    ),
    "prepare_guidance_documents": "European Community welfare guidelines; EU Directive 2010/63",
    "prepare_lay_summary": "Not reported in the publication",
    "prepare_ethics_committee_dialogue": (
        "Approved by Herault department Veterinary Direction, France and French "
        "ministry for higher education, research and innovation."
    ),
    "prepare_3rs_3ss": (
        "Both sexes tested initially; males only used for invasive endpoints to "
        "reduce total animal numbers."
    ),
    "prepare_preregistration_negative_results": "Not reported",
    "prepare_harm_benefit_assessment": (
        "Implicitly balanced: non-invasive behavioural tests; intradermal injections "
        "are minimally invasive; benefit is understanding ASD sensory mechanisms."
    ),
    "prepare_learning_objectives": (
        "Investigate whether Shank3ΔC/ΔC mice show mechanical itch hypersensitivity; "
        "identify responsible sensory fibre populations; explore TAFA4 as a potential mediator."
    ),
    "prepare_severity_classification": (
        "Mild–moderate. Non-invasive alloknesis testing; minimally invasive "
        "intradermal injections; terminal procedures for histology and electrophysiology."
    ),
    "prepare_humane_endpoints": "Not explicitly pre-specified in the publication",
    "prepare_death_endpoint_justification": "Not applicable — no death as endpoint",
    "prepare_pilot_power_significance": "Not explicitly reported",
    "prepare_experimental_unit": "Individual mouse",
    "prepare_randomisation_blinding_criteria": (
        "Roman numeral + number labelling per cage; daily randomisation of testing order; "
        "blinding maintained until post-analysis genotype assignment."
    ),
    "prepare_staff_meetings": "Not reported",
    "prepare_species_strain": (
        "Mus musculus, Shank3ΔC/ΔC on C57BL/6J background; "
        "line gifted by Dr. Julie Perroy."
    ),
    "prepare_acclimation": (
        "≥30 min in test room before experiments; 2-day habituation to Von Frey boxes; "
        "10-day gentle-touch training programme."
    ),
    "prepare_housing_husbandry": (
        "2–4 animals of similar genotype per ventilated cage (Tecniplast); "
        "weekly cage changes; food and water ad libitum; C57BL/6J standard housing."
    ),
    "prepare_animal_care": "Standard vivarium care; ethical oversight under approved protocols",
    "prepare_anaesthesia_analgesia": (
        "Ketamine/xylazine for terminal perfusion. "
        "Lidocaine + QX-314 used as pharmacological tools, not analgesics."
    ),
    "prepare_surgeries_invasive": (
        "Terminal transcardial perfusion. Minimally invasive intradermal injections "
        "(50 µl, 31G syringe)."
    ),
    "prepare_sample_collection": (
        "DRG dissection for RT-qPCR (500 ng total RNA; PrimeScript RT); "
        "thoracic back skin for immunohistology (cryosections, 25 µm)."
    ),
    "prepare_tissue_analysis": (
        "Confocal microscopy (Leica SP8); Imaris filament tracing; RT-qPCR (LightCycler 480); "
        "ex vivo skin-nerve recordings (DAM-80 amplifier, Spike2 analysis)."
    ),
    "prepare_pilot_study": "Not reported",
    "prepare_cost_calculation": "Not reported",
    "prepare_facility_evaluation": (
        "IGF facility (CNRS UMR5203, INSERM U1191, Université de Montpellier); "
        "standard preclinical research infrastructure."
    ),
    "prepare_education_training": (
        "All experimenters blinded; competency implied by institutional affiliation "
        "and publication authorship."
    ),
    "prepare_health_risks_waste": "Not reported",
    "prepare_quarantine_health_monitoring": "Not explicitly reported",
}


def get_demo_paper_extraction() -> dict:
    """Return a paper-extraction-style dict mimicking LLM output for this paper."""
    return {
        "_filename": "huzard_2025_shank3_alloknesis.pdf",
        "_source": "demo_preload",
        "title": (
            "Primary sensory neuron dysfunction underlying mechanical itch "
            "hypersensitivity in a Shank3 mouse model of autism"
        ),
        "authors": "Huzard D, Oliva G, Marias M, Granat C, Soubeyre V, Pereira GN, Negm A, Grellier G, Devaux J, Bourinet E, François A",
        "journal": "Translational Psychiatry",
        "year": "2025",
        "doi": "10.1038/s41398-025-03461-w",
        "abstract": (
            "Autism Spectrum Disorder (ASD) is a neurodevelopmental disorder marked by "
            "social deficits, repetitive behaviors and atypical sensory perception. "
            "This study explores mechanical itch sensitivity in the Shank3ΔC/ΔC mouse model. "
            "Key observations include heightened scratching in response to skin deformation "
            "and hypersensitivity to mechanical itch (alloknesis). C-fiber low-threshold "
            "mechanoreceptors (C-LTMRs) were hyporesponsive and TAFA4 was downregulated. "
            "Pharmacologically inhibiting Aβ-LTMR abolished itch hypersensitivity. "
            "TAFA4 injections reduced spontaneous scratching but failed to restore itch sensitivity."
        ),
        "arrive": {
            "study_design": {
                "value": (
                    "Randomised, blinded, controlled experiment comparing Shank3ΔC/ΔC and "
                    "Shank3+/+ littermates on behavioural, histological, electrophysiological "
                    "and molecular endpoints."
                ),
                "status": "found",
            },
            "sample_size": {
                "value": (
                    "Behaviour n=28–31 per genotype; electrophysiology n=4; "
                    "qPCR triplicates."
                ),
                "status": "found",
            },
            "inclusion_exclusion_criteria": {
                "value": (
                    "Age 8–20 weeks; Mendelian genotype assignment. "
                    "ROUT (Q=1%) for outlier removal."
                ),
                "status": "found",
            },
            "randomisation": {
                "value": (
                    "Roman numeral + number labelling; daily randomised testing order."
                ),
                "status": "found",
            },
            "blinding": {
                "value": (
                    "Experimenters blind to genotype throughout; assignment revealed post-analysis."
                ),
                "status": "found",
            },
            "outcome_measures": {
                "value": (
                    "Scratching % (alloknesis); scratching duration/bouts (skin deformation); "
                    "C-LTMR mechanical threshold; TAFA4 expression; skin innervation."
                ),
                "status": "found",
            },
            "statistical_methods": {
                "value": (
                    "GraphPad Prism; Shapiro-Wilk; unpaired t-test/ANOVA/Mann-Whitney; "
                    "Sidak post-hoc; p<0.05 significance."
                ),
                "status": "found",
            },
            "experimental_animals": {
                "value": (
                    "Mus musculus; Shank3ΔC/ΔC on C57BL/6J background; "
                    "8–20 weeks; both sexes."
                ),
                "status": "found",
            },
            "housing": {
                "value": (
                    "2–4 per ventilated cage (Tecniplast); weekly changes; "
                    "ad libitum food/water."
                ),
                "status": "found",
            },
            "animal_care": {
                "value": "Standard vivarium; ethics approval 2017100915448101 & 2022120112076042.",
                "status": "found",
            },
            "ethical_statement": {
                "value": (
                    "Compliant with European Community welfare guidelines. "
                    "Agreements 2017100915448101 and 2022120112076042."
                ),
                "status": "found",
            },
        },
        "prepare": {
            "literature_searches": {
                "value": (
                    "Clinical reports of touch differences in ASD; animal model literature "
                    "on peripheral/central somatosensory alterations; Shank3 and "
                    "Phelan-McDermid syndrome links to ASD."
                ),
                "status": "found",
            },
            "legal_issues": {
                "value": (
                    "EU Directive 2010/63; French ministry approvals 2017100915448101 "
                    "and 2022120112076042."
                ),
                "status": "found",
            },
            "lay_summary": {
                "value": None,
                "status": "missing",
            },
            "harm_benefit_assessment": {
                "value": (
                    "Non-invasive/minimally invasive procedures; "
                    "benefit: understanding ASD sensory mechanisms."
                ),
                "status": "inferred",
            },
            "severity_classification": {
                "value": "Mild–moderate (behavioural, minimally invasive pharmacological).",
                "status": "found",
            },
            "humane_endpoints": {
                "value": None,
                "status": "missing",
            },
            "facility_evaluation": {
                "value": "IGF facility, CNRS/INSERM/Université de Montpellier.",
                "status": "inferred",
            },
            "education_training": {
                "value": "All experimenters blinded; institutional competency implied.",
                "status": "inferred",
            },
            "health_risks_waste": {
                "value": None,
                "status": "missing",
            },
            "quarantine_health_monitoring": {
                "value": None,
                "status": "missing",
            },
            "housing_husbandry": {
                "value": (
                    "2–4 animals/cage (Tecniplast); weekly cage changes; "
                    "ad libitum food/water; C57BL/6J standard."
                ),
                "status": "found",
            },
            "humane_killing": {
                "value": "Ketamine/xylazine anaesthesia followed by transcardial perfusion.",
                "status": "found",
            },
            "necropsy": {
                "value": "DRG dissection for RT-qPCR; thoracic skin dissection for histology.",
                "status": "found",
            },
        },
        "summary": (
            "Study of mechanical itch hypersensitivity in Shank3ΔC/ΔC ASD mouse model. "
            "Strong ARRIVE compliance (randomisation, blinding, ethics, animal details). "
            "PREPARE gaps: lay summary, explicit humane endpoints, health risk assessment."
        ),
    }
