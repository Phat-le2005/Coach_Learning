"""Export provisional step checkers. No scores, DB imports or approval by models."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import sympy as sp
from jsonschema import Draft202012Validator

from ..gemini_client import content_hash
from ..safe_math import assignment, equivalent
from ..storage import file_hash,read_json,write_json,write_jsonl


SCHEMA={'type':'object','additionalProperties':False,
 'required':['schema_version','question_id','source_pdf_sha256','source_final_sha256','steps','academic_review','grading_support','publishable'],
 'properties':{'schema_version':{'const':'grading-candidates/v1'},'question_id':{'type':'string'},
  'source_pdf_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'source_final_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
  'steps':{'type':'array','items':{'type':'object','required':['step_id','checker','blockers','rubric_weight','source_spans'],
    'properties':{'step_id':{'type':'string'},'checker':{'type':['object','null']},'blockers':{'type':'array','items':{'type':'string'}},
                  'rubric_weight':{'type':'null'},'source_spans':{'type':'array'}}}},
  'academic_review':{'const':'PENDING'},'grading_support':{'const':'NOT_ASSESSED'},'publishable':{'const':False}}}


def bounded(latex):
    if not isinstance(latex,str) or len(latex)>500:raise ValueError('EXPRESSION_LIMIT')
    if any(token in latex for token in ['\\text','\\quad','⇒','⇔',';','<','>','≤','≥']):raise ValueError('DOMAIN_OR_EXTRA_STATEMENT_UNSUPPORTED')
    parsed=assignment(latex)
    if not parsed['chain_consistent'] or parsed['conditions_raw']:raise ValueError('CONDITIONS_REQUIRE_STRUCTURED_DOMAIN')
    symbols=parsed['expression'].free_symbols|{s for d in parsed['denominators'] for s in d.free_symbols}
    if len(symbols)>1:raise ValueError('ONLY_UNIVARIATE_RATIONAL_SUPPORTED')
    variable=next(iter(symbols),sp.Symbol(parsed['variable'] or 'x'))
    if not parsed['expression'].is_rational_function(variable):raise ValueError('ONLY_UNIVARIATE_RATIONAL_SUPPORTED')
    for expression in [parsed['expression'],*parsed['denominators']]:
        numerator,denominator=sp.fraction(sp.cancel(expression))
        for polynomial in [numerator,denominator]:
            if polynomial!=0 and sp.degree(polynomial,variable)>8:raise ValueError('DEGREE_LIMIT')
    excluded=set()
    for d in parsed['denominators']:
        roots=sp.solveset(d,variable,domain=sp.S.Reals)
        if not isinstance(roots,sp.FiniteSet) and roots!=sp.S.EmptySet:raise ValueError('DOMAIN_UNSUPPORTED')
        excluded.update(sp.sstr(v) for v in roots)
    return parsed,{'variable':str(variable),'set':'REAL_EXCEPT','excluded':sorted(excluded)}


def checker_for(candidates):
    if not candidates:return None,['NO_PRECISE_FORMULA_FOR_STEP']
    if any(r.get('source_group_unresolved') or r['status']!='NORMALIZED' for r in candidates):
        return None,['SOURCE_FORMULA_UNRESOLVED']
    try:
        parsed=[bounded(c['latex']) for c in candidates]
        first,domain=parsed[0]
        if any(not equivalent(first,p) or d!=domain for p,d in parsed[1:]):return None,['MULTIPLE_STEP_FORMULAS']
    except (ValueError,TypeError,NotImplementedError):return None,['UNSUPPORTED_CHECKER_OR_DOMAIN']
    return {'kind':'RATIONAL_EXPRESSION_EQUIVALENCE','expected_latex':candidates[0]['latex'],
            'domain':domain,'candidate_ids':[c['candidate_id'] for c in candidates],
            'scope':'PROVISIONAL_IDENTITY_AND_DOMAIN_NOT_SCORE'},[]


def export(job):
    job=Path(job).resolve();report=read_json(job/'final.json');source=Path(report['final_jsonl']).resolve()
    if not source.is_relative_to(job/'final/versions'):raise ValueError('FINAL_OUTSIDE_JOB')
    generation=file_hash(source);records=[json.loads(s) for s in source.read_text(encoding='utf-8').splitlines() if s.strip()]
    output=[];validator=Draft202012Validator(SCHEMA)
    for record in records:
        item=record['source_metadata'];steps=[]
        for step in item['reference_solution']['steps']:
            candidates=[c for c in record['latex_normalization'] if c['text_id']==step['step_id'] and c['origin']=='GEOMETRY_OR_OCR']
            checker,blockers=checker_for(candidates)
            steps.append({'step_id':step['step_id'],'kind_candidate':step['kind_candidate'],
                'text_source':step['text_candidate'],'source_spans':step['source_spans'],
                'checker':checker,'blockers':sorted(set(blockers+['SOURCE_NOT_VERIFIED','STEP_MEANING_NOT_VERIFIED','RUBRIC_NOT_DEFINED'])),
                'rubric_weight':None,'logical_prerequisites':[],'previous_step_id':step.get('previous_step_id'),
                'order_is_logical_proof':False})
        row={'schema_version':'grading-candidates/v1','question_id':record['question_id'],
             'source_pdf_sha256':item['source']['pdf_sha256'],'source_final_sha256':generation,'steps':steps,
             'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False}
        validator.validate(row);output.append(row)
    version=content_hash({'source':generation,'exporter':file_hash(Path(__file__))})[:16]
    directory=job/'core/versions'/version
    write_jsonl(directory/'questions.core-candidates.jsonl',output);write_json(directory/'schema.json',SCHEMA)
    checks=sum(s['checker'] is not None for row in output for s in row['steps'])
    summary={'schema_version':'grading-candidates-report/v1','source_final_sha256':generation,'source_final_file':str(source),
        'question_count':len(output),'step_count':sum(len(r['steps']) for r in output),'provisional_checkers':checks,
        'blocked_for_production':sum(len(r['steps']) for r in output),'grading_ready_count':0,
        'blocker_counts':dict(Counter(b for r in output for s in r['steps'] for b in s['blockers'])),
        'package':str(directory/'questions.core-candidates.jsonl'),'schema':str(directory/'schema.json'),
        'package_sha256':file_hash(directory/'questions.core-candidates.jsonl'),'production_imported':False}
    write_json(job/'core-package.json',summary);write_json(directory/'report.json',summary)
    return summary


def check(job,request):
    """A consumer supplies only step ID and student expression, never an expected answer."""
    if set(request)-{'step_id','candidate_latex','declared_excluded'}:raise ValueError('UNEXPECTED_CHECK_REQUEST_FIELD')
    job=Path(job).resolve();manifest=read_json(job/'core-package.json');package=Path(manifest['package']).resolve()
    if not package.is_relative_to(job/'core/versions') or file_hash(package)!=manifest['package_sha256']:raise ValueError('CORE_PACKAGE_CHANGED')
    final=Path(read_json(job/'final.json')['final_jsonl']).resolve()
    if file_hash(final)!=manifest['source_final_sha256']:raise ValueError('STALE_CORE_PACKAGE')
    rows=[json.loads(s) for s in package.read_text(encoding='utf-8').splitlines() if s.strip()]
    matches=[s for row in rows for s in row['steps'] if s['step_id']==request.get('step_id')]
    if len(matches)!=1:raise ValueError('UNKNOWN_OR_DUPLICATE_STEP_ID')
    step=matches[0];spec=step['checker'];base={'step_id':step['step_id'],'score':None,'production_grade':False,
                                           'scope':'PROVISIONAL_CHECK_AGAINST_UNVERIFIED_SOURCE','blockers':step['blockers']}
    if not spec:return {**base,'status':'NOT_ASSESSED','reason':'NO_SUPPORTED_CHECKER'}
    try:
        expected,domain=bounded(spec['expected_latex']);candidate,candidate_domain=bounded(request['candidate_latex'])
        declared=request.get('declared_excluded',[])
        if not isinstance(declared,list) or len(declared)>16 or any(not isinstance(v,str) or len(v)>30 for v in declared):raise ValueError('INVALID_DOMAIN_DECLARATION')
        # Parse each explicit excluded number with the same bounded grammar.
        extra=[]
        for value in declared:
            v,_=bounded('y='+value)
            if v['expression'].free_symbols:raise ValueError('EXCLUDED_POINT_MUST_BE_CONSTANT')
            extra.append(sp.sstr(v['expression']))
        candidate_domain['excluded']=sorted(set(candidate_domain['excluded'])|set(extra))
        if domain!=candidate_domain:return {**base,'status':'NOT_ASSESSED','reason':'DOMAIN_MISMATCH'}
        return {**base,'status':'CANDIDATE_MATCH' if equivalent(expected,candidate) else 'CANDIDATE_MISMATCH','reason':'RATIONAL_IDENTITY_CHECK'}
    except (ValueError,TypeError,KeyError,NotImplementedError) as error:
        return {**base,'status':'NOT_ASSESSED','reason':str(error)}
