"""Scale controls tested without model downloads or inference."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pdfmeta.storage import file_hash, read_json, write_json
from pdfmeta.paired.transcript_batch import content_hash
from pdfmeta.paired.transcription_v2 import batch, runner, supervisor
from pdfmeta.paired.transcription_v2.checkpoints import save_checkpoint, valid_checkpoint, record_name
from pdfmeta.paired.transcription_v2.engine import BoundedPages, CachedReader
from pdfmeta.paired.transcription_v2.exports import publish
from pdfmeta.paired.transcription_v2.selection import select_new, layout_hints


def question(number=1, chapter='integrals', digest='a'*64):
    return {'question_id': f'{chapter}:{number}', 'collection_number': number, 'source_label': f'Câu {number}',
            'chapter_id': chapter, 'chapter_title': chapter, 'source': {'sha256': digest, 'name': 'test.pdf'},
            **{role: {'source_spans': [{'page_number': 1, 'bbox': [0, 0, 20, 20]}],
                      'text_lossy': 'Bảng tần số' if number % 2 else 'đồ thị hình bên'}
               for role in ['question', 'solution', 'answer']}}


def draft(output, q, identity):
    asset = f"assets/q{q['collection_number']:04}/question-source.png"
    path = output / asset
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'test-only-image-bytes')
    part = {'markdown': 'test draft', 'choices': [], 'source_spans': q['question']['source_spans'],
            'fragments': [{'page_number': 1, 'bbox': [0, 0, 20, 20], 'source_asset': asset,
                           'source_asset_sha256': file_hash(path), 'markdown': 'test draft',
                           'blocks': [], 'coverage': {}}]}
    return {'schema_version': 'layout-first-transcription/v2', **{k: q[k] for k in
            ['question_id', 'collection_number', 'source_label', 'chapter_id', 'chapter_title', 'source']},
            'pipeline_identity': identity, 'checkpoint_identity': content_hash({'source_record': q, 'pipeline': identity}),
            'parts': {role: deepcopy(part) for role in ['question', 'solution', 'answer']},
            'tables': [], 'formula_candidates': [], 'figures': [], 'issues': [],
            'transcript_status': 'TEXT_AND_LATEX_DRAFT', 'academic_review': 'PENDING',
            'grading_support': 'NOT_ASSESSED', 'publishable': False,
            'runtime': {'seconds': 0, 'model_calls': 0, 'secondary_model_calls': 0,
                        'ocr_cache_hits': 0, 'rss_bytes': 1000, 'cloud_calls': 0}}


def test_new_selection_excludes_prior_ids_and_balances_chapter_document_layout():
    rows = [question(n + 100 * ch, chapter, str(n % 2) * 64)
            for ch, chapter in enumerate(['derivative_applications', 'integrals', 'grouped_statistics', 'probability'])
            for n in range(1, 21)]
    old = select_new(rows, 8)
    excluded = [q['question_id'] for q in old['questions']]
    new = select_new(rows, 16, excluded)
    assert new == select_new(list(reversed(rows)), 16, reversed(excluded))
    assert set(new['chapter_counts'].values()) == {4}
    assert not set(excluded) & {q['question_id'] for q in new['questions']}
    assert {'FIGURE_TEXT_HINT', 'TABLE_TEXT_HINT'} <= new['layout_hint_counts'].keys()
    assert new['layout_hints_are_source_text_heuristics']
    with pytest.raises(ValueError, match='NOT_ENOUGH'):
        select_new(rows, 16, [q['question_id'] for q in rows])


def test_multi_page_hint_uses_complete_question_solution_spans():
    q = question()
    q['solution']['source_spans'][0]['page_number'] = 2
    assert 'MULTI_PAGE' in layout_hints(q)
    tasks = runner.build_tasks([q], {}, Path('output'), Path('runtime'), Path('katex'), 'id', {},
                              chunk_size=1, cache_mode='cold', max_page_cache=2, invocation='test')
    assert tasks[0]['payload']['items'][0]['solution']['source_spans'][0]['page_number'] == 2


def test_checkpoint_checks_both_record_bytes_and_source_images(tmp_path):
    q = question()
    row = draft(tmp_path, q, 'id')
    save_checkpoint(tmp_path, row)
    assert valid_checkpoint(tmp_path, q, 'id')
    assert not valid_checkpoint(tmp_path, q, 'different')
    path = tmp_path / 'records' / record_name(q['question_id'])
    path.write_text('{}', encoding='utf-8')
    assert not valid_checkpoint(tmp_path, q, 'id')
    save_checkpoint(tmp_path, row)
    (tmp_path / row['parts']['question']['fragments'][0]['source_asset']).write_bytes(b'changed')
    assert not valid_checkpoint(tmp_path, q, 'id')


def test_checkpoint_rejects_automatic_academic_approval(tmp_path):
    row = draft(tmp_path, question(), 'id')
    row['publishable'] = True
    with pytest.raises(Exception):
        save_checkpoint(tmp_path, row)


def test_bounded_page_cache_evicts_pdfplumber_cache_and_retains_lru():
    class Page:
        closed = False
        def close(self): self.closed = True
    class PDF:
        pages = [Page() for _ in range(4)]
    pdf = PDF()
    pages = BoundedPages(pdf, 2)
    pages[1], pages[2] = 'one', 'two'
    assert pages[1] == 'one'
    pages[3] = 'three'
    assert set(pages) == {1, 3} and pdf.pages[1].closed and pages.peak == 2


def test_cold_mode_disables_even_local_ocr_cache(tmp_path, monkeypatch):
    from pdfmeta.paired.math_recovery import FormulaReader
    monkeypatch.setattr(FormulaReader, '__init__', lambda self, runtime, output, model:
                        self.__dict__.update(output=Path(output), identity={'test': True}))
    calls = []
    monkeypatch.setattr(FormulaReader, 'read', lambda self, image, **kwargs: calls.append(kwargs) or 'x')
    image = tmp_path / 'image.png'
    image.write_bytes(b'fixture')
    cold = CachedReader(tmp_path, tmp_path, 'test', {}, 'cold')
    cold.read(image)
    assert calls == [{'use_cache': False}] and cold.reused == 0


def test_streamed_exports_include_only_valid_ids_and_remain_drafts(tmp_path):
    q = question()
    save_checkpoint(tmp_path, draft(tmp_path, q, 'id'))
    selection = {'count': 2, 'evaluation_count': 1, 'questions': [
        {'question_id': q['question_id'], 'collection_number': 1, 'evaluation': True},
        {'question_id': 'missing', 'collection_number': 2, 'evaluation': False}]}
    report = publish(tmp_path, selection, 'id', 'source', {q['question_id']}, status='INCOMPLETE_DRAFT')
    assert report['completed_questions'] == 1 and report['selected_questions'] == 2
    assert report['full_grading_ready'] is False
    assert len(read_json(tmp_path / 'content.draft.pretty.json')) == 1
    assert json.loads((tmp_path / 'content.draft.jsonl').read_text(encoding='utf-8'))['publishable'] is False


@pytest.mark.parametrize('status,expected', [('COMPLETE_DRAFT', 0), ('PLANNED', 0),
    ('PAUSED_DRAFT', 3), ('INCOMPLETE_DRAFT', 1), ('SOURCE_INTEGRITY_FAILED', 1)])
def test_cli_exit_code_distinguishes_incomplete_and_paused(monkeypatch, status, expected):
    monkeypatch.setattr(batch, 'run', lambda args: {'status': status})
    assert batch.main(['--input', 'x', '--plan', 'p', '--output', 'o', '--runtime', 'r', '--katex', 'k']) == expected


def test_worker_hang_is_terminated_and_error_is_persisted(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    processes = []
    def launch(command, **kwargs):
        child = real_popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
        processes.append(child)
        return child
    monkeypatch.setattr(supervisor.subprocess, 'Popen', launch)
    task = {'chunk_id': 'hang', 'task_path': str(tmp_path / 'chunks/hang/task.json'), 'payload': {}}
    result = supervisor.execute_chunks([task], tmp_path, workers=1, chunk_timeout=.3,
        run_timeout=10, memory_limit_mb=0, min_free_disk_mb=0)
    assert result['chunks'][0]['error'] == 'CHUNK_TIMEOUT'
    assert processes[0].poll() is not None
    assert read_json(tmp_path / 'chunks/hang/supervision.json')['error'] == 'CHUNK_TIMEOUT'


def test_nonzero_worker_exit_does_not_look_like_success(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    monkeypatch.setattr(supervisor.subprocess, 'Popen', lambda command, **kwargs:
                        real_popen([sys.executable, '-c', 'raise SystemExit(7)'], **kwargs))
    task = {'chunk_id': 'fail', 'task_path': str(tmp_path / 'chunks/fail/task.json'), 'payload': {}}
    result = supervisor.execute_chunks([task], tmp_path, workers=1, min_free_disk_mb=0)
    assert result['chunks'][0]['exit_code'] == 7


def test_resume_uses_checkpoints_without_starting_model_workers(tmp_path, monkeypatch):
    q = question()
    source = tmp_path / 'input.jsonl'
    source.write_text(json.dumps(q) + '\n', encoding='utf-8')
    pdf = tmp_path / 'test.pdf'
    pdf.write_bytes(b'test-only-pdf-hash')
    digest = file_hash(pdf)
    q['source']['sha256'] = digest
    source.write_text(json.dumps(q) + '\n', encoding='utf-8')
    plan = tmp_path / 'plan.json'
    write_json(plan, {'documents': [{'path': str(pdf), 'sha256': digest}]})
    selection = tmp_path / 'selection.json'
    write_json(selection, {'count': 1, 'evaluation_count': 0, 'canonical_metadata_sha256': file_hash(source),
        'questions': [{'question_id': q['question_id'], 'collection_number': 1,
                       'source_sha256': digest, 'evaluation': False}]})
    runtime, katex, output = tmp_path / 'runtime', tmp_path / 'katex', tmp_path / 'output'
    katex.mkdir();(katex / 'katex.js').write_text('test-only', encoding='utf-8')
    for model in ['PP-FormulaNet_plus-M', 'PP-FormulaNet_plus-S']:
        path = runtime / 'paddlex/official_models' / model / 'inference.pdiparams'
        path.parent.mkdir(parents=True);path.write_bytes(b'test-only-weights-hash')
    monkeypatch.setattr(runner, 'inference_versions', lambda: {'test-only': 'not-inference'})
    monkeypatch.setattr(runner, 'viewer', lambda *args: None)
    class Syntax:
        def __init__(self, *args): pass
        def __call__(self, *args): return {'status': 'PASS'}
        def close(self): pass
    monkeypatch.setattr(runner, 'Syntax', Syntax)
    calls = []
    def execute(tasks, output, **kwargs):
        calls.append(len(tasks))
        for task in tasks:
            for row in task['payload']['items']:
                save_checkpoint(output, draft(output, row, task['payload']['identity']))
        return {'chunks': [], 'elapsed_seconds': .1, 'peak_process_tree_rss_bytes': 1000}
    monkeypatch.setattr(runner, 'execute_chunks', execute)
    argv = ['--input', str(source), '--plan', str(plan), '--selection', str(selection),
            '--output', str(output), '--runtime', str(runtime), '--katex', str(katex), '--cache-mode', 'cold']
    first = runner.run(batch.parser().parse_args(argv))
    record = output / 'records' / record_name(q['question_id'])
    before = file_hash(record)
    second = runner.run(batch.parser().parse_args(argv))
    assert first['status'] == second['status'] == 'COMPLETE_DRAFT'
    assert calls == [1, 0] and second['resumed_records_this_invocation'] == 1
    assert second['new_records_this_invocation'] == 0 and file_hash(record) == before
