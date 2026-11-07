from copy import deepcopy
import pytest

from pdfmeta.paired.source_book_replay import references,select_item,find_sources,id_reference,reference_rows
from pdfmeta.storage import file_hash


def test_book_provenance_preserves_original_pages_and_distinct_example_numbers():
    rows=references('Câu 007 Bài 25 | TL a2878305 | Trang nguồn 19, 20\n'
                    'Câu 008 Ví dụ 6.4.2 | TL 7fe3c16f | Trang nguồn 28',5)
    assert [(r['number'],r['label'],r['source_pages']) for r in rows]==[
        (7,'bai 25',[19,20]),(8,'vi du 6.4.2',[28])]
    assert rows[0]['book_page']==5


def test_page_captions_without_hash_and_original_page_do_not_resolve_a_source():
    assert references('Câu 7. Đề bài. Ví dụ 25 | Trang nguồn 19',1)==[]


def test_source_is_selected_by_content_hash_even_after_renaming(tmp_path):
    source=tmp_path/'renamed.pdf';source.write_bytes(b'original-pdf-bytes')
    prefix=file_hash(source)[:8]
    result=find_sources(tmp_path,[{'source_hash_prefix':prefix}])
    assert result[prefix]['sha256']==file_hash(source)
    with pytest.raises(ValueError,match='ORIGINAL_SOURCE_PDFS_MISSING'):
        find_sources(tmp_path,[{'source_hash_prefix':'00000000'}])


def item(page=5,solution_page=5):
    return {'source_label':'Ví dụ 7.','stem':{'text_raw':'Printed problem.',
        'source_spans':[{'page_number':page}]},'solution':{'text_raw':'Printed solution.',
        'source_spans':[{'page_number':solution_page}]},'answer':{'source_spans':[]}}


def test_original_label_and_page_are_required_without_rewriting_source_data():
    entry={'number':3,'label':'vi du 7','source_pages':[5]}
    rows=[item(page=2,solution_page=2),item()];before=deepcopy(rows)
    assert select_item(rows,entry) is rows[1]
    assert rows==before
    with pytest.raises(ValueError,match='SOURCE_ENTRY_NOT_UNIQUE'):select_item([item(),item()],entry)
    with pytest.raises(ValueError,match='EXCEEDS_BOOK_PAGE_REFERENCE'):
        select_item([item(solution_page=6)],entry)


def test_id_book_selects_coordinates_without_copying_expected_text():
    entry=id_reference('Câu 002 / Mã bộ gốc 4\nID: a287830565130826:q8:n8\nĐỀ BÀI',3)
    reference={'question_id':'a287830565130826:q8:n8','collection_number':4,
        'chapter_title':'Chapter','source':{'sha256':'a287830565130826'+'a'*48}}
    for role in ['question','solution','answer']:
        reference[role]={'markdown':'EXPECTED ANSWER MUST NOT BECOME INPUT',
            'raw_text_lossy':'EXPECTED RAW TEXT','source_spans':[{'page_number':5,'bbox':[0,10,100,20]}]}
    rows=reference_rows([entry],[reference]);row=rows[0]
    assert row['collection_number']==2 and row['source_book_reference']['original_collection_number']==4
    for role in ['question','solution','answer']:
        assert row[role]=={'text_lossy':'','source_spans':reference[role]['source_spans']}
    assert 'EXPECTED' not in str(row)


def test_id_reference_rejects_wrong_collection_number_and_full_source_prefix():
    entry=id_reference('Câu 002 / Mã bộ gốc 4\nID: a287830565130826:q8:n8',3)
    q={'question_id':entry['source_question_id'],'collection_number':5,
       'source':{'sha256':'a287830565130826'+'a'*48}}
    with pytest.raises(ValueError,match='COLLECTION_NUMBER_MISMATCH'):reference_rows([entry],[q])
    q['collection_number']=4;q['source']['sha256']='b'*64
    with pytest.raises(ValueError,match='SOURCE_HASH_MISMATCH'):reference_rows([entry],[q])
