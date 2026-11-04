import json
from pathlib import Path

import pytest

from pdfmeta.paired.transcript_plan import select
from pdfmeta.paired.transcript_regions import propose, assemble, crop_box
from pdfmeta.paired.transcript_quality import display_decision,check_source_tokens
from pdfmeta.paired.transcript_triage import prepare,validate
from pdfmeta.paired.transcript_batch import Syntax,trusted_native,publish
from pdfmeta.paired.transcript_audit import numeric_equality,inspect_record,inspect_assets,content_record


def fixture(name):return json.loads((Path(__file__).parent/'fixtures'/name).read_text(encoding='utf-8'))


def test_selection_is_balanced_reproducible_and_contains_all_contributing_pdfs():
    records=[]
    for ch in ['derivative_applications','integrals','grouped_statistics','probability']:
        for doc in range(3):
            for n in range(30):records.append({'question_id':f'{ch}:{doc}:{n}','collection_number':len(records)+1,
                'chapter_id':ch,'source':{'sha256':f'{ch}-{doc}'}})
    a=select(records);b=select(list(reversed(records)))
    assert a==b and a['count']==100 and a['evaluation_count']==40
    assert set(a['chapter_counts'].values())=={25} and len(a['document_counts'])==12


def test_question_choices_keep_A_C_and_integration_constant_without_control_markers():
    src=fixture('paired-integral-source-glyphs.json')
    formulas,rows,errors=propose(src['page'],src['question_span'])
    for i,f in enumerate(formulas):f.update(formula_id=str(i),latex_candidate=f['native_candidate'] or 'x',asset_path='assets/f.png')
    result=assemble(rows,formulas)
    assert [c['label'] for c in result['choices']]==list('ABCD')
    assert 'CHOICE_' not in json.dumps(result) and '\x00' not in json.dumps(result)
    assert 'Câu 33.' in result['markdown'] and 'là' in result['markdown']
    assert all(not c['markdown'].startswith(c['label']+'.') for c in result['choices'])


def test_numeric_fraction_choices_are_detected_without_an_equals_sign():
    src=fixture('paired-numeric-fractions.json')
    found,rows,errors=propose(src['page'],src['span'])
    assert len(found)==4 and not errors
    assert all(f['detector']=='SOURCE_NUMERIC_FRACTION_BAR' for f in found)
    owned=set()
    for f in found:
        assert not set(f['source_glyph_keys'])&owned
        owned.update(f['source_glyph_keys'])
        assert f['bbox'][3]-f['bbox'][1]>20


def test_table_rules_cannot_expand_a_tiny_formula_crop_to_the_entire_table():
    src=fixture('paired-integral-source-glyphs.json')
    found,rows,_=propose(src['page'],src['question_span'])
    region=found[0];page={**src['page'],'vectors':[{'kind':'line','bbox':[0,340,600,340]}]}
    crop=crop_box(page,region,src['question_span'],rows)
    assert crop[2]-crop[0]<100


def test_source_numbers_and_independent_model_agreement_are_required_before_display():
    assert check_source_tokens('450-250=200','450-350=200')==['SOURCE_DIGITS_CHANGED']
    signals={key:[] for key in ['absolute_bars','overlines','lower_glyphs','top_bars']}
    bad=display_decision('450-250=200','450-350=200','450-350=200',{'status':'PASS'},signals)
    assert bad['display_latex'] is None and 'SOURCE_DIGITS_CHANGED' in bad['issues']
    disagree=display_decision('x2','x^{2}','x^{3}',{'status':'PASS'},signals)
    assert disagree['display_latex'] is None
    ok=display_decision('x2','x^{2}','x^{2}',{'status':'PASS'},signals)
    assert ok['display_latex']=='x^{2}' and ok['publishable'] is False
    assert ok['academic_review']=='PENDING'


def test_missing_subscript_or_overline_is_held_even_when_both_models_agree():
    result=display_decision('A','A','A',{'status':'PASS'},{'overlines':[[0,0,1,1]]})
    assert result['display_latex'] is None


def test_empty_ocr_uses_image_in_the_markdown_and_keeps_original_prose():
    src=fixture('paired-integral-source-glyphs.json')
    formulas,rows,_=propose(src['page'],src['question_span'])
    for i,f in enumerate(formulas):f.update(formula_id=str(i),latex_candidate='WRONG',display_latex=None,asset_path='assets/held.png')
    value=assemble(rows,formulas)
    assert 'WRONG' not in json.dumps(value) and 'assets/held.png' in value['markdown']
    assert 'Họ nguyên hàm' in value['markdown']


def test_qwen_never_calls_truncated_metadata_clear_or_claims_source_images():
    record={'parts':{r:{'markdown':'x'*5000,'choices':[]} for r in ['question','solution','answer']},'issues':[],'formula_candidates':[]}
    data=prepare(record)
    assert data['truncated'] and not data['source_images_provided']
    with pytest.raises(ValueError,match='TRUNCATED'):
        validate({'verdict':'NO_ISSUE_FOUND','issues':[]},True)


