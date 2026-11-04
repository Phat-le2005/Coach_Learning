"""Deterministic sandbox rubric; no DB writes or production grading approval."""
from __future__ import annotations

from decimal import Decimal,ROUND_HALF_UP
import re
import sympy as sp

from .calculus import analyse,domain,interval_spec,poles,rational,same_points,scalar,source_conflicts


RUBRIC_VERSION='calculus-independent-claims/v1'


def rounded(value,digits):
    if type(digits) is not int or not 0<=digits<=6:raise ValueError('ROUNDING_DIGITS_INVALID')
    return format(Decimal(str(sp.N(value,50))).quantize(Decimal(1).scaleb(-digits),rounding=ROUND_HALF_UP),'f')


def answer_matches(value,reference):
    actual=scalar(value);exact=scalar(reference['answer_exact'])
    if sp.simplify(actual-exact)==0:return True
    return reference.get('round_digits') is not None and actual==scalar(reference['answer_display'])


def build_reference(spec):
    data=analyse(spec);issues=source_conflicts(spec,data)
    exact=sp.sstr(data['answer']);display=rounded(data['answer'],spec['round_digits']) if 'round_digits' in spec else exact
    answer={'answer_exact':exact,'answer_display':display,'round_digits':spec.get('round_digits')}
    if not answer_matches(spec['printed_answer'],answer):issues.append('PRINTED_ANSWER_DISAGREES_WITH_INDEPENDENT_CALCULATION')
    x=data['variable'];parsed=data['parsed'];kind=spec['task']['kind']
    lhs=parsed['label']+"'"+('('+spec['variable']+')' if parsed['variable'] else '')
    def criterion(key,label,maximum,expected,requires):
        return {'criterion_id':key,'label':label,'max_points':maximum,'expected':expected,'requires':requires,
                'origin':'CODE_DERIVED_RUBRIC_NOT_VERBATIM_SOURCE_STEP'}
    criteria=[criterion('domain','Miền xét và điều kiện',1,interval_spec(data['domain']),[]),
              criterion('derivative','Tính đạo hàm',2,lhs+'='+sp.latex(data['derivative']),['domain']),
              criterion('critical_points','Tìm nghiệm đạo hàm trong miền xét',2,[sp.sstr(v) for v in data['critical']],['domain','derivative'])]
    if kind in {'INCREASING_ENDPOINT_LINEAR','RIGHT_INCREASING_START'}:
        criteria.append(criterion('increasing','Xét dấu và kết luận khoảng đồng biến',3,interval_spec(data['increasing']),['critical_points']))
        final_weight=2
    else:
        criteria.append(criterion('points','Tọa độ hai điểm cực trị',2,[[sp.sstr(a),sp.sstr(b)] for a,b in data['extrema']],['critical_points']))
        if kind=='EXTREMA_DISTANCE':
            criteria.append(criterion('metric','Lập biểu thức độ dài',2,exact,['points']))
        else:
            a,b=data['line']
            criteria.append(criterion('line','Đường thẳng qua hai điểm cực trị',2,'y='+sp.latex(a*x+b),['points']))
        final_weight=1
    criteria.append(criterion('final','Kết quả cuối theo yêu cầu đề',final_weight,display,[criteria[-1]['criterion_id']]))
    assert sum(c['max_points'] for c in criteria)==10
    methods={'direct':criteria}
    if data['line'] is not None and kind!='EXTREMA_DISTANCE':
        line='y='+sp.latex(data['line'][0]*x+data['line'][1])
        final=criterion('final','Kết quả cuối theo yêu cầu đề',1,display,['line'])
        if data['function'].is_polynomial(x) and sp.degree(data['function'],x)==3:
            q,r=sp.div(data['function'],data['derivative'],x)
            methods['polynomial_division']=[criteria[0],criteria[1],
                criterion('division','Chia đa thức và dùng điều kiện đạo hàm bằng 0',4,
                          {'quotient':sp.sstr(q),'remainder':sp.sstr(r)},['derivative']),
                criterion('line','Đường thẳng qua hai điểm cực trị',2,line,['division']),final]
        u,v=sp.fraction(sp.cancel(data['function']))
        if sp.degree(u,x)==2 and sp.degree(v,x)==1:
            up,vp=sp.diff(u,x),sp.diff(v,x)
            if vp==0 or sp.cancel(data['function']-up/vp+v/vp*data['derivative'])!=0:raise ValueError('QUOTIENT_CRITICAL_IDENTITY_FAILED')
            methods['rational_critical_ratio']=[criteria[0],
                criterion('numerator_derivative','Đạo hàm của tử số',2,"u'="+sp.latex(up),['domain']),
                criterion('denominator_derivative','Đạo hàm của mẫu số',1,"v'="+sp.latex(vp),['domain']),
                criterion('critical_rule','Dùng tỉ số đạo hàm tại điểm cực trị',3,
                    {'rule':'F_EQUALS_U_PRIME_OVER_V_PRIME_AT_CRITICAL','ratio':line},['numerator_derivative','denominator_derivative']),
                criterion('line','Đường thẳng qua hai điểm cực trị',2,line,['critical_rule']),final]
    if any(sum(c['max_points'] for c in route)!=10 for route in methods.values()):raise ValueError('RUBRIC_SCORE_TOTAL_INVALID')
    return {'question_id':spec['question_id'],'source_number':spec['source_number'],'variable':spec['variable'],
        'function_latex':spec['function_latex'],'source_domain':spec['domain'],'task':spec['task'],**answer,
        'eligibility':'HELD_SOURCE_CONFLICT' if issues else 'SANDBOX_REFERENCE_READY','source_issues':issues,
        'rubric_version':RUBRIC_VERSION,'rubric_status':'PROPOSED_NOT_TEACHER_APPROVED','maximum_score':10,
        'grading_policy':'INDEPENDENT_CLAIM_CREDIT_WITH_DOMAIN_GATE_MISSING_STEPS_NOT_INFERRED',
        'criteria':criteria,'source_sign_cells':data['cells'],
        'criteria_by_method':methods,'allowed_methods':list(methods),
        'academic_review':'PENDING','publishable':False,'production_grade':False}


