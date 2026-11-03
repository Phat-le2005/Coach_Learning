import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from PIL import Image
import pytest

from pdfmeta.assemble import assemble
from pdfmeta.paired.dataset import compose, export, from_html, validate
from pdfmeta.paired.viewer import render


def page(number, texts):
    return {'page_number': number, 'width': 600, 'height': 800,
        'content_bounds': [0, 0, 600, 780], 'blocks': [
            {'block_id': f'p{number}-b{i}', 'text_raw': text,
             'bbox': [40, 40 + i * 30, 550, 56 + i * 30], 'review_flags': []}
            for i, text in enumerate(texts)]}


def payload(tmp_path, text='Câu 1. A question <script>alert(1)</script>'):
    pages = [page(1, [text, 'Lời giải', 'Trả lời: 0,8', 'Vậy kết luận của lời giải.']),
             page(2, ['Câu 1. Câu ở mục khác chưa có lời giải.'])]
    items, orphans = assemble(pages, 'a' * 64)
    assets = tmp_path / 'assets'; assets.mkdir(exist_ok=True)
    for index, item in enumerate(items):
        for role in ['stem', 'answer', 'solution']:
            for j, span in enumerate(item[role]['source_spans']):
                key = f'assets/item-{index}-{role}-{j}.png'
                Image.new('RGB', (16, 16), 'white').save(tmp_path / key)
                span['asset_path'] = key
    return compose(items, orphans, pages, {'name': 'test.pdf', 'sha256': 'a' * 64, 'page_count': 2}, tmp_path)


def test_response_label_inside_solution_is_an_answer_not_a_new_empty_response_area():
    items, _ = assemble([page(1, ['Câu 1. Đề bài.', 'Trả lời: …', 'Lời giải',
        'Trả lời: 6,67', 'Gọi A là một biến cố.', 'Vậy kết luận đúng theo nguồn.'])], 'a' * 64)
    assert items[0]['answer']['text_raw'] == '6,67'
    assert 'Gọi A' in items[0]['solution']['text_raw']
    assert 'Trả lời' not in items[0]['stem']['text_raw']


def test_empty_response_label_inside_solution_does_not_discard_following_text():
    items, _ = assemble([page(1, ['Câu 1. Đề bài.', 'Lời giải', 'Trả lời: …', 'Phần giải còn lại.'])], 'a' * 64)
    assert items[0]['answer']['text_raw'] is None
    assert 'Phần giải còn lại' in items[0]['solution']['text_raw']


def test_cross_page_solution_stays_with_original_question_and_ids_survive_number_reset():
    items, _ = assemble([page(1, ['Câu 1. Đề một.', 'Lời giải', 'Giải bắt đầu.']),
        page(2, ['Giải tiếp qua trang.', 'Trả lời: 2', 'Câu 1. Đề hai.', 'Lời giải', 'Giải thứ hai.'])], 'a' * 64)
    assert len({q['question_id'] for q in items}) == 2
    assert 'Giải tiếp qua trang' in items[0]['solution']['text_raw']
    assert 'Giải thứ hai' not in items[0]['solution']['text_raw']


def test_one_html_roundtrip_is_source_for_metadata_and_preserves_unpaired_records(tmp_path):
    data = payload(tmp_path)
    target = tmp_path / 'dataset.html'; render(target, data)
    assert from_html(target) == data
    assert '</script><script>alert(1)</script>' not in target.read_text(encoding='utf-8')
    result = export(target, tmp_path / 'new-export')
    metadata = json.loads(Path(result['metadata_json']).read_text(encoding='utf-8'))
    assert len(metadata['questions']) == 1
    assert metadata['questions'][0]['answer']['text_raw'] == '0,8'
    assert metadata['unpaired_questions'][0]['pair_status'] == 'MISSING_SOLUTION'
    assert len({q['question_id'] for q in metadata['questions'] + metadata['unpaired_questions']}) == 2
    assert len(Path(result['metadata_jsonl']).read_text(encoding='utf-8').splitlines()) == 1
    assert result['html_sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    for key, image in data['images'].items():
        assert hashlib.sha256((tmp_path / 'new-export' / key).read_bytes()).hexdigest() == image['sha256']
    assert all('data_url' not in im for im in metadata['images'].values())
    assert all(q['publishable'] is False for q in metadata['questions'])


@pytest.mark.parametrize('kind', ['bad_image', 'image_path_escape', 'outside_page', 'duplicate_id', 'fake_approval'])
def test_malformed_or_unsafe_conversion_cannot_export_metadata(tmp_path, kind):
    data = payload(tmp_path)
    key = next(iter(data['images']))
    if kind == 'bad_image': data['images'][key]['data_url'] = 'data:image/png;base64,' + base64.b64encode(b'wrong').decode()
    elif kind == 'image_path_escape': data['images']['../escape.png'] = data['images'].pop(key)
    elif kind == 'outside_page': data['questions'][0]['question']['source_spans'][0]['page_number'] = 9
    elif kind == 'duplicate_id': data['questions'][1]['question_id'] = data['questions'][0]['question_id']
    else: data['questions'][0]['publishable'] = True
    with pytest.raises(Exception): validate(data)


def test_image_only_page_is_reported_for_ocr_not_claimed_as_a_blank_complete_page(tmp_path):
    pages = [page(1, [])]
    data = compose([], [], pages, {'name': 'scan.pdf', 'sha256': 'b' * 64, 'page_count': 1}, tmp_path)
    assert data['questions'] == []
    assert data['page_coverage'][0]['status'] == 'OCR_REQUIRED'
    assert data['policy']['local_inference_calls'] == 0


def test_section_context_is_flagged_without_silently_cutting_source_text(tmp_path):
    pages = [page(1, ['Câu 7. Đề.', 'Lời giải', 'Một kết luận.', 'DẠNG 2. Bài tiếp theo.'])]
    items, orphans = assemble(pages, 'c' * 64)
    data = compose(items, orphans, pages, {'name': 'context.pdf', 'sha256': 'c' * 64, 'page_count': 1}, tmp_path)
    assert 'POSSIBLE_SECTION_CONTEXT_ATTACHED_TO_SOLUTION' in data['questions'][0]['quality_flags']
    assert 'DẠNG 2' in data['questions'][0]['solution']['text_lossy']


def test_real_conversion_and_resume_use_same_version_and_keep_pdf_bytes(tmp_path):
    from test_one_pdf_workflow import small_pdf
    from pdfmeta.paired.dataset import build
    pdf = tmp_path / 'synthetic.pdf'
    small_pdf(pdf, ['Câu 7. A synthetic question.', 'Solution', 'Answer: 2', 'A short printed solution.'])
    before = pdf.read_bytes()
    first = build(pdf, tmp_path / 'job')
    second = build(pdf, tmp_path / 'job')
    assert first['single_file_html'] == second['single_file_html']
    assert first['html_sha256'] == second['html_sha256']
    assert first['metadata_question_count'] == 1
    assert first['structural_errors'] == []
    assert pdf.read_bytes() == before
    assert (tmp_path / 'job/input.pdf').read_bytes() == before
