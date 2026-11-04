"""Deterministic chapter/document/layout sampling before inference."""
from collections import Counter, defaultdict, deque
import hashlib
import re

from ..transcript_plan import CHAPTERS


def layout_hints(row):
    text = ' '.join(str(row.get(role, {}).get('text_lossy', row.get(role, {}).get('text_raw', '')))
                    for role in ('question', 'solution'))
    pages = {s['page_number'] for role in ('question', 'solution', 'answer')
             for s in row.get(role, {}).get('source_spans', [])}
    hints = []
    if len(pages) > 1:
        hints.append('MULTI_PAGE')
    if re.search(r'bảng|tần số|mẫu số liệu|biến thiên|thống kê', text, re.I):
        hints.append('TABLE_TEXT_HINT')
    if re.search(r'hình vẽ|đồ thị|hình bên|biểu đồ|hình sau', text, re.I):
        hints.append('FIGURE_TEXT_HINT')
    if not hints:
        hints.append('OTHER_TEXT_MATH')
    return hints


def select_new(records, count, excluded=(), seed='pdf-scale-trial-20261104'):
    if count < 4 or count % 4:
        raise ValueError('COUNT_MUST_BE_POSITIVE_MULTIPLE_OF_FOUR')
    excluded = set(excluded)
    rank = lambda row: hashlib.sha256((seed + ':' + row['question_id']).encode()).hexdigest()
    chosen = []
    for chapter in CHAPTERS:
        groups = defaultdict(lambda: defaultdict(list))
        for row in records:
            if row['chapter_id'] == chapter and row['question_id'] not in excluded:
                groups[row['source']['sha256']]['+'.join(layout_hints(row))].append(row)
        if sum(len(rows) for buckets in groups.values() for rows in buckets.values()) < count // 4:
            raise ValueError('NOT_ENOUGH_NEW_RECORDS_IN_CHAPTER: ' + chapter)
        documents = {}
        for digest, buckets in sorted(groups.items()):
            buckets = {key: deque(sorted(rows, key=rank)) for key, rows in sorted(buckets.items())}
            ordered = []
            while any(buckets.values()):
                for rows in buckets.values():
                    if rows:
                        ordered.append(rows.popleft())
            documents[digest] = deque(ordered)
        local = []
        while len(local) < count // 4:
            for rows in documents.values():
                if rows:
                    local.append(rows.popleft())
                if len(local) == count // 4:
                    break
        chosen.extend(local)
    evaluation = {row['question_id'] for chapter in CHAPTERS
                  for row in sorted((q for q in chosen if q['chapter_id'] == chapter), key=rank)[:10]}
    return {
        'schema_version': 'paired-transcript-selection/v2', 'seed': seed,
        'count': len(chosen), 'evaluation_count': len(evaluation),
        'chapter_counts': dict(Counter(q['chapter_id'] for q in chosen)),
        'document_counts': dict(Counter(q['source']['sha256'] for q in chosen)),
        'layout_hint_counts': dict(Counter(h for q in chosen for h in layout_hints(q))),
        'layout_hints_are_source_text_heuristics': True,
        'selection_policy': 'BALANCED_CHAPTERS_DOCUMENTS_LAYOUT_HINTS_EXCLUDE_PRIOR_IDS_NO_OUTPUT_FILTER',
        'excluded_question_ids': sorted(excluded),
        'questions': [{'question_id': q['question_id'], 'collection_number': q['collection_number'],
                       'chapter_id': q['chapter_id'], 'source_sha256': q['source']['sha256'],
                       'layout_hints': layout_hints(q), 'evaluation': q['question_id'] in evaluation} for q in chosen],
    }