def expression_match(actual,expected,reference,*,line=False):
    a=rational(actual,reference['variable']);b=rational(expected,reference['variable'])
    if a['label']!=b['label'] or a['derivative_order']!=b['derivative_order']:return False,'FUNCTION_OR_DERIVATIVE_LABEL_MISMATCH'
    if a['variable'] not in {None,reference['variable']}:return False,'VARIABLE_MISMATCH'
    allowed=sp.S.Reals if line else domain(reference['criteria'][0]['expected'])
    if poles(a,sp.Symbol(reference['variable'])).intersect(allowed)!=sp.S.EmptySet:return False,'NEW_UNDEFINED_POINT_IN_STEP_DOMAIN'
    return sp.cancel(a['expression']-b['expression'])==0,'SYMBOLIC_IDENTITY_CHECK'


def grade(reference,request):
    if not isinstance(request,dict) or set(request)-{'question_id','domain','steps','method'}:raise ValueError('ATTEMPT_SCHEMA_INVALID')
    if request.get('question_id')!=reference['question_id']:raise ValueError('QUESTION_ID_MISMATCH')
    steps=request.get('steps',[])
    if not isinstance(steps,list) or len(steps)>20:raise ValueError('ATTEMPT_STEP_LIMIT')
    method=request.get('method')
    if method is None:
        submitted_ids={s.get('criterion_id') for s in steps if isinstance(s,dict) and isinstance(s.get('criterion_id'),str)}
        if 'division' in submitted_ids and submitted_ids & {'critical_rule','numerator_derivative','denominator_derivative'}:raise ValueError('AMBIGUOUS_METHOD_REQUIRES_REVIEW')
        method='polynomial_division' if 'division' in submitted_ids else 'rational_critical_ratio' if submitted_ids & {'critical_rule','numerator_derivative','denominator_derivative'} else 'direct'
    if method not in reference['criteria_by_method']:raise ValueError('METHOD_UNSUPPORTED_USE_REVIEW_ROUTE')
    criteria=reference['criteria_by_method'][method]
    submitted={};known={c['criterion_id'] for c in criteria} - {'domain'}
    for step in steps:
        if not isinstance(step,dict) or set(step)!={'criterion_id','value'}:raise ValueError('STEP_SCHEMA_INVALID')
        key=step['criterion_id']
        if key not in known:raise ValueError('UNKNOWN_CRITERION')
        if key in submitted:raise ValueError('DUPLICATE_CRITERION')
        submitted[key]=step['value']
    base={'question_id':reference['question_id'],'rubric_version':reference['rubric_version'],
          'method':method,'maximum_score':10,'production_grade':False,'score_scope':'SANDBOX_RUBRIC_NOT_OFFICIAL_STUDENT_GRADE'}
    if reference['eligibility']!='SANDBOX_REFERENCE_READY':
        return {**base,'status':'HELD_SOURCE_CONFLICT','score':None,'score_lower_bound':0,'score_upper_bound':10,
                'source_issues':reference['source_issues'],'criteria':[]}
    results=[];domain_ok=False
    for criterion in criteria:
        key=criterion['criterion_id'];maximum=criterion['max_points'];status='NOT_ASSESSED';points=None;reason='UNSUPPORTED_INPUT'
        try:
            if key=='domain':
                if 'domain' not in request:reason='DOMAIN_NOT_PROVIDED'
                else:
                    domain_ok=domain(request['domain'])==domain(criterion['expected'])
                    status='PASS' if domain_ok else 'FAIL';points=maximum if domain_ok else 0;reason='DOMAIN_MATCH' if domain_ok else 'DOMAIN_MISMATCH'
            elif not domain_ok:reason='DOMAIN_GATE_NOT_SATISFIED'
            elif key not in submitted:status='MISSING';points=0;reason='STEP_NOT_SUBMITTED_NO_INFERRED_CREDIT'
            else:
                value=submitted[key];expected=criterion['expected']
                if key in {'derivative','line','numerator_derivative','denominator_derivative'}:matched,reason=expression_match(value,expected,reference,line=key!='derivative')
                elif key=='division':
                    if not isinstance(value,dict) or set(value)!={'quotient','remainder'}:raise ValueError('DIVISION_FIELDS_REQUIRED')
                    x=sp.Symbol(reference['variable'])
                    q=rational('q='+value['quotient'],reference['variable'])['expression']
                    r=rational('r='+value['remainder'],reference['variable'])['expression']
                    if not q.is_polynomial(x) or not r.is_polynomial(x) or sp.degree(q,x)>1 or (r!=0 and sp.degree(r,x)>1):raise ValueError('DIVISION_DEGREE_OR_KIND_UNSUPPORTED')
                    f=rational(reference['function_latex'],reference['variable'])['expression']
                    matched=sp.cancel(f-q*sp.diff(f,x)-r)==0;reason='POLYNOMIAL_DIVISION_IDENTITY_CHECK'
                elif key=='critical_rule':
                    if not isinstance(value,dict) or set(value)!={'rule','ratio'}:raise ValueError('CRITICAL_RULE_FIELDS_REQUIRED')
                    if value['rule']!=expected['rule']:matched=False;reason='WRONG_QUOTIENT_CRITICAL_RULE'
                    else:matched,reason=expression_match(value['ratio'],expected['ratio'],reference,line=True)
                elif key=='critical_points':
                    if not isinstance(value,list) or len(value)>12:raise ValueError('ROOT_LIST_INVALID')
                    matched=sp.FiniteSet(*(scalar(v) for v in value))==sp.FiniteSet(*(scalar(v) for v in expected));reason='CRITICAL_SET_MATCH'
                elif key=='increasing':matched=domain(value)==domain(expected);reason='INCREASING_INTERVALS_MATCH'
                elif key=='points':matched=same_points(value,[(scalar(a),scalar(b)) for a,b in expected]);reason='EXTREMA_COORDINATES_MATCH'
                elif key=='metric':matched=sp.simplify(scalar(value)-scalar(expected))==0;reason='EXACT_GEOMETRY_VALUE_MATCH'
                elif key=='final':matched=answer_matches(value,reference);reason='FINAL_VALUE_AND_ROUNDING_CHECK'
                else:raise ValueError('CRITERION_NOT_SUPPORTED')
                status='PASS' if matched else 'FAIL';points=maximum if matched else 0
        except (ValueError,TypeError,KeyError,NotImplementedError) as error:reason=str(error)
        results.append({'criterion_id':key,'label':criterion['label'],'status':status,'points':points,
                        'max_points':maximum,'reason':reason,'requires':criterion['requires']})
    earned=sum(c['points'] or 0 for c in results);unknown=sum(c['max_points'] for c in results if c['points'] is None)
    statuses={c['criterion_id']:c['status'] for c in results}
    warnings=[{'criterion_id':c['criterion_id'],'prerequisite':key,'prerequisite_status':statuses[key]}
              for c in results if c['status']=='PASS' for key in c['requires'] if statuses[key]!='PASS']
    return {**base,'status':'NEEDS_REVIEW' if unknown else 'COMPLETE_SANDBOX_ASSESSMENT','score':None if unknown else earned,
            'score_lower_bound':earned,'score_upper_bound':earned+unknown,'criteria':results,
            'dependency_warnings':warnings,
            'missing_prerequisite_claims':[c['criterion_id'] for c in results if c['status']=='MISSING']}
