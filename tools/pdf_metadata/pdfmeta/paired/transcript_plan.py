"""Reproducible chapter/document-balanced transcription trials."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib


CHAPTERS = ('derivative_applications', 'integrals', 'grouped_statistics', 'probability')
SEED = 'toan12-transcription-batch-20261103-v1'


def rank(q, salt='sample'):
    return hashlib.sha256((SEED + ':' + salt + ':' + q['question_id']).encode()).hexdigest()


def select(records, count=100):
    if count < 4 or count % 4:
        raise ValueError('COUNT_MUST_BE_POSITIVE_MULTIPLE_OF_FOUR')
    selected = []
    for chapter in CHAPTERS:
        docs = defaultdict(list)
        for q in records:
            if q['chapter_id'] == chapter:docs[q['source']['sha256']].append(q)
        for rows in docs.values():rows.sort(key=rank)
        if sum(map(len, docs.values())) < count // 4:
            raise ValueError('NOT_ENOUGH_RECORDS_IN_CHAPTER: ' + chapter)
        # Round-robin across contributing PDFs, then deterministic order within.
        ordered = sorted(docs)
        while sum(q['chapter_id'] == chapter for q in selected) < count // 4:
            for key in ordered:
                if docs[key]:selected.append(docs[key].pop(0))
                if sum(q['chapter_id'] == chapter for q in selected) == count // 4:break
    evaluation = set()
    for chapter in CHAPTERS:
        rows = sorted((q for q in selected if q['chapter_id'] == chapter), key=lambda q: rank(q, 'evaluation'))
        evaluation.update(q['question_id'] for q in rows[:min(10, len(rows))])
    return {'schema_version': 'paired-transcript-selection/v1', 'seed': SEED,
            'count': len(selected), 'evaluation_count': len(evaluation),
            'chapter_counts': dict(Counter(q['chapter_id'] for q in selected)),
            'document_counts': dict(Counter(q['source']['sha256'] for q in selected)),
            'selection_policy': 'BALANCED_CHAPTERS_ROUND_ROBIN_CONTRIBUTING_PDFS_NO_OUTPUT_BASED_FILTER',
            'questions': [{'question_id': q['question_id'], 'collection_number': q['collection_number'],
                           'chapter_id': q['chapter_id'], 'source_sha256': q['source']['sha256'],
                           'evaluation': q['question_id'] in evaluation} for q in selected]}
