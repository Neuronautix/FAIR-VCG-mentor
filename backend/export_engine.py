import io
import json
import re
import zipfile
import csv as csv_module
from datetime import datetime
from typing import Dict, List, Any

import pandas as pd


def _normalize_col_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.lower().strip('_')


def generate_cleaned_csv(df: pd.DataFrame, columns: List[Dict], metadata: Dict) -> str:
    rename_map = {}
    for col in columns:
        orig = col['name']
        new_name = col.get('user_label') or _normalize_col_name(orig)
        if new_name != orig:
            rename_map[orig] = new_name

    cleaned = df.copy()
    if rename_map:
        cleaned = cleaned.rename(columns=rename_map)

    for col in columns:
        col_in_cleaned = rename_map.get(col['name'], col['name'])
        allowed = col.get('allowed_values')
        if allowed and col_in_cleaned in cleaned.columns:
            lower_map = {v.lower(): v for v in allowed}
            cleaned[col_in_cleaned] = cleaned[col_in_cleaned].apply(
                lambda x: lower_map.get(str(x).strip().lower(), x) if pd.notna(x) else x
            )

    return cleaned.to_csv(index=False)


def generate_data_dictionary(columns: List[Dict], metadata: Dict) -> str:
    buf = io.StringIO()
    writer = csv_module.writer(buf)
    writer.writerow([
        'column_name', 'label', 'description', 'data_type',
        'unit', 'allowed_values', 'required', 'uri', 'semantic_type',
    ])
    for col in columns:
        writer.writerow([
            col['name'],
            col.get('user_label') or col.get('label') or col['name'],
            col.get('user_description') or col.get('description') or '',
            col.get('user_type') or col.get('data_type') or '',
            col.get('user_unit') or col.get('unit_guess') or '',
            '|'.join(col.get('allowed_values') or []),
            'true' if col.get('required') else 'false',
            col.get('uri') or '',
            col.get('inferred_type') or '',
        ])
    return buf.getvalue()


def generate_frictionless(
    df: pd.DataFrame, columns: List[Dict], metadata: Dict, import_info: Dict
) -> str:
    raw_name = metadata.get('title') or import_info.get('filename', 'dataset')
    name_slug = re.sub(r'[^a-z0-9-]', '-', raw_name.lower()).strip('-')

    fields = []
    primary_keys = []

    for col in columns:
        field: Dict[str, Any] = {
            'name': col['name'],
            'type': col.get('data_type', 'string'),
        }
        desc = col.get('user_description') or col.get('description')
        if desc:
            field['description'] = desc

        unit = col.get('user_unit') or col.get('unit_guess')
        if unit:
            field['unit'] = unit

        constraints: Dict[str, Any] = {}
        if col.get('allowed_values'):
            constraints['enum'] = col['allowed_values']
        if col.get('required'):
            constraints['required'] = True
        if constraints:
            field['constraints'] = constraints

        if col.get('inferred_type') == 'identifier':
            primary_keys.append(col['name'])

        fields.append(field)

    schema: Dict[str, Any] = {'fields': fields}
    if primary_keys:
        schema['primaryKey'] = primary_keys[0] if len(primary_keys) == 1 else primary_keys

    package = {
        'profile': 'tabular-data-package',
        'name': name_slug,
        'title': metadata.get('title') or import_info.get('filename', 'Dataset'),
        'description': metadata.get('description') or '',
        'licenses': [{'name': metadata['license']}] if metadata.get('license') else [],
        'contributors': [{'title': metadata['creator']}] if metadata.get('creator') else [],
        'resources': [{'name': name_slug, 'path': 'cleaned_data.csv', 'schema': schema}],
    }
    return json.dumps(package, indent=2)


def generate_csvw(columns: List[Dict], metadata: Dict, import_info: Dict) -> str:
    col_specs = []
    primary_keys = []

    for col in columns:
        spec: Dict[str, Any] = {
            'name': col['name'],
            'titles': col.get('user_label') or col.get('label') or col['name'],
            'datatype': col.get('data_type', 'string'),
            'required': bool(col.get('required')),
        }
        desc = col.get('user_description') or col.get('description')
        if desc:
            spec['dc:description'] = desc
        unit = col.get('user_unit') or col.get('unit_guess')
        if unit:
            spec['schema:unitText'] = unit
        if col.get('uri'):
            spec['propertyUrl'] = col['uri']
        col_specs.append(spec)
        if col.get('inferred_type') == 'identifier':
            primary_keys.append(col['name'])

    table_schema: Dict[str, Any] = {'columns': col_specs}
    if primary_keys:
        table_schema['primaryKey'] = primary_keys

    csvw = {
        '@context': ['http://www.w3.org/ns/csvw', {'@language': 'en'}],
        'url': 'cleaned_data.csv',
        'dc:title': metadata.get('title') or import_info.get('filename', 'Dataset'),
        'dc:description': metadata.get('description') or '',
        'dc:creator': metadata.get('creator') or '',
        'dc:license': metadata.get('license') or '',
        'tableSchema': table_schema,
    }
    return json.dumps(csvw, indent=2)


