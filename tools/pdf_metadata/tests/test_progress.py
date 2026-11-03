import json
import os
import threading
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

import pytest

from pdfmeta.progress import Progress, preparing_model, controller
from pdfmeta.progress.server import create_server, snapshot


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def extraction():
    return {'source_path': 'sample.pdf', 'page_count': 57, 'question_count': 120,
            'tables': {'count': 8}, 'workflow_fingerprint': 'v1',
            'ocr_cache_hits': 4, 'stage_cache_hits': 2}


def test_live_handoff_and_scoped_review_do_not_claim_full_document(tmp_path):
    p = Progress(tmp_path / ('a' * 24))
    p.begin('sample.pdf')
    run_id = p.state['run_id']
    p.extract_event('stage', 'native-extraction')
    p.extract_event('native_page', {'done': 8, 'total': 57})
    assert p.state['stages'][0]['done'] == 8
    p.extract_event('cache', 'native-extraction')
    assert p.state['stages'][0]['status'] == 'cached'
    p.extracted(extraction())
    preparing_model(p.job)
    p = Progress(p.job)
    p.begin_document({'version': 'v1', 'report': extraction()}, 3, False)
    assert p.state['run_id'] == run_id
    p.document_event('[latex/qwen] 1/120 · q1')
    assert p.state['stages'][5]['done'] == 0
    p.document_event('[latex/qwen] 3/120 · q3')
    assert p.state['stages'][5]['done'] == 2
    p.latex_done({'formula_count': 20, 'question_count': 120,
                  'status_counts': {'NORMALIZED': 12}, 'cache_hits': 3})
    p.document_event('[pipeline] qwen-review')
    p.document_event('[qwen] 1/120 · câu 151')
    assert '1/3 trong lượt' in p.state['detail']
    p.document_event('[review/done] 2/3')
    assert p.state['stages'][6]['done'] == 2
    p.review_done({'status': 'PARTIAL', 'selected_count': 3, 'question_count': 120,
                   'completed_count': 3, 'status_counts': {'DEFERRED': 117}, 'cache_hits': 2})
    p.finish({'status': 'PARTIAL_DRAFT'})
    assert p.state['status'] == 'COMPLETED_PARTIAL'
    assert p.state['stages'][6]['done'] == p.state['stages'][6]['total'] == 3
    assert '117' in p.state['stages'][6]['detail']
    assert len((p.job / 'progress-events.jsonl').read_text(encoding='utf-8').splitlines()) > 5


def test_failure_cannot_overwrite_another_process(tmp_path):
    p = Progress(tmp_path / ('b' * 24)); p.begin('sample.pdf')
    p.state['owner']['pid'] = os.getpid() + 1000000
    p.fail(ValueError('test'))
    assert p.state['status'] == 'RUNNING'


def test_controller_skips_transient_windows_python_redirector(monkeypatch):
    import psutil
    class Process:
        def __init__(self, pid=None): self.pid = pid
        def name(self): return {1:'python.exe', 2:'powershell.exe'}[self.pid]
        def parents(self): return [Process(1), Process(2)]
        def create_time(self): return self.pid * 100
    monkeypatch.setattr(psutil, 'Process', Process)
    assert controller() == {'pid': 2, 'created': 200}


