from typing import List, Dict, Any, Optional


def _template_conformance_score(template_validation: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Score the declares_template_conformance criterion (0/1/3/5 pts)."""
    if not template_validation:
        return {
            "satisfied": False,
            "points": 0,
            "pct": 0.0,
            "recommendation": (
                "Assign a community template (ARRIVE, MNMS, ...) to declare conformance"
            ),
        }
    total = len(template_validation)
    satisfied = sum(1 for e in template_validation if e.get("status") == "satisfied")
    pct = (satisfied / total) * 100.0 if total else 0.0
    if pct >= 90.0:
        return {"satisfied": True, "points": 5, "pct": pct, "recommendation": None}
    if pct >= 50.0:
        return {
            "satisfied": False,
            "points": 3,
            "pct": pct,
            "recommendation": (
                f"Template only {pct:.0f}% satisfied; address remaining required fields "
                "for full conformance points."
            ),
        }
    return {
        "satisfied": False,
        "points": 1,
        "pct": pct,
        "recommendation": (
            f"Template only {pct:.0f}% satisfied; address remaining required fields "
            "for full conformance points."
        ),
    }


def compute_fair_score(
    import_info: Dict,
    columns: List[Dict],
    table_structure: Dict,
    metadata: Dict,
    issues: List[Dict],
    template_validation: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    def has(field: str) -> bool:
        val = metadata.get(field)
        return bool(val) and (not isinstance(val, list) or len(val) > 0)

    measurements = [c for c in columns if c['inferred_type'] == 'measurement']
    identifiers = [c for c in columns if c['inferred_type'] == 'identifier']
    has_col_descriptions = any(c.get('user_description') for c in columns)
    has_col_units = all(
        c.get('user_unit') or c.get('unit_guess') for c in measurements
    ) if measurements else False
    has_controlled_vocab = any(c.get('allowed_values') for c in columns)
    has_uri_mapping = any(c.get('uri') for c in columns)

    # ── Findable (25 pts, 5 each) ──────────────────────────────────────────
    f = {
        'Dataset title present': has('title'),
        'Dataset description present': has('description'),
        'Dataset identifier / URI present': (has('base_uri') and has('title')) or has('persistent_identifier') or has('repository_url'),
        'Creator or contact present': has('creator') or has('contact_email'),
        'Keywords or ontology terms present': has('keywords') or has('ontology_terms'),
    }
    f_score = sum(5 for v in f.values() if v)
    f_weak = (
        'No persistent dataset identifier'
        if not f['Dataset identifier / URI present']
        else 'No title defined'
        if not f['Dataset title present']
        else 'Missing creator or contact'
    )

    # ── Accessible (20 pts, 5 each) ────────────────────────────────────────
    a = {
        'License defined': has('license'),
        'Access conditions stated': has('access_conditions') or has('repository_url'),
        'File format open (CSV)': True,
        'Contact or repository present': has('contact_email') or has('institution') or has('repository_url'),
    }
    a_score = sum(5 for v in a.values() if v)
    a_weak = (
        'No license defined'
        if not a['License defined']
        else 'No access conditions stated'
        if not a['Access conditions stated']
        else 'No contact information'
    )

    # ── Interoperable (30 pts, 5 each) ────────────────────────────────────
    i = {
        'Column metadata present': has_col_descriptions,
        'Units defined for measurements': has_col_units and bool(measurements),
        'Controlled vocabularies used': has_controlled_vocab or has('ontology_terms'),
        'External ontology or URI mapping': has_uri_mapping or has('ontology_terms') or has('base_uri'),
        'JSON-LD or CSVW export ready': (has('title') and has_col_descriptions) or has('data_dictionary_reference'),
        'Stable identifiers for entities': bool(identifiers),
    }
    i_score = sum(5 for v in i.values() if v)
    i_weak = (
        'No controlled vocabularies or URI mapping'
        if not i['Controlled vocabularies used']
        else 'Missing units for measurements'
        if not i['Units defined for measurements']
        else 'No column descriptions'
    )

    # ── Reusable (30 pts, 5 each) ──────────────────────────────────────────
    template_conformance = _template_conformance_score(template_validation)
    r = {
        'Protocol or method described': has('protocol_reference'),
        'Provenance captured': (has('creator') and has('date_created')) or has('provenance_notes'),
        'Data dictionary present': has_col_descriptions or has('data_dictionary_reference'),
        'Missing values documented': all(
            c.get('missing_values', 0) == 0 or c.get('user_description')
            for c in columns
        ),
        'Version or date recorded': has('version') or has('date_created'),
        'declares_template_conformance': template_conformance['satisfied'],
    }
    r_score = sum(5 for k, v in r.items() if v and k != 'declares_template_conformance')
    r_score += template_conformance['points']
    r_weak = (
        'No protocol or method described'
        if not r['Protocol or method described']
        else 'No provenance captured'
        if not r['Provenance captured']
        else 'No data dictionary'
        if not r['Data dictionary present']
        else 'No reporting-standard template declared'
        if not r['declares_template_conformance']
        else 'No data dictionary'
    )

    total = f_score + a_score + i_score + r_score

    recs: List[str] = []
    if not f['Dataset title present']:
        recs.append('Add a dataset title.')
    if not f['Creator or contact present']:
        recs.append('Add creator or contact information.')
    if not a['License defined']:
        recs.append('Add a license (e.g. CC BY 4.0).')
    if measurements and not i['Units defined for measurements']:
        recs.append('Add units for all quantitative variables.')
    if not i['Controlled vocabularies used']:
        recs.append('Define allowed values for categorical columns or add relevant ontology terms.')
    if not i['External ontology or URI mapping']:
        recs.append('Map key columns to ontology terms or internal URIs.')
    if not r['Protocol or method described']:
        recs.append('Add a protocol or method reference.')
    if not has_col_descriptions:
        recs.append('Add column descriptions to create a data dictionary.')
    if not r['Provenance captured']:
        recs.append('Record provenance: creator/date or a concise provenance note.')
    if template_conformance.get('recommendation'):
        recs.append(template_conformance['recommendation'])

    return {
        'fair_score': total,
        'findable': {'score': f_score, 'max_score': 25, 'main_weakness': f_weak, 'criteria': f},
        'accessible': {'score': a_score, 'max_score': 20, 'main_weakness': a_weak, 'criteria': a},
        'interoperable': {'score': i_score, 'max_score': 30, 'main_weakness': i_weak, 'criteria': i},
        'reusable': {'score': r_score, 'max_score': 30, 'main_weakness': r_weak, 'criteria': r},
        'main_recommendations': recs[:7],
    }


def detect_issues(
    import_info: Dict,
    columns: List[Dict],
    table_structure: Dict,
) -> List[Dict]:
    issues: List[Dict] = []

    identifiers = [c for c in columns if c['inferred_type'] == 'identifier']
    measurements = [c for c in columns if c['inferred_type'] == 'measurement']

    if not identifiers:
        issues.append({
            'id': 'no_identifier',
            'severity': 'high',
            'category': 'structure',
            'column': None,
            'problem': 'No identifier column detected.',
            'why_it_matters': (
                'Without a stable identifier, rows cannot be reliably linked to other datasets, '
                'provenance records, or external systems. This makes the data very difficult to '
                'reuse or cross-reference.'
            ),
            'suggested_fix': (
                'Add a unique identifier column (e.g. animal_id, sample_id, subject_id) '
                'that uniquely identifies each row or entity.'
            ),
        })

    for col in measurements:
        if not col.get('unit_guess') and not col.get('user_unit'):
            issues.append({
                'id': f'missing_unit_{col["name"]}',
                'severity': 'medium',
                'category': 'metadata',
                'column': col['name'],
                'problem': f'Column "{col["name"]}" appears to be a measurement but has no unit defined.',
                'why_it_matters': (
                    'A measurement value without a unit is not reusable or comparable across datasets. '
                    'It is impossible to determine whether values are in grams, milligrams, or arbitrary units.'
                ),
                'suggested_fix': (
                    f'Rename the column to include the unit (e.g. {col["name"]}_g or {col["name"]}_mg_kg) '
                    'or define the unit in the data dictionary.'
                ),
            })

    ambiguous_names = {'value', 'data', 'result', 'measurement', 'number', 'val', 'amount', 'x', 'y'}
    for col in columns:
        if col['name'].lower() in ambiguous_names:
            issues.append({
                'id': f'ambiguous_name_{col["name"]}',
                'severity': 'medium',
                'category': 'naming',
                'column': col['name'],
                'problem': f'Column name "{col["name"]}" is ambiguous and does not describe the variable.',
                'why_it_matters': (
                    'Ambiguous column names make it impossible to understand what the variable '
                    'represents without additional context, severely reducing reusability.'
                ),
                'suggested_fix': (
                    f'Rename "{col["name"]}" to something descriptive, '
                    'e.g. "body_weight_g", "distance_cm", or "latency_s".'
                ),
            })

    for col in columns:
        if col['name'].lower() in ('sex', 'gender') and not col.get('allowed_values'):
            issues.append({
                'id': f'no_vocab_{col["name"]}',
                'severity': 'medium',
                'category': 'interoperability',
                'column': col['name'],
                'problem': f'Column "{col["name"]}" has no controlled vocabulary defined.',
                'why_it_matters': (
                    'Without controlled values, sex/gender data is often inconsistently encoded '
                    '(M, m, Male, male, MALE), preventing machine-readable comparison across datasets.'
                ),
                'suggested_fix': (
                    'Define allowed values: male, female, unknown. '
                    'Apply consistent encoding throughout the column.'
                ),
            })

    for col in columns:
        if col['missing_pct'] > 20:
            issues.append({
                'id': f'high_missing_{col["name"]}',
                'severity': 'low',
                'category': 'quality',
                'column': col['name'],
                'problem': f'Column "{col["name"]}" has {col["missing_pct"]}% missing values.',
                'why_it_matters': (
                    'High proportions of missing values reduce data quality and may indicate '
                    'data entry errors or inapplicable fields. Missing values should be documented.'
                ),
                'suggested_fix': (
                    'Document why values are missing. Use "NA" for not applicable, '
                    '"ND" for not determined, or "NM" for not measured.'
                ),
            })

    for col_name in import_info.get('empty_columns', []):
        issues.append({
            'id': f'empty_column_{col_name}',
            'severity': 'high',
            'category': 'quality',
            'column': col_name,
            'problem': f'Column "{col_name}" is completely empty.',
            'why_it_matters': (
                'Completely empty columns add noise and may indicate incomplete data collection '
                'or copy-paste errors.'
            ),
            'suggested_fix': f'Remove the empty column "{col_name}" or populate it with appropriate values.',
        })

    for col_name in import_info.get('duplicate_columns', []):
        issues.append({
            'id': f'duplicate_column_{col_name}',
            'severity': 'high',
            'category': 'structure',
            'column': col_name,
            'problem': f'Column name "{col_name}" appears more than once.',
            'why_it_matters': (
                'Duplicate column names cause ambiguity and make it impossible to reliably '
                'reference a specific column programmatically.'
            ),
            'suggested_fix': (
                f'Rename duplicate columns to make them distinct, '
                f'e.g. "{col_name}_1" and "{col_name}_2".'
            ),
        })

    has_protocol = any(
        'protocol' in c['name'].lower() or 'method' in c['name'].lower()
        for c in columns
    )
    if not has_protocol:
        issues.append({
            'id': 'no_protocol_column',
            'severity': 'low',
            'category': 'reusability',
            'column': None,
            'problem': 'No protocol or method column detected.',
            'why_it_matters': (
                'Without reference to the experimental protocol, it is impossible to reproduce '
                'the experiment or compare results with datasets using different procedures.'
            ),
            'suggested_fix': (
                'Add a protocol_id or method column, or include a protocol reference '
                'in the dataset-level metadata.'
            ),
        })

    has_provenance = any(
        any(x in c['name'].lower() for x in ['operator', 'experimenter', 'technician', 'date', 'batch'])
        for c in columns
    )
    if not has_provenance:
        issues.append({
            'id': 'no_provenance_columns',
            'severity': 'low',
            'category': 'reusability',
            'column': None,
            'problem': 'No provenance columns detected (operator, date, batch, instrument).',
            'why_it_matters': (
                'Without provenance information, it is impossible to audit who collected the data, '
                'when, or with what instrument, weakening data integrity.'
            ),
            'suggested_fix': (
                'Add columns for operator, date, and instrument, '
                'or include this information in the dataset metadata.'
            ),
        })

    # ── ARRIVE 2.0 compliance checks ─────────────────────────────────────────
    # Only triggered for datasets that appear to be pre-clinical animal studies.
    PRECLINICAL_SIGNALS = {
        'animal_id', 'animal', 'mouse', 'rat', 'mice', 'rats', 'rabbit', 'pig',
        'strain', 'cage', 'litter', 'dose', 'dosing', 'treatment', 'group',
        'body_weight', 'bw', 'organ_weight',
    }
    col_names_lower = {c['name'].lower() for c in columns}
    is_preclinical = bool(col_names_lower & PRECLINICAL_SIGNALS)

    if is_preclinical:
        metadata_flat = import_info  # import_info doesn't carry metadata; use columns instead
        # We check the table_structure and column list as proxies for the items we can detect.

        # ARRIVE 2.1 – Ethical statement
        has_ethics = any(
            any(kw in c['name'].lower() for kw in ['ethic', 'iacuc', 'approval', 'license'])
            for c in columns
        )
        if not has_ethics:
            issues.append({
                'id': 'arrive_missing_ethical_statement',
                'severity': 'medium',
                'category': 'arrive_2.0',
                'column': None,
                'problem': 'ARRIVE 2.0 (item 1): No ethical statement detected.',
                'why_it_matters': (
                    'ARRIVE 2.0 requires documentation of ethical approval (IACUC, Home Office, '
                    'or equivalent) for all in vivo studies. Most journals mandate this.'
                ),
                'suggested_fix': (
                    'Add an "ethical_approval_id" column or record the ethics committee '
                    'approval number in the dataset metadata.'
                ),
            })

        # ARRIVE 2.3 – Sex of animals
        has_sex = any(c['name'].lower() in ('sex', 'gender') for c in columns)
        if not has_sex:
            issues.append({
                'id': 'arrive_missing_sex',
                'severity': 'medium',
                'category': 'arrive_2.0',
                'column': None,
                'problem': 'ARRIVE 2.0 (item 3): Sex of animals not recorded.',
                'why_it_matters': (
                    'Sex is a biological variable that strongly influences most physiological '
                    'endpoints. ARRIVE 2.0 and most journals require it to be reported.'
                ),
                'suggested_fix': (
                    'Add a "sex" column with values: male, female, or unknown.'
                ),
            })

        # ARRIVE 2.3 – Species / strain
        has_strain = any(
            any(kw in c['name'].lower() for kw in ['strain', 'species', 'genotype', 'line'])
            for c in columns
        )
        if not has_strain:
            issues.append({
                'id': 'arrive_missing_strain',
                'severity': 'medium',
                'category': 'arrive_2.0',
                'column': None,
                'problem': 'ARRIVE 2.0 (item 3): Strain or species not recorded as a column.',
                'why_it_matters': (
                    'Results are not reproducible without knowing the exact strain, substrain, '
                    'and source of animals. This is a core ARRIVE 2.0 essential item.'
                ),
                'suggested_fix': (
                    'Add a "strain" or "species" column recording the exact animal background.'
                ),
            })

        # ARRIVE 2.4 – Housing and husbandry (light cycle, housing)
        has_housing = any(
            any(kw in c['name'].lower() for kw in ['cage', 'housing', 'light', 'temperature', 'humidity'])
            for c in columns
        )
        if not has_housing:
            issues.append({
                'id': 'arrive_missing_housing',
                'severity': 'low',
                'category': 'arrive_2.0',
                'column': None,
                'problem': 'ARRIVE 2.0 (item 4): Housing / husbandry conditions not recorded.',
                'why_it_matters': (
                    'Light cycle, temperature, and social housing significantly affect behaviour '
                    'and physiology. ARRIVE 2.0 requires these to be reported.'
                ),
                'suggested_fix': (
                    'Add housing metadata (cage_type, light_cycle, temperature_C) as columns '
                    'or document them in the metadata protocol field.'
                ),
            })

        # ARRIVE 2.5 – Sample size statement / group size
        has_n = any(
            any(kw in c['name'].lower() for kw in ['group', 'cohort', 'batch', 'replicate'])
            for c in columns
        )
        n_rows = table_structure.get('n_rows') or import_info.get('n_rows', 0)
        if not has_n and n_rows < 6:
            issues.append({
                'id': 'arrive_small_n',
                'severity': 'medium',
                'category': 'arrive_2.0',
                'column': None,
                'problem': f'ARRIVE 2.0 (item 5): Dataset has very few rows (n={n_rows}); group size statement likely missing.',
                'why_it_matters': (
                    'ARRIVE 2.0 requires justification for the chosen sample size. '
                    'Very small datasets raise concerns about statistical power.'
                ),
                'suggested_fix': (
                    'Add a "group_size_justification" field to dataset metadata or a '
                    'power calculation reference in the protocol field.'
                ),
            })

        # ARRIVE 2.6 – Inclusion / exclusion criteria
        has_exclusion = any(
            any(kw in c['name'].lower() for kw in ['exclude', 'excluded', 'outlier', 'dropout'])
            for c in columns
        )
        if not has_exclusion:
            issues.append({
                'id': 'arrive_missing_exclusion',
                'severity': 'low',
                'category': 'arrive_2.0',
                'column': None,
                'problem': 'ARRIVE 2.0 (item 6): No exclusion/inclusion criteria column detected.',
                'why_it_matters': (
                    'Without documented exclusion criteria, selective reporting of results '
                    'cannot be ruled out. ARRIVE 2.0 requires pre-specified criteria.'
                ),
                'suggested_fix': (
                    'Add an "excluded" flag column (True/False) with a reason field, '
                    'or document criteria in the protocol metadata field.'
                ),
            })

        # ARRIVE 2.7 – Randomisation
        has_randomisation = any(
            any(kw in c['name'].lower() for kw in ['random', 'randomis', 'randomiz', 'allocation'])
            for c in columns
        )
        if not has_randomisation:
            issues.append({
                'id': 'arrive_missing_randomisation',
                'severity': 'medium',
                'category': 'arrive_2.0',
                'column': None,
                'problem': 'ARRIVE 2.0 (item 7): No randomisation information detected.',
                'why_it_matters': (
                    'Lack of randomisation is a leading source of bias in animal studies. '
                    'ARRIVE 2.0 requires a description of how animals were allocated to groups.'
                ),
                'suggested_fix': (
                    'Add a "randomisation_method" field to dataset metadata '
                    '(e.g. "stratified by body weight, computer-generated sequence").'
                ),
            })

        # ARRIVE 2.8 – Blinding
        has_blinding = any(
            any(kw in c['name'].lower() for kw in ['blind', 'blinded', 'masked'])
            for c in columns
        )
        if not has_blinding:
            issues.append({
                'id': 'arrive_missing_blinding',
                'severity': 'medium',
                'category': 'arrive_2.0',
                'column': None,
                'problem': 'ARRIVE 2.0 (item 8): No blinding information detected.',
                'why_it_matters': (
                    'Observer bias is a major source of irreproducibility. ARRIVE 2.0 requires '
                    'a statement on whether outcome assessment was blinded to treatment group.'
                ),
                'suggested_fix': (
                    'Add a "blinding" field to dataset metadata '
                    '(e.g. "outcome assessors blinded to treatment allocation").'
                ),
            })

    return issues
