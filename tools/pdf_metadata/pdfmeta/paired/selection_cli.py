"""Freeze all paired records without imposing balanced trial quotas."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from ..storage import file_hash, read_json, write_json


def all_records(source, target, *, exclusions=()):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError('SELECTION_MUST_NOT_OVERWRITE_SOURCE')
    before = file_hash(source)
    excluded = {q['question_id'] for p in exclusions for q in read_json(Path(p))['questions']}
    selected, seen = [], set()
    with source.open(encoding='utf-8-sig') as stream:
        for line in stream:
            if not line.strip():
                continue
            q = json.loads(line)
            if q['question_id'] in seen:
                raise ValueError('DUPLICATE_SOURCE_QUESTION_ID')
            seen.add(q['question_id'])
            if q['question_id'] not in excluded:
                selected.append({'question_id': q['question_id'], 'collection_number': q['collection_number'],
                                 'chapter_id': q['chapter_id'], 'source_sha256': q['source']['sha256'],
                                 'evaluation': False})
    if not selected:
        raise ValueError('EMPTY_SELECTION')
    chapters = defaultdict(list)
    for item in selected:
        chapters[item['chapter_id']].append(item)
    for rows in chapters.values():
        ordered = sorted(rows, key=lambda q: hashlib.sha256(('all-records-eval-v1:' + q['question_id']).encode()).hexdigest())
        for item in ordered[:10]:
            item['evaluation'] = True
    selected.sort(key=lambda q: (q['collection_number'], q['question_id']))
    selection = {'schema_version': 'paired-transcript-selection/v2-all',
                 'canonical_metadata_sha256': before, 'seed': 'all-records-eval-v1',
                 'selection_policy': 'ALL_PAIRED_RECORDS_EXCLUDING_EXPLICIT_PRIOR_IDS_NO_CHAPTER_QUOTA',
                 'count': len(selected), 'evaluation_count': sum(q['evaluation'] for q in selected),
                 'chapter_counts': dict(Counter(q['chapter_id'] for q in selected)),
                 'document_counts': dict(Counter(q['source_sha256'] for q in selected)),
                 'excluded_question_ids': sorted(excluded), 'questions': selected}
    if file_hash(source) != before:
        raise ValueError('SOURCE_CHANGED_DURING_SELECTION')
    if target.exists() and read_json(target) != selection:
        raise ValueError('SELECTION_CHANGED_USE_NEW_OUTPUT')
    write_json(target, selection)
    return selection


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exclude-selection', type=Path, action='append', default=[])
    args = parser.parse_args()
    result = all_records(args.input, args.output, exclusions=args.exclude_selection)
    print(json.dumps({k: v for k, v in result.items() if k not in ('questions', 'excluded_question_ids')},
                     ensure_ascii=False, indent=2))
