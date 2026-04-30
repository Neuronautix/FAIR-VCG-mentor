import re
from typing import Dict, List, Any


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-') or 'dataset'


def suggest_uris(
    columns: List[Dict],
    metadata: Dict,
    import_info: Dict,
) -> Dict[str, Any]:
    base_uri = (metadata.get('base_uri') or 'https://your-lab.org').rstrip('/')
    title = metadata.get('title') or import_info.get('filename', 'dataset')
    dataset_slug = slugify(title)

    dataset_level: Dict[str, str] = {
        'dataset_uri': f'{base_uri}/dataset/{dataset_slug}',
        'observation_uri_pattern': f'{base_uri}/observation/{dataset_slug}/{{row_number}}',
    }

    for col in columns:
        if col['inferred_type'] == 'identifier':
            name = col['name']
            entity = (
                name.lower()
                .replace('_id', '')
                .replace('id_', '')
                .replace('id', '')
                .strip('_-')
            ) or 'entity'
            dataset_level[f'{entity}_uri_pattern'] = f'{base_uri}/{entity}/{{{name}}}'

    column_uris = {
        col['name']: f'{base_uri}/variable/{slugify(col["name"])}'
        for col in columns
    }

    return {
        'dataset_slug': dataset_slug,
        'dataset_level': dataset_level,
        'column_uris': column_uris,
    }
