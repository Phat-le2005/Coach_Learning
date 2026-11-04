import json
from pathlib import Path

import pytest

from pdfmeta.assemble import assemble
from pdfmeta.paired.fast_native import extract,extract_page
from pdfmeta.paired.corpus import document
from pdfmeta.paired.corpus_layout import split_columns,restore
from pdfmeta.paired.corpus_merge import merge
from pdfmeta.storage import file_hash,write_json
from test_one_pdf_workflow import small_pdf
from test_paired_dataset import page


def source_pdf(tmp_path):
    p=tmp_path/'source.pdf'
    small_pdf(p,['Example 2. A worked example with enough source text to use the native route.',
        'Solution','Answer: 2','The printed solution is kept as source text without inferring a grading rubric.'])
    return p


def test_pdfium_cache_and_worked_example_keep_source_hash(tmp_path):
    pdf=source_pdf(tmp_path);first,pages=extract(pdf,tmp_path/'native');second,_=extract(pdf,tmp_path/'native')
    assert first['pages']==1 and second['cache_hits']==1
    assert first['source_sha256']==file_hash(pdf)
    items,_=assemble(pages,file_hash(pdf))
    assert len(items)==1 and items[0]['source_number']==2
    assert items[0]['source_label'].startswith('Example 2')


def test_pdfium_keeps_embedded_images_when_native_captions_exist(tmp_path):
    import pypdfium2 as pdfium
    from PIL import Image
    pdf=source_pdf(tmp_path)
    image_path=tmp_path/'exercise.jpg';Image.new('RGB',(200,100),'white').save(image_path)
    doc=pdfium.PdfDocument(pdf);pg=doc[0]
    try:
        image=pdfium.PdfImage.new(doc);image.load_jpeg(image_path,inline=True)
        image.set_matrix(pdfium.PdfMatrix(400,0,0,200,40,100));pg.insert_obj(image)
        pg.gen_content()
        record=extract_page(pg,1,file_hash(pdf),110)
        assert record['blocks']
        assert len(record['images'])==1
        assert record['images'][0]['bbox']==pytest.approx([40,record['height']-300,440,record['height']-100])
    finally:pg.close();doc.close()


def test_vietnamese_worked_example_keeps_full_printed_subnumber():
    items,_=assemble([page(1,['\uf046 Ví dụ 6.4.2','Giải','Lời giải nguồn.'])],'source')
    assert len(items)==1 and items[0]['source_number']==6
    assert '6.4.2' in items[0]['source_label']


def test_decorated_book_question_and_solution_labels_are_structural_markers():
    items,_=assemble([page(1,['» Câu 3. A printed source question.','\uf040 Lời giải','Printed proof.'])],'source')
    assert len(items)==1 and items[0]['source_number']==3
    assert items[0]['solution']['text_raw'].strip()=='Printed proof.'


def test_source_book_preserves_inner_label_without_splitting_its_pair():
    from copy import deepcopy
    from pdfmeta.auto_ocr import apply_section_hints
    from pdfmeta.paired.corpus_layout import source_book_labels
    source=page(1,['Câu 007','Bài 25 | TL a2878305 | Trang nguồn 19, 20',
        'Đề bài và lời giải nguồn','Bài 25. A printed exercise.','Gii','A printed proof.',
        'Câu 008','Ví dụ 9 | TL a2878305 | Trang nguồn 21',
        'Ví dụ 9. A different exercise.','Giài','A different proof.'])
    for i,b in enumerate(source['blocks']):b['bbox']=[40,40+i*20,550,54+i*20]
    original=deepcopy(source)
    prepared=source_book_labels(apply_section_hints(source))
    virtual,_,issues=split_columns([prepared]);items,_=assemble(virtual,'source')
    assert not issues and len(items)==2
    assert [q['source_number'] for q in items]==[7,8]
    assert 'Bài 25.' in items[0]['stem']['text_raw']
    assert 'Ví dụ 9.' in items[1]['stem']['text_raw']
    assert 'printed proof' in items[0]['solution']['text_raw']
    assert 'different proof' in items[1]['solution']['text_raw']
    assert source==original


def test_ordinary_adjacent_labels_are_not_merged_without_book_provenance():
    from pdfmeta.paired.corpus_layout import source_book_labels
    source=page(1,['Câu 7','A question without a solution.','Bài 25. Another question.',
        'Giải','A separate printed proof.'])
    prepared=source_book_labels(source)
    items,_=assemble([prepared],'source')
    assert len(items)==2 and [q['source_number'] for q in items]==[7,25]
    assert not any(b.get('source_book_inner_label') for b in prepared['blocks'])


