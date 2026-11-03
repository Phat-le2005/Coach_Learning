from __future__ import annotations

import re
import sympy as sp

from ..safe_math import assignment,parse_expression


def scalar(value,*,infinity=False):
    if not isinstance(value,str) or len(value)>120:raise ValueError('SCALAR_LIMIT')
    if any(len(v)>18 for v in re.findall(r'\d+',value)):raise ValueError('NUMBER_DIGIT_LIMIT')
    if infinity and value in {'inf','-inf'}:return sp.oo if value=='inf' else -sp.oo
    result=parse_expression(value).expression
    if result.free_symbols or result.is_real is not True or result.is_finite is not True:raise ValueError('FINITE_REAL_SCALAR_REQUIRED')
    return result


def domain(spec):
    if not isinstance(spec,dict) or set(spec)-{'intervals','excluded'}:raise ValueError('DOMAIN_SCHEMA_INVALID')
    parts=spec.get('intervals')
    if not isinstance(parts,list) or len(parts)>12:raise ValueError('DOMAIN_INTERVAL_LIMIT')
    result=sp.S.EmptySet
    for item in parts:
        if set(item)!={'left','right','left_open','right_open'}:raise ValueError('DOMAIN_INTERVAL_INVALID')
        if type(item['left_open']) is not bool or type(item['right_open']) is not bool:raise ValueError('DOMAIN_ENDPOINT_FLAGS_INVALID')
        a,b=scalar(item['left'],infinity=True),scalar(item['right'],infinity=True)
        if a>=b:raise ValueError('DOMAIN_INTERVAL_ORDER')
        result=sp.Union(result,sp.Interval(a,b,left_open=item['left_open'],right_open=item['right_open']))
    excluded=spec.get('excluded',[])
    if not isinstance(excluded,list) or len(excluded)>12:raise ValueError('DOMAIN_EXCLUSION_LIMIT')
    return result-sp.FiniteSet(*(scalar(v) for v in excluded))


def intervals(value):
    if value==sp.S.EmptySet:return []
    if isinstance(value,sp.Interval):return [value]
    if isinstance(value,sp.Union) and all(isinstance(v,sp.Interval) for v in value.args):return list(value.args)
    raise ValueError('DOMAIN_SHAPE_UNSUPPORTED')


def interval_spec(value):
    def text(v):return '-inf' if v is -sp.oo else 'inf' if v is sp.oo else sp.sstr(v)
    return {'intervals':[{'left':text(v.start),'right':text(v.end),'left_open':bool(v.left_open),
                         'right_open':bool(v.right_open)} for v in intervals(value)],'excluded':[]}


def rational(latex,variable):
    if not isinstance(latex,str) or len(latex)>500:raise ValueError('FORMULA_LENGTH_LIMIT')
    if any(len(v)>18 for v in re.findall(r'\d+',latex)):raise ValueError('NUMBER_DIGIT_LIMIT')
    if any(t in latex for t in ['\\text','\\quad',';','⇒','⇔','<','>','≤','≥']):raise ValueError('EXTRA_STATEMENT_UNSUPPORTED')
    parsed=assignment(latex)
    x=sp.Symbol(variable)
    if not parsed['chain_consistent'] or parsed['conditions_raw']:raise ValueError('INCONSISTENT_CHAIN_OR_INLINE_DOMAIN')
    if parsed['expression'].free_symbols-{x}:raise ValueError('MULTIVARIATE_FORMULA_UNSUPPORTED')
    if not parsed['expression'].is_rational_function(x):raise ValueError('NONRATIONAL_FORMULA_UNSUPPORTED')
    for e in [parsed['expression'],*parsed['denominators']]:
        a,b=sp.fraction(sp.cancel(e))
        if any(p!=0 and sp.degree(p,x)>8 for p in [a,b]):raise ValueError('POLYNOMIAL_DEGREE_LIMIT')
    return parsed


def poles(parsed,x):
    values=sp.S.EmptySet
    for expression in parsed['denominators']:
        roots=sp.solveset(expression,x,domain=sp.S.Reals)
        if roots!=sp.S.EmptySet and not isinstance(roots,sp.FiniteSet):raise ValueError('NONFINITE_POLE_SET')
        values|=roots
    return values


def ordered(values):return sorted(values,key=lambda v:float(sp.N(v,30)))


def sample(a,b):
    return sp.S.Zero if a==-sp.oo and b==sp.oo else b-1 if a==-sp.oo else a+1 if b==sp.oo else (a+b)/2