def generate_jsonld(
    columns: List[Dict],
    metadata: Dict,
    import_info: Dict,
    uri_suggestions: Dict,
) -> str:
    base_uri = (metadata.get('base_uri') or 'https://your-lab.org').rstrip('/')
    dataset_uri = (
        uri_suggestions.get('dataset_level', {}).get('dataset_uri')
        or f'{base_uri}/dataset/dataset'
    )

    variables = []
    for col in columns:
        if col.get('inferred_type') == 'measurement':
            var: Dict[str, Any] = {
                '@id': col.get('uri') or f'{base_uri}/variable/{col["name"]}',
                '@type': 'schema:PropertyValue',
                'schema:name': col['name'],
            }
            desc = col.get('user_description') or col.get('description')
            if desc:
                var['schema:description'] = desc
            unit = col.get('user_unit') or col.get('unit_guess')
            if unit:
                var['schema:unitText'] = unit
            variables.append(var)

    jsonld = {
        '@context': {
            'schema': 'https://schema.org/',
            'dc': 'http://purl.org/dc/terms/',
            'obo': 'http://purl.obolibrary.org/obo/',
            'ex': f'{base_uri}/',
        },
        '@id': dataset_uri,
        '@type': 'schema:Dataset',
        'schema:name': metadata.get('title') or import_info.get('filename', 'Dataset'),
        'schema:description': metadata.get('description') or '',
        'schema:creator': {
            '@type': 'schema:Person',
            'schema:name': metadata.get('creator') or 'Unknown',
            'schema:email': metadata.get('contact_email') or '',
            'schema:affiliation': metadata.get('institution') or '',
        },
        'schema:dateCreated': metadata.get('date_created') or datetime.now().strftime('%Y-%m-%d'),
        'schema:version': metadata.get('version') or '1.0',
        'schema:license': metadata.get('license') or '',
        'schema:encodingFormat': 'text/csv',
        'schema:keywords': metadata.get('keywords') or [],
        'schema:variableMeasured': variables,
        'schema:isBasedOn': metadata.get('protocol_reference') or '',
        'schema:about': metadata.get('species') or '',
    }
    return json.dumps(jsonld, indent=2)


def generate_fair_report(
    import_info: Dict,
    columns: List[Dict],
    table_structure: Dict,
    fair_score: Dict,
    metadata: Dict,
    issues: List[Dict],
) -> str:
    lines = []
    title = metadata.get('title') or import_info.get('filename', 'Untitled')
    lines += [
        '# FAIR-Readiness Report',
        '',
        f'**Dataset:** {title}',
        f'**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        f'**FAIR-Readiness Score: {fair_score["fair_score"]} / 100**',
        '',
        '> This report is a FAIR-readiness assessment only. It does not constitute legal or regulatory certification.',
        '',
    ]

    lines += [
        '## 1. Dataset Summary',
        '',
        '| Property | Value |',
        '|---|---|',
        f'| Filename | {import_info.get("filename")} |',
        f'| Rows | {import_info.get("n_rows")} |',
        f'| Columns | {import_info.get("n_columns")} |',
        f'| Encoding | {import_info.get("encoding")} |',
        f'| Delimiter | `{import_info.get("delimiter")}` |',
        '',
    ]

    ts = table_structure
    lines += [
        '## 2. Detected Table Structure',
        '',
        f'- **Table shape:** {ts.get("table_shape", "unknown")}',
        f'- **Row represents:** {ts.get("row_represents", "unknown")}',
        f'- **Primary entity:** {ts.get("primary_entity", "unknown")}',
    ]
    if ts.get('secondary_entity'):
        lines.append(f'- **Secondary entity:** {ts["secondary_entity"]}')
    lines += [
        f'- **Detected identifiers:** {", ".join(ts.get("detected_identifiers") or []) or "None"}',
        f'- **Detected measurements:** {", ".join(ts.get("detected_measurements") or []) or "None"}',
        '',
    ]

    lines += [
        '## 3. FAIR-Readiness Score',
        '',
        '| Dimension | Score | Max | Main Weakness |',
        '|---|---|---|---|',
    ]
    for dim in ['findable', 'accessible', 'interoperable', 'reusable']:
        d = fair_score[dim]
        lines.append(f'| {dim.capitalize()} | {d["score"]} | {d["max_score"]} | {d["main_weakness"]} |')
    lines += [f'| **Total** | **{fair_score["fair_score"]}** | **100** | |', '']

    sev_order = {'high': 0, 'medium': 1, 'low': 2}
    sorted_issues = sorted(issues, key=lambda x: sev_order.get(x['severity'], 3))
    lines += ['## 4. Data Quality Issues', '']
    if sorted_issues:
        for issue in sorted_issues:
            icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(issue['severity'], '⚪')
            col_str = f' (`{issue["column"]}`)'if issue.get('column') else ''
            lines += [
                f'### {icon} {issue["problem"]}{col_str}',
                '',
                f'**Why it matters:** {issue["why_it_matters"]}',
                '',
                f'**Suggested fix:** {issue["suggested_fix"]}',
                '',
            ]
    else:
        lines += ['No major issues detected.', '']

    lines += [
        '## 5. Column Summary',
        '',
        '| Column | Semantic Type | Data Type | Unit | Missing % |',
        '|---|---|---|---|---|',
    ]
    for col in columns:
        unit = col.get('user_unit') or col.get('unit_guess') or '—'
        lines.append(
            f'| {col["name"]} | {col.get("inferred_type", "—")} '
            f'| {col.get("data_type", "—")} | {unit} | {col.get("missing_pct", 0)}% |'
        )
    lines.append('')

    lines += ['## 6. Recommended Next Actions', '']
    for i, rec in enumerate(fair_score.get('main_recommendations', []), 1):
        lines.append(f'{i}. {rec}')
    lines.append('')

    lines += [
        '## 7. Generated Export Files',
        '',
        '- `original_data.csv` — Original uploaded file',
        '- `cleaned_data.csv` — Normalized column names and values',
        '- `data_dictionary.csv` — Column-level metadata',
        '- `datapackage.json` — Frictionless Table Schema',
        '- `csvw_metadata.json` — W3C CSVW metadata',
        '- `metadata.jsonld` — JSON-LD dataset description',
        '- `fair_readiness_report.md` — This report',
        '',
        '---',
        '*Generated by FAIR CSV Mentor — FAIR-readiness assessment tool*',
    ]
    return '\n'.join(lines)