def test_corpus_theory_and_decorated_sections_do_not_leak_into_solution():
    from pdfmeta.paired.boundaries import detach
    from pdfmeta.paired.corpus import CORPUS_HEADING
    for heading in ['\uf050Dạng 2.1. Bài toán tiếp theo','A. LÝ THUYẾT CHUNG.']:
        pages=[page(1,['Example 1. Printed question.','Solution','Printed proof.',heading,'Unrelated theory.'])]
        items,orphans=assemble(pages,'source')
        revised,unassigned,audit=detach(items,pages,orphans,heading_pattern=CORPUS_HEADING,title_size=20)
        assert len(audit)==1 and 'Printed proof.' in revised[0]['solution']['text_raw']
        assert 'Unrelated theory.' not in revised[0]['solution']['text_raw']
        assert any(b['text_raw']=='Unrelated theory.' for b in unassigned)


def test_pdfium_cache_cannot_mix_another_document(tmp_path):
    pdf=source_pdf(tmp_path);extract(pdf,tmp_path/'native')
    other=tmp_path/'other.pdf';small_pdf(other,['Câu 9. Another source file.'])
    with pytest.raises(ValueError,match='ANOTHER_PDF'):extract(other,tmp_path/'native')


def test_invalid_pdf_unicode_is_flagged_and_remains_utf8_serializable(tmp_path,monkeypatch):
    import pypdfium2 as p
    from pypdfium2 import raw
    pdf=source_pdf(tmp_path);old=raw.FPDFText_GetUnicode
    monkeypatch.setattr(raw,'FPDFText_GetUnicode',lambda tp,i:0xD800 if i==0 else old(tp,i))
    doc=p.PdfDocument(pdf);pg=doc[0]
    try:record=extract_page(pg,1,file_hash(pdf),110)
    finally:pg.close();doc.close()
    assert 'PDFIUM_INVALID_UNICODE_REPLACED' in record['blocks'][0]['review_flags']
    json.dumps(record,ensure_ascii=False).encode('utf-8')


def test_two_columns_are_distinct_regions_of_one_original_page():
    p=page(1,[]);p['blocks']=[]
    for col,x in enumerate([20,330]):
        for i,text in enumerate(['Câu 1. Separate column question.','Solution','Printed solution.']):
            p['blocks'].append({'block_id':f'c{col}-b{i}','text_raw':text,'bbox':[x,50+i*30,x+240,65+i*30],
                'glyphs':[],'review_flags':[],'is_margin':False})
    virtual,mapping,issues=split_columns([p]);items,_=assemble(virtual,'abc')
    assert len(virtual)==2 and not issues and len(items)==2
    left=restore(items[0]['stem']['source_spans'][0],mapping)
    right=restore(items[1]['stem']['source_spans'][0],mapping)
    assert left['page_number']==right['page_number']==1
    assert left['bbox'][2]<=right['bbox'][0] and left['column']==1 and right['column']==2


def test_whole_document_exports_only_solved_examples_with_original_coordinates(tmp_path):
    pdf=source_pdf(tmp_path);work=tmp_path/'doc';extract(pdf,work/'native')
    source={'path':str(pdf),'sha256':file_hash(pdf),'pages':1,'document_id':'example',
        'label':'Toan12/integrals/source.pdf','chapter':'integrals'}
    result=document(source,work,tmp_path/'runtime',use_ocr=False)
    assert result['selected_pairs']==1 and not result['ocr_calls']
    q=json.loads(Path(result['questions_jsonl']).read_text(encoding='utf-8'))
    assert q['source']['sha256']==file_hash(pdf) and q['chapter_id']=='integrals'
    assert q['collection_source_spans'][0]['page_number']==1 and q['publishable'] is False
    archive=tmp_path/'archive.zip';archive.write_bytes(b'unit test archive identity')
    root=tmp_path/'corpus';write_json(root/'profile.json',[source])
    import shutil
    target=root/'documents'/source['sha256'][:24];shutil.copytree(work,target)
    # Report paths intentionally point at the verified original work directory.
    merged=merge(root,tmp_path/'merged',archive)
    assert merged['documents_accounted_for']==1 and merged['selected_pairs']==1
    metadata=json.loads(Path(merged['metadata_json']).read_text(encoding='utf-8'))
    assert metadata['source']['kind']=='SOURCE_ARCHIVE_NOT_A_SINGLE_PDF'
    assert metadata['questions'][0]['source']['sha256']!=metadata['source']['sha256']


def test_printed_solution_label_with_only_student_writing_lines_is_not_solved(tmp_path):
    pdf=tmp_path/'blank.pdf';small_pdf(pdf,[
        'Example 1. A long printed question with enough text for the native route.',
        'Solution','................................................................................',
        '................................................................................'])
    work=tmp_path/'doc';extract(pdf,work/'native')
    source={'path':str(pdf),'sha256':file_hash(pdf),'pages':1,'document_id':'blank',
        'label':'integrals/blank.pdf','chapter':'integrals'}
    result=document(source,work,tmp_path/'runtime',use_ocr=False)
    assert result['question_occurrences']==1 and result['selected_pairs']==0
    queue=json.loads(Path(result['review_jsonl']).read_text(encoding='utf-8'))
    assert queue['reasons']==['BLANK_SOLUTION_WORKSPACE']