def analyse(spec):
    variable=spec['variable']
    if not isinstance(variable,str) or len(variable)!=1 or not variable.isascii() or not variable.isalpha():raise ValueError('INVALID_VARIABLE')
    parsed=rational(spec['function_latex'],variable);x=sp.Symbol(variable)
    if parsed['derivative_order'] or parsed['variable'] not in {None,variable}:raise ValueError('SOURCE_FUNCTION_IDENTITY_INVALID')
    declared=domain(spec['domain']);excluded=poles(parsed,x);allowed=declared-excluded
    f=parsed['expression'];derivative=sp.cancel(sp.diff(f,x))
    numerator=sp.fraction(derivative)[0]
    roots=sp.solveset(numerator,x,domain=allowed)
    if roots!=sp.S.EmptySet and not isinstance(roots,sp.FiniteSet):raise ValueError('FINITE_CRITICAL_SET_REQUIRED')
    critical=ordered(roots);cells=[];increasing=sp.S.EmptySet;extrema=[]
    for part in intervals(allowed):
        interior=[v for v in critical if part.start<v<part.end]
        cuts=[part.start,*interior,part.end];signs=[]
        for a,b in zip(cuts,cuts[1:]):
            sign=sp.sign(derivative.subs(x,sample(a,b)))
            if sign not in {-1,1}:raise ValueError('SIGN_CELL_UNSUPPORTED')
            signs.append(int(sign));cells.append({'left':sp.sstr(a),'right':sp.sstr(b),'sign':int(sign)})
            if sign==1:increasing|=sp.Interval.open(a,b)
        for i,root in enumerate(interior):
            if signs[i]!=signs[i+1]:extrema.append((root,sp.simplify(f.subs(x,root))))
            elif signs[i]==1:increasing|=sp.FiniteSet(root)
    line=None
    if len(extrema)==2:
        (a,fa),(b,fb)=extrema
        slope=sp.simplify((fb-fa)/(b-a));intercept=sp.simplify(fa-slope*a)
        line=(slope,intercept)
    task=spec['task'];kind=task['kind']
    if kind=='INCREASING_ENDPOINT_LINEAR':
        spans=intervals(increasing)
        if len(spans)!=1 or not spans[0].start.is_finite or not spans[0].end.is_finite:raise ValueError('SINGLE_BOUNDED_INCREASING_INTERVAL_REQUIRED')
        answer=scalar(task['left_coefficient'])*spans[0].start+scalar(task['right_coefficient'])*spans[0].end
    elif kind=='RIGHT_INCREASING_START':
        spans=[s for s in intervals(increasing) if s.end==sp.oo]
        if len(spans)!=1 or not spans[0].start.is_finite:raise ValueError('RIGHT_UNBOUNDED_BRANCH_REQUIRED')
        answer=spans[0].start
    elif kind=='EXTREMA_DISTANCE':
        if len(extrema)!=2:raise ValueError('EXACTLY_TWO_EXTREMA_REQUIRED')
        answer=sp.sqrt(sum((a-b)**2 for a,b in zip(extrema[0],extrema[1])))
    else:
        if line is None:raise ValueError('EXACTLY_TWO_EXTREMA_REQUIRED')
        slope,intercept=line
        if kind=='SECANT_LINEAR_COMBINATION':answer=scalar(task['a_coefficient'])*slope+scalar(task['b_coefficient'])*intercept
        elif kind=='ORIGIN_LINE_DISTANCE':answer=sp.Abs(intercept)/sp.sqrt(slope**2+1)
        elif kind=='AXIS_TRIANGLE_AREA':
            if slope==0 or intercept==0:raise ValueError('NONDEGENERATE_AXIS_TRIANGLE_REQUIRED')
            answer=sp.Abs(intercept**2/(2*slope))
        else:raise ValueError('TASK_KIND_UNSUPPORTED')
    return {'parsed':parsed,'variable':x,'function':f,'derivative':derivative,'domain':allowed,
            'source_domain_omits_pole':bool(excluded.intersect(declared)),
            'critical':critical,'extrema':extrema,'line':line,'increasing':increasing,
            'cells':cells,'answer':sp.simplify(answer)}


def same_points(actual,expected):
    if not isinstance(actual,list) or len(actual)>12:raise ValueError('POINT_LIST_INVALID')
    points=[]
    for pair in actual:
        if not isinstance(pair,list) or len(pair)!=2:raise ValueError('POINT_PAIR_INVALID')
        points.append(tuple(scalar(v) for v in pair))
    if len(points)!=len(expected):return False
    return all(any(all(sp.simplify(a-b)==0 for a,b in zip(p,q)) for q in points) for p in expected)


def source_conflicts(spec,analysis):
    claims=spec.get('source_claims',{});issues=[]
    if analysis['source_domain_omits_pole']:issues.append('SOURCE_DOMAIN_OMITS_FUNCTION_POLE')
    if 'increasing' in claims and domain(claims['increasing'])!=analysis['increasing']:issues.append('SOURCE_MONOTONICITY_CLAIM_CONFLICT')
    if 'extrema_points' in claims and not same_points(claims['extrema_points'],analysis['extrema']):issues.append('SOURCE_POINT_VALUES_CONFLICT')
    if 'secant_line' in claims:
        parsed=rational(claims['secant_line'],spec['variable']);a,b=analysis['line']
        if sp.cancel(parsed['expression']-a*analysis['variable']-b)!=0:issues.append('SOURCE_SECANT_LINE_CONFLICT')
    return issues
