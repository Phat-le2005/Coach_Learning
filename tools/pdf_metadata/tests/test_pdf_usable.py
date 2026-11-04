import json
from pathlib import Path

import pytest

from pdfmeta.curation import classify,explicit_answer
from pdfmeta.source_recheck import structure_issues
from pdfmeta.paired.transcription_v2.geometry import render
from pdfmeta.paired.transcription_v2.glyphs import glyph_lookup
from pdfmeta.paired.transcription_v2.layout import prepare
from pdfmeta.paired.transcript_regions import assemble
from pdfmeta.paired.transcript_batch import Syntax
from pdfmeta.paired.transcription_v2.checkpoints import record_name


def fixture():return json.loads((Path(__file__).parent/'fixtures/paired-absolute-choice-source.json').read_text(encoding='utf-8'))


def test_actual_pdf_absolute_delimiters_survive_integral_reconstruction():
    data=fixture();page=data['page']
    _,fs,_,_,_=prepare(page,data['spans']['solution'],[])
    f=next(f for f in fs if f['bbox'][0]<283<f['bbox'][2] and f['bbox'][1]>255)
    lookup=glyph_lookup(page)
    text,evidence=render([lookup[k] for k in f['source_glyph_keys']],page['vectors'])
    assert r'\left|' in text and r'\right|' in text and r'\int_{-2}^{2}' in text
    assert any(e['kind']=='ABSOLUTE_VALUE' for e in evidence)
    assert structure_issues('x^2-4',{'absolute_bars':[[1,2]]})==['SOURCE_STRUCTURE_MISSING_ABSOLUTE_BARS']
    from pdfmeta.source_layout import inspect
    copy=json.loads(json.dumps(page))
    for vector in copy['vectors']:
        if vector['bbox'][2]-vector['bbox'][0]<.9:vector['kind']='rect'
    assert inspect(copy,f['bbox'])['absolute_bars']


def test_minus_sign_loss_is_not_accepted_as_same_source():
    from pdfmeta.paired.transcript_quality import check_source_tokens
    assert 'SOURCE_MINUS_SIGNS_CHANGED' in check_source_tokens('x−2','x+2')


def test_actual_split_fraction_options_are_assigned_by_source_cells():
    data=fixture();page=data['page'];_,fs,rows,_,_=prepare(page,data['spans']['question'],[])
    lookup=glyph_lookup(page)
    for i,f in enumerate(fs):
        text,_=render([lookup[k] for k in f['source_glyph_keys']],page['vectors'])
        f.update(formula_id=str(i),display_latex=text,asset_path='assets/f.png')
    result=assemble(rows,fs)
    assert [c['label'] for c in result['choices']]==list('ABCD')
    for choice,num in zip(result['choices'],['32','40','16','8']):
        assert r'\frac{'+num+'}{3}' in choice['markdown']
        assert choice['markdown'].count(r'\frac')==1
    assert not result['choice_issues'] and 'Diện tích' in result['markdown']


def row():
    part=lambda text:{'markdown':text,'raw_text_lossy':text,'source_spans':[{'page_number':1}],
                      'fragments':[{'source_asset':'assets/a.png'}],'choices':[]}
    q={'parts':{'question':part('Câu hỏi'), 'solution':part('Chọn B.\nLời giải')},
       'issues':[],'formula_candidates':[],'tables':[]}
    q['parts']['question']['choices']=[{'label':label,'markdown':'Nội dung '+label} for label in 'ABCD']
    q['parts']['question']['raw_text_lossy']='Câu hỏi\nA. Một\nB. Hai\nC. Ba\nD. Bốn'
    return q


def test_source_label_is_candidate_only_and_whole_question_is_routed():
    q=row();group,reasons,answer=classify(q)
    assert group=='core_candidates' and answer['expected_label']=='B' and answer['academic_review']=='PENDING'
    q['issues']=[{'code':'UNCOVERED_SUSPECT_MATH_GLYPHS'}]
    assert classify(q)[0]=='core_candidates'
    assert classify(q,['SOURCE_ASSET_MISSING_OR_CHANGED'])[0]=='held_items'