def test_real_local_katex_dist_refuses_invalid_syntax_and_unsafe_macros():
    katex=Path(__file__).parents[3]/'frontend/node_modules/katex/dist'
    if not katex.exists():pytest.skip('Local KaTeX not installed')
    syntax=Syntax(katex)
    try:
        assert syntax(r'\frac{x^2}{2}')['status']=='PASS'
        assert syntax(r'\frac{x^2}{')['status']=='FAIL'
        assert syntax(r'\href{https://example.test}{x}')['status']=='FAIL'
    finally:syntax.close()


def test_reference_arithmetic_checks_are_bounded_and_preserve_a_wrong_printed_equation():
    assert numeric_equality('450-350=200')['status']=='INCONSISTENCY_CANDIDATE'
    assert numeric_equality(r'\frac{1}{2}=0.5')['status']=='PASS'
    assert numeric_equality('f(x)=x^2')['status']=='NOT_ASSESSED'
    assert numeric_equality('1=__import__(os)')['status']=='NOT_ASSESSED'
    f={'formula_id':'x','role':'question','display_latex':'1=2','method':'native','asset_path':'assets/source.png'}
    q={'question_id':'q','collection_number':1,'source':{'sha256':'a'*64},'formula_candidates':[f]}
    assert inspect_record(q)['checks']==[]
    f['role']='solution'
    result=inspect_record(q)
    assert result['checks'][0]['status']=='INCONSISTENCY_CANDIDATE'
    assert f['display_latex']=='1=2' and not result['publishable']


def test_transcript_schema_cannot_accept_ready_for_grading_or_published_content():
    from jsonschema import Draft202012Validator
    schema=json.loads((Path(__file__).parents[1]/'schemas/paired-transcript-draft.v1.schema.json').read_text())
    validator=Draft202012Validator(schema)
    part={'markdown':'','choices':[],'source_spans':[],'raw_text_lossy':None,'fragments':[]}
    q={'schema_version':'paired-transcript-draft/v1','question_id':'q','collection_number':1,
       'source':{'name':'source.pdf','sha256':'a'*64},'pipeline_identity':'b'*64,'checkpoint_identity':'c'*64,
       'parts':{r:part for r in ['question','solution','answer']},'formula_candidates':[],'issues':[],
       'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False}
    validator.validate(q)
    q['publishable']=True
    assert list(validator.iter_errors(q))


def test_previous_pipeline_records_cannot_leak_into_new_publication(tmp_path):
    (tmp_path/'records').mkdir()
    (tmp_path/'records/old.json').write_text(json.dumps({'question_id':'q','pipeline_identity':'old'}))
    selection={'count':4,'evaluation_count':4,'questions':[{'question_id':'q','evaluation':True}]}
    report=publish(tmp_path,selection,'new','a'*64,running=True)
    assert report['completed_questions']==0
    assert json.loads((tmp_path/'metadata.transcribed.draft.pretty.json').read_text())==[]


def test_missing_or_changed_source_assets_cannot_pass_artifact_audit(tmp_path):
    from pdfmeta.storage import file_hash
    (tmp_path/'assets').mkdir();p=tmp_path/'assets/source.png';p.write_bytes(b'original')
    q={'question_id':'q','formula_candidates':[{'asset_path':'assets/source.png','asset_sha256':file_hash(p)}],'parts':{}}
    assert inspect_assets(tmp_path,[q])['errors']==[]
    p.write_bytes(b'changed')
    assert inspect_assets(tmp_path,[q])['errors'][0]['issue']=='ASSET_HASH_MISMATCH'
    p.unlink()
    assert inspect_assets(tmp_path,[q])['errors'][0]['issue']=='ASSET_MISSING'


def test_content_projection_keeps_clean_fields_and_warnings_without_lossy_raw_text():
    part={'markdown':'$x^{2}$','choices':[{'label':'A','markdown':'$1$'}],
          'raw_text_lossy':'\uf028 broken font','fragments':[]}
    q={'question_id':'q','collection_number':1,'chapter_title':'Toán','source_label':'\uf046 Ví dụ 1.2',
       'parts':{r:part for r in ['question','solution','answer']},'source':{'sha256':'a'*64},
       'transcript_status':'SOURCE_REVIEW_REQUIRED','issues':[{'code':'UNCOVERED_SUSPECT_MATH_GLYPHS'}],
       'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False}
    clean=content_record(q)
    assert clean['question_markdown']=='$x^{2}$' and '\uf028' not in json.dumps(clean,ensure_ascii=False)
    assert clean['source_label']=='Ví dụ 1.2' and q['source_label']=='\uf046 Ví dụ 1.2'
    assert clean['issues']==q['issues'] and not clean['publishable']
    clean['choices'][0]['markdown']='changed'
    assert part['choices'][0]['markdown']=='$1$'
