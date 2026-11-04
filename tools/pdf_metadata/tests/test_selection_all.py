import json

import pytest

from pdfmeta.paired.selection_cli import all_records
from pdfmeta.storage import file_hash, write_json


def source_file(tmp_path):
    rows = [{'question_id': f'{ch}:{n}', 'collection_number': i + 1, 'chapter_id': ch,
             'source': {'sha256': str(i % 2) * 64}}
            for i, (ch, n) in enumerate([(ch, n) for ch, count in [('a', 3), ('b', 11), ('new-topic', 1)]
                                        for n in range(count)])]
    source = tmp_path / 'input.jsonl'
    source.write_text('\n'.join(json.dumps(q) for q in rows), encoding='utf-8')
    return source


def test_all_selection_keeps_unequal_and_unfamiliar_chapters_without_trial_quotas(tmp_path):
    source = source_file(tmp_path)
    before = file_hash(source)
    selected = all_records(source, tmp_path / 'selection.json')
    assert selected['count'] == 15 and selected['chapter_counts'] == {'a': 3, 'b': 11, 'new-topic': 1}
    assert selected['evaluation_count'] == 14 and file_hash(source) == before
    assert all_records(source, tmp_path / 'selection.json') == selected


def test_all_selection_can_exclude_a_previous_trial_explicitly(tmp_path):
    source = source_file(tmp_path)
    old = tmp_path / 'old.json'
    write_json(old, {'questions': [{'question_id': 'a:0'}]})
    result = all_records(source, tmp_path / 'selection.json', exclusions=[old])
    assert result['count'] == 14 and 'a:0' not in {q['question_id'] for q in result['questions']}


def test_existing_frozen_selection_cannot_be_silently_replaced(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / 'selection.json'
    all_records(source, output)
    source.write_text(source.read_text(encoding='utf-8') + '\n' + json.dumps({
        'question_id': 'extra', 'collection_number': 99, 'chapter_id': 'a', 'source': {'sha256': 'a'*64}}), encoding='utf-8')
    with pytest.raises(ValueError, match='SELECTION_CHANGED'):
        all_records(source, output)


def test_selection_never_replaces_input_and_duplicate_ids_fail(tmp_path):
    source = source_file(tmp_path)
    with pytest.raises(ValueError, match='OVERWRITE'):
        all_records(source, source)
    first = source.read_text(encoding='utf-8').splitlines()[0]
    source.write_text(first + '\n' + first, encoding='utf-8')
    with pytest.raises(ValueError, match='DUPLICATE'):
        all_records(source, tmp_path / 'selection.json')
