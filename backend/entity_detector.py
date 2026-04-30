from typing import List, Dict, Any, Optional
import pandas as pd


def detect_entity_structure(df: pd.DataFrame, columns: List[Dict]) -> Dict[str, Any]:
    identifiers = [c['name'] for c in columns if c['inferred_type'] == 'identifier']
    measurements = [c['name'] for c in columns if c['inferred_type'] == 'measurement']
    categoricals = [
        c['name'] for c in columns
        if c['inferred_type'] in ('biological_descriptor', 'experimental_condition', 'categorical')
    ]
    time_vars = [c['name'] for c in columns if c['inferred_type'] == 'time_variable']

    primary_entity = _infer_primary_entity(identifiers, columns)
    secondary_entity: Optional[str] = None
    table_shape = 'tabular_data'
    row_represents = 'one_row_per_record'

    if identifiers and time_vars:
        id_col = identifiers[0]
        if id_col in df.columns and df[id_col].duplicated().any():
            table_shape = 'repeated_measures_long_format'
            row_represents = f'{primary_entity}_timepoint_observation'
            secondary_entity = 'timepoint'
        else:
            table_shape = 'one_row_per_entity'
            row_represents = f'one_{primary_entity}'

    elif identifiers:
        id_col = identifiers[0]
        if id_col in df.columns:
            if df[id_col].duplicated().any():
                table_shape = 'repeated_measures'
                row_represents = f'{primary_entity}_observation'
            else:
                table_shape = 'one_row_per_entity'
                row_represents = f'one_{primary_entity}'

    elif len(measurements) > 5:
        table_shape = 'wide_measurement_format'
        row_represents = 'wide_format_observation'

    return {
        'table_shape': table_shape,
        'row_represents': row_represents,
        'primary_entity': primary_entity,
        'secondary_entity': secondary_entity,
        'detected_identifiers': identifiers,
        'detected_measurements': measurements,
        'detected_categoricals': categoricals,
        'detected_time_vars': time_vars,
    }


def _infer_primary_entity(identifiers: List[str], columns: List[Dict]) -> str:
    all_names = [c['name'].lower() for c in columns]
    combined = ' '.join(identifiers).lower() + ' ' + ' '.join(all_names)

    for keyword, entity in [
        ('animal', 'animal'),
        ('mouse', 'animal'),
        ('rat', 'animal'),
        ('subject', 'subject'),
        ('patient', 'patient'),
        ('sample', 'sample'),
        ('specimen', 'specimen'),
        ('cell', 'cell'),
        ('well', 'well'),
        ('participant', 'participant'),
    ]:
        if keyword in combined:
            return entity

    if identifiers:
        name = identifiers[0].lower()
        return name.replace('_id', '').replace('id_', '').replace('id', '').strip('_') or 'entity'

    return 'entity'