def test_dead_process_is_interrupted_without_rewriting_record(tmp_path):
    p = Progress(tmp_path / ('a' * 24)); p.begin('sample.pdf')
    p.state.update(owner={'pid': -1}, controller={'pid': -1},
                   updated_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    save(p.path, p.state)
    original = p.path.read_bytes()
    assert snapshot(p.job)['status'] == 'INTERRUPTED'
    assert p.path.read_bytes() == original


def stored_job(root):
    job = root / ('a' * 24)
    save(job / 'latest.json', {'version': 'v1', 'report': extraction()})
    (job / 'final.html').write_text('<h1>Result</h1>', encoding='utf-8')
    output = job / 'final' / 'versions' / 'v1' / 'questions.final.jsonl'
    output.parent.mkdir(parents=True); output.write_bytes(b'{}\n')
    save(job / 'final.json', {'status': 'PARTIAL_DRAFT', 'question_count': 120,
         'final_jsonl': str(output), 'effective_latex_status_counts': {'NORMALIZED': 12, 'UNRESOLVED': 8},
         'latex': {'formula_count': 20, 'cache_hits': 3}, 'status_counts': {'DEFERRED': 117},
         'qwen_review': {'status': 'PARTIAL', 'selected_count': 3, 'completed_count': 3}})
    return job


def test_legacy_results_are_real_saved_counts_not_fabricated_history(tmp_path):
    j = snapshot(stored_job(tmp_path))
    assert j['record_source'] == 'stored-report'
    assert j['started_at'] is None and not j['events']
    assert j['quality']['review_selected'] == 3
    assert j['quality']['questions'] == 120
    assert j['stages'][6]['total'] == 3
    assert j['counters']['normalized'] == 12


def test_rerun_keeps_old_result_but_hides_old_quality(tmp_path):
    job = stored_job(tmp_path)
    Progress(job).begin('sample.pdf')
    j = snapshot(job)
    assert j['result']['is_previous'] and j['result']['review']
    assert j['quality'] is None
    assert 'normalized' not in j['counters']


@pytest.fixture
def monitor(tmp_path):
    root = tmp_path / 'jobs'; root.mkdir()
    runtime = tmp_path / 'runtime'; runtime.mkdir()
    server = create_server(root, runtime, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    opener = build_opener(ProxyHandler({}))
    def request(path, **kwargs):
        return opener.open(Request(url + path, **kwargs), timeout=3)
    try: yield root, request
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_empty_monitor_and_static_ui(monitor):
    root, request = monitor
    with request('/api/jobs') as r: assert json.load(r)['jobs'] == []
    with request('/api/health') as r: assert json.load(r)['service'] == 'pdf-progress/v1'
    with request('/') as r:
        assert b'Trung t' in r.read()
        assert r.headers['Cache-Control'] == 'no-store'


def test_monitor_serves_results_and_rejects_writes_and_escape_paths(monitor):
    root, request = monitor; job = stored_job(root)
    with request('/api/jobs') as r:
        jobs = json.load(r)['jobs']
        assert len(jobs) == 1 and 'owner' not in jobs[0]
        link = jobs[0]['result']['jsonl']
    with request(link) as r: assert r.read() == b'{}\n'
    with request('/artifacts/' + job.name + '/final.html') as r: assert r.status == 200
    (job / 'collection.pdf').write_bytes(b'%PDF-1.7\n')
    with request('/artifacts/' + job.name + '/collection.pdf') as r:
        assert r.read() == b'%PDF-1.7\n'
        assert r.headers['Content-Type'] == 'application/pdf'
    for path, kwargs, expected in [
        ('/api/jobs', {'method': 'POST', 'data': b'{}'}, 405),
        ('/api/jobs', {'headers': {'Host': 'evil.example'}}, 403),
        ('/artifacts/' + job.name + '/%2e%2e/secret.json', {}, 403),
        ('/artifacts/' + job.name + '/.env', {}, 403),
        ('/artifacts/' + job.name + '/final', {}, 404),
        ('/artifacts/' + job.name + '/input.pdf', {}, 404),
    ]:
        with pytest.raises(HTTPError) as error: request(path, **kwargs)
        assert error.value.code == expected


def test_resource_view_does_not_load_inference_models(monitor):
    _, request = monitor
    with request('/api/jobs') as r: resources = json.load(r)['resources']
    assert resources['available'] and resources['process_count'] == 0
    assert not resources['model_loaded'] and resources['ram_mb'] == 0


def test_queue_evaluation_route_stays_inside_queue_storage(monitor):
    root, request = monitor
    queue = root.parent / 'pdf-queues' / ('b' * 24)
    save(queue / 'queue.json', {'queue_id': queue.name, 'status': 'COMPLETED', 'counts': {'COMPLETED': 1}, 'items': [{}]})
    (queue / 'evaluation.html').write_text('<h1>Evaluation</h1>', encoding='utf-8')
    save(queue.parent / 'latest.json', {'queue': str(queue / 'queue.json')})
    with request('/api/jobs') as r: link = json.load(r)['queue']['review']
    with request(link) as r: assert b'Evaluation' in r.read()
    with pytest.raises(HTTPError) as error: request('/queue/' + queue.name + '/%2e%2e/secret.json')
    assert error.value.code == 403
    save(queue.parent / 'latest.json', {'queue': str(root.parent / 'private.json')})
    with request('/api/jobs') as r: assert json.load(r)['queue'] is None


def test_image_worker_is_measured_without_exposing_its_owner_fields(monitor):
    from pdfmeta.progress import owner
    root, request = monitor; job = stored_job(root)
    save(job / 'readiness-status.json', {'status': 'RUNNING', 'owner': owner(), 'done': 1, 'total': 2})
    with request('/api/jobs') as r: result = json.load(r)
    assert result['jobs'][0]['readiness']['done'] == 1
    assert '_post_owner' not in result['jobs'][0]
    assert result['resources']['process_count'] == 1
