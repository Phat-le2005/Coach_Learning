"""Content-checked record checkpoints independent of worker lifetime."""
from pathlib import Path
from functools import lru_cache

from ...storage import file_hash, read_json, write_json
from ..transcript_batch import content_hash


def record_name(question_id):
    return 'q-' + content_hash(question_id)[:24] + '.json'


@lru_cache(maxsize=1)
def record_validator():
    from jsonschema import Draft202012Validator
    return Draft202012Validator(read_json(Path(__file__).with_name('record.schema.json')))


def asset_hashes(row):
    assets = {}
    for formula in row['formula_candidates']:
        assets[formula['asset_path']] = formula['asset_sha256']
    for table in row.get('tables', []):
        assets[table['asset_path']] = table['asset_sha256']
        for cell in table['cells']:
            if cell.get('asset_path'):
                assets[cell['asset_path']] = cell['asset_sha256']
    for figure in row.get('figures', []):
        assets[figure['asset_path']] = figure['asset_sha256']
    for part in row['parts'].values():
        for fragment in part['fragments']:
            assets[fragment['source_asset']] = fragment['source_asset_sha256']
    return assets


def save_checkpoint(output, row):
    record_validator().validate(row)
    output = Path(output)
    name = record_name(row['question_id'])
    write_json(output / 'records' / name, row)
    checkpoint = {
        'question_id': row['question_id'],
        'checkpoint_identity': row['checkpoint_identity'],
        'record_sha256': file_hash(output / 'records' / name),
        'assets': asset_hashes(row),
        'catalog_entry': {'question_id': row['question_id'], 'number': row['collection_number'],
                          'label': row['source_label'], 'chapter_id': row['chapter_id'],
                          'chapter_title': row['chapter_title'], 'source_name': row['source']['name'],
                          'status': row['transcript_status'], 'issues': len(row['issues']),
                          'formulas': len(row['formula_candidates']), 'record': 'records/' + name},
    }
    write_json(output / 'checkpoints' / name, checkpoint)
    return checkpoint


def valid_checkpoint(output, question, identity, *, check_assets=True):
    output = Path(output)
    name = record_name(question['question_id'])
    path = output / 'records' / name
    manifest = output / 'checkpoints' / name
    try:
        expected = content_hash({'source_record': question, 'pipeline': identity})
        checkpoint = read_json(manifest)
        if checkpoint['question_id'] != question['question_id'] or checkpoint['checkpoint_identity'] != expected:
            return False
        if file_hash(path) != checkpoint['record_sha256']:
            return False
        row = read_json(path)
        if (row['checkpoint_identity'] != expected or row['pipeline_identity'] != identity
                or row['question_id'] != question['question_id'] or row['publishable'] is not False
                or row['academic_review'] != 'PENDING' or row['grading_support'] != 'NOT_ASSESSED'):
            return False
        if asset_hashes(row) != checkpoint['assets']:
            return False
        if check_assets:
            for relative, digest in checkpoint['assets'].items():
                asset = (output / relative).resolve()
                if not asset.is_relative_to((output / 'assets').resolve()) or file_hash(asset) != digest:
                    return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