def test_merge_refuses_a_silently_missing_source(tmp_path):
    write_json(tmp_path/'root/profile.json',[{'document_id':'missing','sha256':'a'*64,'chapter':'integrals'}])
    with pytest.raises(ValueError,match='NOT_ACCOUNTED'):merge(tmp_path/'root',tmp_path/'out',tmp_path/'archive.zip')


def test_chapter_mapping_uses_known_labels_and_requires_an_explicit_unknown_group():
    from pdfmeta.paired.solved_workflow import chapter_for
    assert chapter_for('Toan12/integrals/source.pdf')=='integrals'
    assert chapter_for('bai-tap-xac-suat.pdf')=='probability'
    with pytest.raises(ValueError,match='CHAPTER_NOT_IDENTIFIED'):chapter_for('unfamiliar.pdf')
    assert chapter_for('unfamiliar.pdf','grouped_statistics')=='grouped_statistics'


def test_resume_rejects_changed_question_or_review_queue(tmp_path):
    from pdfmeta.paired.solved_workflow import cached_report
    work=tmp_path/'work';out=work/'solved';out.mkdir(parents=True)
    q=out/'questions.jsonl';q.write_text('{}\n',encoding='utf-8')
    review=out/'review.jsonl';review.write_text('{}\n',encoding='utf-8')
    source={'sha256':'a'*64}
    write_json(out/'report.json',{'source_pdf_sha256':source['sha256'],'source_code_hash':'v1',
        'questions_jsonl':str(q),'questions_sha256':file_hash(q),
        'review_jsonl':str(review),'review_sha256':file_hash(review)})
    assert cached_report(work,source,'v1')
    assert cached_report(work,source,'v2') is None
    review.write_text('changed\n',encoding='utf-8')
    assert cached_report(work,source,'v1') is None


def test_public_collection_workflow_resumes_without_rerunning_a_verified_document(tmp_path):
    from pdfmeta.paired.solved_workflow import run
    pdf=source_pdf(tmp_path);root=tmp_path/'collection';output=tmp_path/'export';runtime=tmp_path/'runtime'
    first=run(root,runtime,output,pdf,input_path=pdf,default_chapter='integrals')
    assert first['documents_accounted_for']==1 and first['selected_pairs']==1
    metadata=json.loads(Path(first['metadata_json']).read_text(encoding='utf-8'))
    assert metadata['source']['kind']=='PDF' and metadata['source']['sha256']==file_hash(pdf)
    second=run(root,runtime,output,pdf)
    assert second['metadata_sha256']==first['metadata_sha256']
    state=json.loads((root/'controller.json').read_text(encoding='utf-8'))
    assert state['completed'][0]['cached'] is True and state['pdf_export_pending'] is True


@pytest.mark.parametrize('role',['question','solution'])
def test_ocr_question_pairs_are_queued_without_being_exported_as_solved(tmp_path,role):
    from pdfmeta.storage import read_json,write_jsonl
    pdf=source_pdf(tmp_path);source={'path':str(pdf),'sha256':file_hash(pdf),'pages':1,
        'document_id':'ocr-trial','label':'integrals/ocr.pdf','chapter':'integrals'}
    root=tmp_path/'collection';work=root/'documents'/source['sha256'][:24]
    extract(pdf,work/'native');report=document(source,work,tmp_path/'runtime',use_ocr=False)
    q=json.loads(Path(report['questions_jsonl']).read_text(encoding='utf-8'))
    q[role]['source_spans'][0]['block_ids']=['p001-ocr-0001']
    write_jsonl(Path(report['questions_jsonl']),[q]);report['questions_sha256']=file_hash(Path(report['questions_jsonl']))
    write_json(work/'solved/report.json',report);write_json(root/'profile.json',[source])
    result=merge(root,tmp_path/'out',pdf)
    assert result['selected_pairs']==0 and result['unselected_occurrences']==1
    metadata=read_json(Path(result['metadata_json']))
    assert metadata['documents'][0]['selected_pairs']==0
    assert metadata['documents'][0]['source_adapter_selected_pairs']==1
    queued=json.loads((tmp_path/'out/review-queue.jsonl').read_text(encoding='utf-8'))
    assert queued['reasons']==['OCR_PAIR_REQUIRES_SOURCE_REVIEW']
    assert 'asset_path' not in queued['source_regions'][0]
    assert result['page_review_count']==1
