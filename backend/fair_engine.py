from typing import List, Dict, Any


def compute_fair_score(
    import_info: Dict,
    columns: List[Dict],
    table_structure: Dict,
    metadata: Dict,
    issues: List[Dict],
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
        'Dataset identifier / URI present': has('base_uri') and has('title'),
        'Creator or contact present': has('creator') or has('contact_email'),
        'Keywords or ontology terms present': has('keywords'),
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
        'Access conditions stated': has('access_conditions'),
        'File format open (CSV)': True,
        'Contact or repository present': has('contact_email') or has('institution'),
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
        'Controlled vocabularies used': has_controlled_vocab,
        'External ontology or URI mapping': has_uri_mapping,
        'JSON-LD or CSVW export ready': has('title') and has_col_descriptions,
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

    # ── Reusable (25 pts, 5 each) ──────────────────────────────────────────
    r = {
        'Protocol or method described': has('protocol_reference'),
        'Provenance captured': has('creator') and has('date_created'),
        'Data dictionary present': has_col_descriptions,
        'Missing values documented': all(
            c.get('missing_values', 0) == 0 or c.get('user_description')
            for c in columns
        ),
        'Version or date recorded': has('version') or has('date_created'),
    }
    r_score = sum(5 for v in r.values() if v)
    r_weak = (
        'No protocol or method described'
        if not r['Protocol or method described']
        else 'No provenance captured'
        if not r['Provenance captured']
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
        recs.append('Define allowed values for categorical columns (e.g. sex: male / female / unknown).')
    if not i['External ontology or URI mapping']:
        recs.append('Map key columns to ontology terms or internal URIs.')
    if not r['Protocol or method described']:
        recs.append('Add a protocol or method reference.')
    if not has_col_descriptions:
        recs.append('Add column descriptions to create a data dictionary.')
    if not r['Provenance captured']:
        recs.append('Record provenance: creator name and date of data collection.')

    return {
        'fair_score': total,
        'findable': {'score': f_score, 'max_score': 25, 'main_weakness': f_weak, 'criteria': f},
        'accessible': {'score': a_score, 'max_score': 20, 'main_weakness': a_weak, 'criteria': a},
        'interoperable': {'score': i_score, 'max_score': 30, 'main_weakness': i_weak, 'criteria': i},
        'reusable': {'score': r_score, 'max_score': 25, 'main_weakness': r_weak, 'criteria': r},
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

    return issues