def test_conflicting_answers_and_missing_sources_block_core_but_text_can_use_source_images():
    q=row();q['parts']['solution']['raw_text_lossy']='Chọn A.'
    assert explicit_answer(q) is None and classify(q)[0]=='image_reference'
    q=row();q['parts']['question']['choices'][0]['markdown']=' . '
    assert classify(q)[0]=='core_candidates'
    q=row();q['parts']['solution']['source_spans']=[]
    assert classify(q)[0]=='held_items'


def test_numeric_source_answer_does_not_require_perfect_solution_latex():
    from pdfmeta.curation import compare_source_answer
    q=row();q['parts']['answer']={'raw_text_lossy':'15.','markdown':'Đáp án: 15.',
        'source_spans':[{'page_number':1}],'fragments':[{'source_asset':'assets/answer.png'}]}
    q['issues']=[{'code':'FORMULA_CANDIDATES_HELD_FOR_SOURCE_REVIEW'}]
    group,reasons,answer=classify(q)
    assert group=='core_candidates' and answer['kind']=='NUMBER' and answer['expected_decimal']=='15'
    item={'usage_group':group,'answer_spec':answer}
    assert compare_source_answer(item,'15,0')['status']=='MATCHES_SOURCE_ANSWER'
    assert compare_source_answer(item,'14')['status']=='DIFFERS_FROM_SOURCE_ANSWER'
    assert compare_source_answer(item,'__import__(x)')['status']=='INVALID_ANSWER_FORMAT'


def test_conflicting_numeric_readings_units_and_grouping_are_not_guessed():
    from pdfmeta.curation import decimal_answer
    assert decimal_answer('1,6')==__import__('decimal').Decimal('1.6')
    assert decimal_answer('1.000') is None and decimal_answer('20 m') is None
    q=row();q['parts']['answer']={'raw_text_lossy':'15','markdown':'Đáp án: 16',
        'source_spans':[{'page_number':1}],'fragments':[{}]}
    q['parts']['solution']['raw_text_lossy']='Lời giải';q['parts']['solution']['markdown']='Lời giải'
    assert explicit_answer(q) is None


def test_source_replay_resolves_katex_path_and_checks_syntax_before_export(tmp_path,monkeypatch):
    import pdfmeta.source_recheck as replay
    from pdfmeta.storage import write_json
    plan=tmp_path/'plan.json';write_json(plan,{'documents':[]});seen=[]
    class Checker:
        def __init__(self,path):seen.append(path)
        def __call__(self,value):return {'status':'PASS'}
        def close(self):pass
    monkeypatch.setattr(replay,'Syntax',Checker)
    checker=replay.SourceReplay(plan,Path('frontend/node_modules/katex/dist'));checker.close()
    assert seen[0].is_absolute()


def test_answer_leak_overlap_and_missing_source_replay_do_not_reach_core():
    q=row();q['issues']=[{'code':'SOURCE_RECHECK_NOT_RUN'}]
    assert classify(q)[0]=='image_reference'
    q=row();q['parts']['question']['source_spans']=[{'page_number':1,'bbox':[0,0,100,100]}]
    q['parts']['answer']={'raw_text_lossy':'15','markdown':'Đáp án: 15','fragments':[{}],
                         'source_spans':[{'page_number':1,'bbox':[0,50,100,60]}]}
    assert classify(q)[0]=='held_items'


def test_blank_pdf_returns_page_references_without_inventing_questions(tmp_path):
    import pypdfium2 as pdfium
    from pdfmeta.dataset_workflow import run
    pdf=tmp_path/'unknown.pdf';doc=pdfium.PdfDocument.new()
    for _ in range(2):doc.new_page(600,800).close()
    doc.save(pdf);doc.close()
    result=run(pdf,tmp_path/'storage',Path(__file__).parents[3],profile='native')
    assert result['status']=='SOURCE_ONLY_NO_PAIRED_QUESTIONS'
    assert result['questions']==0 and result['page_references']==2 and result['cloud_api_calls']==0
