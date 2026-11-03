"""Synthetic, labelled perturbations, not measurements of real student accuracy."""
from copy import deepcopy
from collections import Counter
from pathlib import Path

from ..storage import read_json,write_json,write_jsonl
from .build import load
from .engine import grade


def cases_for(reference):
    base={'question_id':reference['question_id'],'domain':reference['source_domain'],
          'steps':[{'criterion_id':k,'value':v} for k,v in reference['reference_work'].items()]}
    def case(name,request,score,status='COMPLETE_SANDBOX_ASSESSMENT',criterion=None,criterion_status=None):
        return {'scenario_id':reference['question_id']+':'+name,'category':name,'request':request,
                'expected_score':score,'expected_status':status,'expected_criterion':criterion,
                'expected_criterion_status':criterion_status,'label_basis':'CONTROLLED_SYNTHETIC_PERTURBATION_OF_VISUALLY_REVIEWED_COHORT'}
    if reference['eligibility']!='SANDBOX_REFERENCE_READY':
        bad=deepcopy(base);next(s for s in bad['steps'] if s['criterion_id']=='final')['value']='999'
        return [case('source_conflict_correct_work',base,None,'HELD_SOURCE_CONFLICT'),
                case('source_conflict_wrong_work',bad,None,'HELD_SOURCE_CONFLICT')]
    result=[case('source_checked_work',base,10)]
    # Algebraically equivalent factorization is a positive metamorphic case.
    import sympy as sp
    from .calculus import rational
    equivalent=deepcopy(base);step=next(s for s in equivalent['steps'] if s['criterion_id']=='derivative')
    left,right=step['value'].split('=',1)
    parsed=rational(step['value'],reference['variable'])
    step['value']=left+'='+sp.sstr(sp.factor(parsed['expression']))
    result.append(case('equivalent_derivative',equivalent,10))
    wrong=deepcopy(base);next(s for s in wrong['steps'] if s['criterion_id']=='derivative')['value']=left+'=-('+right+')'
    result.append(case('wrong_derivative_sign',wrong,8,criterion='derivative',criterion_status='FAIL'))
    wrong=deepcopy(base);v=reference['variable'];changed=right.replace(v+'^2',v+'^3',1) if v+'^2' in right else right.replace(v,v+'^2',1)
    next(s for s in wrong['steps'] if s['criterion_id']=='derivative')['value']=left+'='+changed
    result.append(case('wrong_power',wrong,8,criterion='derivative',criterion_status='FAIL'))
    final_weight=next(c['max_points'] for c in reference['criteria'] if c['criterion_id']=='final')
    wrong=deepcopy(base);next(s for s in wrong['steps'] if s['criterion_id']=='final')['value']='('+reference['reference_work']['final']+')+1'
    result.append(case('wrong_final',wrong,10-final_weight,criterion='final',criterion_status='FAIL'))
    for key in ['derivative','critical_points']:
        missing=deepcopy(base);missing['steps']=[s for s in missing['steps'] if s['criterion_id']!=key]
        result.append(case('missing_'+key,missing,8,criterion=key,criterion_status='MISSING'))
    answer_only=deepcopy(base);answer_only['steps']=[s for s in answer_only['steps'] if s['criterion_id']=='final']
    result.append(case('final_answer_only',answer_only,1+final_weight,criterion='derivative',criterion_status='MISSING'))
    missing=deepcopy(base);missing.pop('domain')
    result.append(case('missing_domain',missing,None,'NEEDS_REVIEW',criterion='domain',criterion_status='NOT_ASSESSED'))
    wrong=deepcopy(base)
    if reference['source_domain'].get('excluded') or reference['source_domain']['intervals'][0]['left']!='-inf':
        wrong['domain']={'intervals':[{'left':'-inf','right':'inf','left_open':True,'right_open':True}],'excluded':[]}
    else:wrong['domain']['excluded']=['101']
    result.append(case('wrong_domain',wrong,None,'NEEDS_REVIEW',criterion='domain',criterion_status='FAIL'))
    hole=deepcopy(base);next(s for s in hole['steps'] if s['criterion_id']=='derivative')['value']=left+'=('+right+')*('+v+'-101)/('+v+'-101)'
    result.append(case('cancelled_factor_new_hole',hole,8,criterion='derivative',criterion_status='FAIL'))
    unsupported=deepcopy(base);next(s for s in unsupported['steps'] if s['criterion_id']=='derivative')['value']=left+'=sin('+v+')'
    result.append(case('unsupported_expression',unsupported,None,'NEEDS_REVIEW',criterion='derivative',criterion_status='NOT_ASSESSED'))
    reordered=deepcopy(base);reordered['steps'].reverse()
    for s in reordered['steps']:
        if s['criterion_id'] in {'critical_points','points'}:s['value']=list(reversed(s['value']))
    result.append(case('reordered_claims',reordered,10))
    for method,work in reference.get('alternate_work',{}).items():
        other={'question_id':reference['question_id'],'domain':deepcopy(reference['source_domain']),
               'method':method,'steps':[{'criterion_id':k,'value':deepcopy(v)} for k,v in work.items()]}
        result.append(case('valid_alternative_'+method,other,10))
        wrong=deepcopy(other)
        if method=='polynomial_division':
            value=next(s for s in wrong['steps'] if s['criterion_id']=='division')['value']
            value['quotient']='('+value['quotient']+')+1'
            result.append(case('wrong_alternative_division',wrong,6,criterion='division',criterion_status='FAIL'))
        else:
            next(s for s in wrong['steps'] if s['criterion_id']=='critical_rule')['value']['rule']='INVALID_CRITICAL_IDENTITY'
            result.append(case('wrong_alternative_rule',wrong,7,criterion='critical_rule',criterion_status='FAIL'))
        wrong=deepcopy(other);line=next(s for s in wrong['steps'] if s['criterion_id']=='line');line['value']+=' +1'
        result.append(case('wrong_alternative_line',wrong,8,criterion='line',criterion_status='FAIL'))
    return result