def generate_rocrate_zip(
    original_csv: bytes,
    cleaned_csv: str,
    data_dict: str,
    frictionless_json: str,
    csvw_json: str,
    jsonld_str: str,
    report_md: str,
    metadata: Dict,
    import_info: Dict,
    uri_suggestions: Dict,
) -> bytes:
    base_uri = (metadata.get('base_uri') or 'https://your-lab.org').rstrip('/')
    dataset_uri = (
        uri_suggestions.get('dataset_level', {}).get('dataset_uri')
        or f'{base_uri}/dataset/dataset'
    )

    file_entries = [
        ('original_data.csv', 'Original data file', 'text/csv'),
        ('cleaned_data.csv', 'Cleaned data file with normalized columns', 'text/csv'),
        ('data_dictionary.csv', 'Data dictionary', 'text/csv'),
        ('datapackage.json', 'Frictionless Data Package descriptor', 'application/json'),
        ('csvw_metadata.json', 'CSVW metadata', 'application/json'),
        ('metadata.jsonld', 'JSON-LD dataset metadata', 'application/ld+json'),
        ('fair_readiness_report.md', 'FAIR-readiness report', 'text/markdown'),
    ]

    ro_crate = {
        '@context': 'https://w3id.org/ro/crate/1.2/context',
        '@graph': [
            {
                '@type': 'CreativeWork',
                '@id': 'ro-crate-metadata.json',
                'conformsTo': {'@id': 'https://w3id.org/ro/crate/1.2'},
                'about': {'@id': dataset_uri},
            },
            {
                '@id': dataset_uri,
                '@type': 'Dataset',
                'name': metadata.get('title') or import_info.get('filename', 'Dataset'),
                'description': metadata.get('description') or '',
                'datePublished': metadata.get('date_created') or datetime.now().strftime('%Y-%m-%d'),
                'license': metadata.get('license') or '',
                'author': {'@type': 'Person', 'name': metadata.get('creator') or 'Unknown'},
                'hasPart': [{'@id': name} for name, _, _ in file_entries],
            },
            *[
                {'@id': name, '@type': 'File', 'name': desc, 'encodingFormat': fmt}
                for name, desc, fmt in file_entries
            ],
        ],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('ro-crate-metadata.json', json.dumps(ro_crate, indent=2))
        zf.writestr('original_data.csv', original_csv)
        zf.writestr('cleaned_data.csv', cleaned_csv)
        zf.writestr('data_dictionary.csv', data_dict)
        zf.writestr('datapackage.json', frictionless_json)
        zf.writestr('csvw_metadata.json', csvw_json)
        zf.writestr('metadata.jsonld', jsonld_str)
        zf.writestr('fair_readiness_report.md', report_md)
    return buf.getvalue()
