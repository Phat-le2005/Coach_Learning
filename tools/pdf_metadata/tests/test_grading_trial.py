from copy import deepcopy
import json
from pathlib import Path

import pytest
import sympy as sp
import pypdfium2 as pdfium

from pdfmeta.grading_trial.calculus import analyse,domain,rational,scalar
from pdfmeta.grading_trial.engine import build_reference,grade
from pdfmeta.grading_trial.scenarios import cases_for,run as run_suite
from pdfmeta.grading_trial.build import build,load,check
from pdfmeta.storage import file_hash,read_json,write_json,write_jsonl


COHORT=read_json(Path(__file__).parent/'fixtures/calculus-cohort-12.v1.json')
BY_NUMBER={s['source_number']:s for s in COHORT['cases']}


def attempt(spec):
    return {'question_id':spec['question_id'],'domain':deepcopy(spec['domain']),
            'steps':[{'criterion_id':k,'value':deepcopy(v)} for k,v in spec['reference_work'].items()]}


@pytest.mark.parametrize('number',[154,171,172,175,176,177,178,179,180,181])
def test_independently_transcribed_work_receives_full_sandbox_rubric(number):
    spec=BY_NUMBER[number];reference=build_reference(spec);result=grade(reference,attempt(spec))
    assert reference['eligibility']=='SANDBOX_REFERENCE_READY'
    assert result['score']==10 and not result['production_grade']
    assert all(c['status']=='PASS' for c in result['criteria'])


@pytest.mark.parametrize('number,issue',[(173,'SOURCE_MONOTONICITY_CLAIM_CONFLICT'),(182,'SOURCE_POINT_VALUES_CONFLICT')])
def test_source_internal_contradictions_block_even_correct_final_answers(number,issue):
    spec=BY_NUMBER[number];reference=build_reference(spec)
    assert reference['source_issues']==[issue]
    assert grade(reference,attempt(spec))['score'] is None
    assert grade(reference,attempt(spec))['status']=='HELD_SOURCE_CONFLICT'


def test_all_labelled_synthetic_scenarios_have_expected_scores_and_routing():
    count=0
    for spec in COHORT['cases']:
        reference=build_reference(spec)
        reference['reference_work']=spec['reference_work']
        reference['alternate_work']=spec.get('alternate_work',{})
        for case in cases_for(reference):
            result=grade(reference,case['request']);count+=1
            assert result['score']==case['expected_score'],case['scenario_id']
            assert result['status']==case['expected_status'],case['scenario_id']
            if case['expected_criterion']:
                assert next(c for c in result['criteria'] if c['criterion_id']==case['expected_criterion'])['status']==case['expected_criterion_status']
    assert count==149


@pytest.mark.parametrize('number,method',[(175,'polynomial_division'),(176,'polynomial_division'),
                                        (179,'rational_critical_ratio'),(180,'rational_critical_ratio'),(181,'rational_critical_ratio')])
def test_valid_source_shortcut_methods_do_not_require_unnecessary_root_and_coordinate_steps(number,method):
    spec=BY_NUMBER[number];request={'question_id':spec['question_id'],'domain':spec['domain'],
        'steps':[{'criterion_id':k,'value':deepcopy(v)} for k,v in spec['alternate_work'][method].items()]}
    result=grade(build_reference(spec),request)
    assert result['score']==10 and result['method']==method
    assert not result['dependency_warnings']


def test_stationary_inflection_does_not_split_a_strictly_increasing_interval():
    spec=deepcopy(BY_NUMBER[171]);spec.update(function_latex='y=x^3',domain={'intervals':[{'left':'-1','right':'1','left_open':True,'right_open':True}],'excluded':[]})
    result=analyse(spec)
    assert result['critical']==[0] and result['extrema']==[]
    assert result['increasing']==sp.Interval.open(-1,1)


def test_cancellation_preserves_original_poles_and_excludes_them_from_critical_points():
    spec=deepcopy(BY_NUMBER[173]);spec.update(function_latex='y=(x^2-1)/(x-1)',source_claims={})
    result=analyse(spec)
    assert result['critical']==[] and result['domain']==sp.S.Reals-sp.FiniteSet(1)
    assert result['answer']==1


def test_positive_current_domain_is_not_replaced_with_all_reals():
    spec=BY_NUMBER[154];reference=build_reference(spec);request=attempt(spec)
    request['domain']=deepcopy(BY_NUMBER[171]['domain'])
    result=grade(reference,request)
    assert result['score'] is None
    assert result['criteria'][0]['status']=='FAIL'
    assert {c['reason'] for c in result['criteria'][1:]}=={'DOMAIN_GATE_NOT_SATISFIED'}


def test_line_is_defined_on_all_reals_even_when_the_original_function_has_a_pole():
    spec=BY_NUMBER[179];reference=build_reference(spec);request=attempt(spec)
    next(s for s in request['steps'] if s['criterion_id']=='line')['value']='y=(6*x+13)*(x+3)/(x+3)'
    result=grade(reference,request)
    line=next(c for c in result['criteria'] if c['criterion_id']=='line')
    assert line['status']=='FAIL' and line['reason']=='NEW_UNDEFINED_POINT_IN_STEP_DOMAIN'
    assert result['score']==8


def test_derivative_may_cancel_only_factors_already_excluded_by_the_question():
    spec=BY_NUMBER[179];reference=build_reference(spec);request=attempt(spec)
    next(s for s in request['steps'] if s['criterion_id']=='derivative')['value']="y'=((3*x^2+18*x+20)/(x+3)^2)*(x+3)/(x+3)"
    assert grade(reference,request)['score']==10