def run(job):
    summary,references=load(job);cases=[];results=[];lookup={r['question_id']:r for r in references}
    for reference in references:
        for case in cases_for(reference):
            outcome=grade(reference,case['request']);actual={c['criterion_id']:c['status'] for c in outcome['criteria']}
            passed=(outcome['score']==case['expected_score'] and outcome['status']==case['expected_status']
                and (case['expected_criterion'] is None or actual.get(case['expected_criterion'])==case['expected_criterion_status']))
            cases.append(case);results.append({'scenario_id':case['scenario_id'],'category':case['category'],
                'question_id':reference['question_id'],'assertion_passed':passed,'expected_score':case['expected_score'],
                'expected_status':case['expected_status'],'outcome':outcome})
    directory=Path(summary['output_directory'])
    write_jsonl(directory/'scenario-cases.jsonl',cases);write_jsonl(directory/'scenario-results.jsonl',results)
    report={'schema_version':'calculus-trial-evaluation/v1','questions':len(references),'synthetic_scenarios':len(cases),
            'assertions_passed':sum(r['assertion_passed'] for r in results),'assertions_failed':sum(not r['assertion_passed'] for r in results),
            'by_category':dict(Counter(r['category'] for r in results)),
            'scope':'CURATED_DEVELOPMENT_COHORT_AND_SYNTHETIC_PERTURBATIONS_NOT_REAL_STUDENT_OR_FULL_CORPUS_ACCURACY',
            'cloud_api_calls':0,'production_grade':False}
    write_json(directory/'evaluation.json',report)
    summary['evaluation']=str(directory/'evaluation.json');summary['synthetic_scenarios']=len(cases)
    summary['assertions_passed']=report['assertions_passed'];summary['assertions_failed']=report['assertions_failed']
    write_json(Path(job)/'grading-trial.json',summary)
    from .viewer import render
    render(directory,references,summary,cases=cases,results=results)
    return report