@pytest.mark.parametrize('value,score',[('4,47',10),('2*sqrt(5)',10),('4.4700',10),('4.474',9),('4.48',9)])
def test_exact_geometry_and_requested_rounding_are_accepted_without_a_wide_tolerance(value,score):
    spec=BY_NUMBER[177];request=attempt(spec)
    next(s for s in request['steps'] if s['criterion_id']=='final')['value']=value
    assert grade(build_reference(spec),request)['score']==score


def test_missing_derivative_cannot_be_inferred_from_a_correct_final_answer():
    spec=BY_NUMBER[175];reference=build_reference(spec);request=attempt(spec)
    request['steps']=[s for s in request['steps'] if s['criterion_id']=='final']
    result=grade(reference,request)
    assert result['score']==2
    assert next(c for c in result['criteria'] if c['criterion_id']=='derivative')['status']=='MISSING'
    assert result['dependency_warnings']


def test_unknown_parser_case_is_unassessed_with_score_bounds_not_a_wrong_answer():
    spec=BY_NUMBER[171];request=attempt(spec)
    next(s for s in request['steps'] if s['criterion_id']=='derivative')['value']="y'=sin(x)"
    result=grade(build_reference(spec),request)
    assert result['score'] is None and (result['score_lower_bound'],result['score_upper_bound'])==(8,10)
    assert result['criteria'][1]['status']=='NOT_ASSESSED'


@pytest.mark.parametrize('mutation',['expected','weight','duplicate','unknown'])
def test_student_cannot_supply_the_reference_or_change_the_rubric(mutation):
    spec=BY_NUMBER[171];request=attempt(spec)
    if mutation=='expected':request['expected_answer']='999'
    elif mutation=='weight':request['steps'][0]['max_points']=100
    elif mutation=='duplicate':request['steps'].append(request['steps'][0])
    else:request['steps'].append({'criterion_id':'invented','value':'999'})
    with pytest.raises(ValueError):grade(build_reference(spec),request)


@pytest.mark.parametrize('value',['__import__(x)','1'*30,'sqrt(-1)','x'])
def test_scalars_are_bounded_finite_real_constants(value):
    with pytest.raises(ValueError):scalar(value)


def integration_fixture(tmp_path):
    job=tmp_path/'jobs'/('a'*24);job.mkdir(parents=True)
    pdf=pdfium.PdfDocument.new();page=pdf.new_page(600,800);page.close();pdf.save(job/'input.pdf');pdf.close()
    with pdfium.PdfDocument(job/'input.pdf') as doc:
        image=job/'native/pages/page-001.png';image.parent.mkdir(parents=True);doc[0].render(scale=1).to_pil().save(image)
    spec=deepcopy(BY_NUMBER[175]);spec.update(question_id='test:q1',source_number=1)
    row={'question_id':spec['question_id'],'source_number':1,'source_metadata_file':str(job/'versions/v1/metadata/questions.jsonl'),
         'source_metadata':{'source':{'pdf_sha256':file_hash(job/'input.pdf'),'spans':[{'page_number':1,'bbox':[0,0,600,800]}]},
                           'student_view':{'stem_text_lossy':'synthetic unit test'},
                           'reference_solution':{'steps':[],'raw_text':'synthetic unit test'}},'latex_normalization':[]}
    final=job/'final/versions/v1/questions.final.jsonl';write_jsonl(final,[row]);write_json(job/'final.json',{'final_jsonl':str(final)})
    cohort=tmp_path/'cohort.json';write_json(cohort,{'source_pdf_sha256':file_hash(job/'input.pdf'),
        'selection':'TARGETED_DEVELOPMENT_COHORT_NOT_RANDOM_OR_HELDOUT','review_scope':'SYNTHETIC_UNIT_TEST_NOT_SOURCE_FIDELITY',
        'reviewed_page_images':[{'page_number':1,'sha256':file_hash(image)}],'cases':[spec]})
    return job,cohort,spec,final,image


def test_build_and_cli_adapter_preserve_raw_and_keep_score_only_in_sandbox(tmp_path):
    job,cohort,spec,final,_=integration_fixture(tmp_path);before=file_hash(final)
    report=build(job,cohort)
    assert report['ready_for_sandbox']==1 and report['academic_approved_count']==0
    result=check(job,attempt(spec));assert result['score']==10 and result['production_grade'] is False
    assert file_hash(final)==before
    assert run_suite(job)['assertions_failed']==0


@pytest.mark.parametrize('mutation',['package','source','pdf','image','grader'])
def test_hashes_reject_stale_or_changed_pilot_dependencies(tmp_path,mutation):
    job,cohort,_,final,image=integration_fixture(tmp_path);report=build(job,cohort)
    if mutation=='package':Path(report['package']).write_bytes(b'{}')
    elif mutation=='source':final.write_bytes(final.read_bytes()+b'\n')
    elif mutation=='pdf':(job/'input.pdf').write_bytes(b'changed')
    elif mutation=='image':
        package=Path(report['package']);row=json.loads(package.read_text(encoding='utf-8').splitlines()[0])
        (package.parent/row['source_images'][0]['path']).write_bytes(b'changed')
    else:
        report['grader_code']['engine.py']='0'*64;write_json(job/'grading-trial.json',report)
    with pytest.raises(ValueError):load(job)


def test_a_cohort_cannot_be_reused_with_a_different_pdf(tmp_path):
    job,cohort,_,_,_=integration_fixture(tmp_path);data=read_json(cohort);data['source_pdf_sha256']='0'*64;write_json(cohort,data)
    with pytest.raises(ValueError,match='HASH_MISMATCH'):build(job,cohort)
