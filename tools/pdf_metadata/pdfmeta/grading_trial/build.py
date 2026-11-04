from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from ..gemini_client import content_hash
from ..pdf_workflow import local_lock
from ..storage import file_hash,read_json,write_json,write_jsonl
from .calculus import rational
from .engine import build_reference


def align(reference,item):
    """Attach exact formula matches separately from weaker layout/language cues."""
    import sympy as sp
    source_steps=item['source_metadata']['reference_solution']['steps']
    by_id={s['step_id']:s for s in source_steps}
    seen=set()
    for c in [c for route in reference['criteria_by_method'].values() for c in route]:
        if id(c) in seen:continue
        seen.add(id(c))
        matches=[];method='NO_EXACT_SOURCE_STEP_MATCH_CAS_DERIVED_CRITERION'
        if c['criterion_id'] in {'derivative','line'}:
            expected=rational(c['expected'],reference['variable'])
            for candidate in item['latex_normalization']:
                if candidate['status']!='NORMALIZED' or candidate['text_id'] not in by_id:continue
                try:
                    parsed=rational(candidate['latex'],reference['variable'])
                    if parsed['derivative_order']==expected['derivative_order'] and parsed['label']==expected['label'] and sp.cancel(parsed['expression']-expected['expression'])==0:
                        matches.append(candidate['text_id'])
                except (ValueError,TypeError,NotImplementedError):pass
            if matches:method='FORMULA_IDENTITY_MATCH_NOT_NEW_SOURCE_APPROVAL'
        else:
            kinds={'domain':{'ASSUMPTION'},'critical_points':{'ROOT_FINDING'},
                   'increasing':{'SIGN_TABLE'},'final':{'CONCLUSION'}}.get(c['criterion_id'],set())
            matches=[s['step_id'] for s in source_steps if s['kind_candidate'] in kinds]
            if matches:method='SOURCE_KIND_CUE_ONLY_NOT_MATHEMATICAL_PROOF'
        c['source_alignment']={'method':method,'source_step_ids':sorted(set(matches)),
            'source_spans':[span for sid in sorted(set(matches)) for span in by_id[sid]['source_spans']]}


def build(job,cohort):
    job,cohort=Path(job).resolve(),Path(cohort).resolve();annotations=read_json(cohort)
    pdf=job/'input.pdf';digest=file_hash(pdf)
    if annotations['source_pdf_sha256']!=digest:raise ValueError('COHORT_PDF_HASH_MISMATCH')
    if annotations.get('selection')!='TARGETED_DEVELOPMENT_COHORT_NOT_RANDOM_OR_HELDOUT':raise ValueError('COHORT_SELECTION_SCOPE_MUST_BE_DECLARED')
    cases=annotations['cases']
    if not 1<=len(cases)<=20 or len({s['question_id'] for s in cases})!=len(cases):raise ValueError('COHORT_SIZE_OR_DUPLICATE_IDS')
    for page in annotations['reviewed_page_images']:
        path=job/f"native/pages/page-{page['page_number']:03}.png"
        if file_hash(path)!=page['sha256']:raise ValueError('VISUALLY_REVIEWED_PAGE_CHANGED')
    final=read_json(job/'final.json');source=Path(final['final_jsonl']).resolve()
    if not source.is_relative_to(job/'final/versions'):raise ValueError('FINAL_OUTSIDE_JOB')
    generation=file_hash(source)
    rows=[json.loads(s) for s in source.read_text(encoding='utf-8').splitlines() if s.strip()]
    lookup={r['question_id']:r for r in rows}
    if len(rows)!=len(lookup):raise ValueError('DUPLICATE_SOURCE_IDS')
    code={p.name:file_hash(p) for p in Path(__file__).parent.glob('*.py')}
    version=content_hash({'source':generation,'annotations':file_hash(cohort),'code':code})[:16]
    root=job/'grading-trial';output=root/'versions'/version;references=[]
    with local_lock(root):
        import pdfplumber
        with pdfplumber.open(pdf) as document:
            for spec in cases:
                row=lookup.get(spec['question_id'])
                if not row or row['source_number']!=spec['source_number']:raise ValueError('COHORT_SOURCE_QUESTION_MISMATCH')
                if row['source_metadata']['source']['pdf_sha256']!=digest:raise ValueError('SOURCE_RECORD_PDF_MISMATCH')
                reference=build_reference(spec)
                reference.update(source_pdf_sha256=digest,source_final_sha256=generation,
                    source_number=row['source_number'],source_metadata_file=row['source_metadata_file'],
                    source_stem_lossy=row['source_metadata']['student_view']['stem_text_lossy'],
                    source_solution_lossy=row['source_metadata']['reference_solution']['raw_text'],
                    printed_answer=spec['printed_answer'],source_claims=spec.get('source_claims',{}),
                    annotation_notes=spec.get('annotation_notes',[]),
                    review_scope=annotations['review_scope'],reference_work=spec['reference_work'],
                    alternate_work=spec.get('alternate_work',{}))
                align(reference,row);images=[]
                for index,span in enumerate(row['source_metadata']['source']['spans'],1):
                    number=span['page_number'];page=document.pages[number-1];box=span['bbox']
                    if not 0<=box[0]<box[2]<=page.width or not 0<=box[1]<box[3]<=page.height:raise ValueError('SOURCE_QUESTION_BOX_INVALID')
                    path=output/'assets'/f"q{row['source_number']}-p{number:03}-{index}.png";path.parent.mkdir(parents=True,exist_ok=True)
                    page.crop(tuple(box)).to_image(resolution=120).save(path)
                    images.append({'path':path.relative_to(output).as_posix(),'page_number':number,
                                   'bbox':box,'sha256':file_hash(path)})
                reference['source_images']=images;references.append(reference)
        if file_hash(pdf)!=digest or file_hash(source)!=generation:raise ValueError('SOURCE_CHANGED_DURING_COHORT_BUILD')
        package=output/'questions.sandbox-rubric.jsonl';write_jsonl(package,references)
        write_json(output/'annotations.snapshot.json',annotations)
        write_json(output/'policy.json',{'version':'sandbox-only/v1','production_grade':False,'teacher_rubric_approved':False,
            'source_annotations_are_manual':True,'automatic_general_pdf_approval':False,
            'score_policy':'INDEPENDENT_CRITERION_CREDIT_WITH_EXPLICIT_DEPENDENCY_WARNINGS',
            'unknown_or_domain_blocked_steps':'NO_NUMERIC_TOTAL_RETURN_SCORE_BOUNDS',
            'unsubmitted_steps':'ZERO_FOR_THAT_CRITERION_NO_INFERRED_PROOF'})
        summary={'schema_version':'calculus-grading-trial/v1','source_pdf_sha256':digest,
            'source_final_file':str(source),'source_final_sha256':generation,'cohort_sha256':file_hash(cohort),
            'selection':annotations['selection'],'questions':len(references),
            'ready_for_sandbox':sum(r['eligibility']=='SANDBOX_REFERENCE_READY' for r in references),
            'held_for_source_conflict':sum(r['eligibility']=='HELD_SOURCE_CONFLICT' for r in references),
            'rubric_criteria':sum(len(r['criteria']) for r in references),
            'formula_aligned_criteria':sum(c['source_alignment']['method'].startswith('FORMULA_IDENTITY') for r in references for c in r['criteria']),
            'source_issue_counts':dict(Counter(i for r in references for i in r['source_issues'])),
            'grader_code':{n:code[n] for n in ['calculus.py','engine.py']},
            'package':str(package),'package_sha256':file_hash(package),'output_directory':str(output),
            'review_html':str(root/'review.html'),'production_grade':False,'academic_approved_count':0}
        write_json(output/'report.json',summary);write_json(job/'grading-trial.json',summary)
        from .viewer import render
        render(output,references,summary)
        (root/'review.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=versions/'+version+'/review.html">',encoding='utf-8')
        return summary


def load(job):
    job=Path(job).resolve();summary=read_json(job/'grading-trial.json');package=Path(summary['package']).resolve()
    if not package.is_relative_to(job/'grading-trial/versions') or file_hash(package)!=summary['package_sha256']:raise ValueError('TRIAL_PACKAGE_CHANGED')
    final=Path(read_json(job/'final.json')['final_jsonl']).resolve()
    if final!=Path(summary['source_final_file']).resolve() or file_hash(final)!=summary['source_final_sha256']:raise ValueError('TRIAL_SOURCE_STALE')
    if file_hash(job/'input.pdf')!=summary['source_pdf_sha256']:raise ValueError('TRIAL_PDF_CHANGED')
    if any(file_hash(Path(__file__).parent/name)!=h for name,h in summary.get('grader_code',{}).items()) or not summary.get('grader_code'):
        raise ValueError('TRIAL_GRADER_CHANGED_REBUILD_REQUIRED')
    records=[json.loads(s) for s in package.read_text(encoding='utf-8').splitlines() if s.strip()]
    for record in records:
        for image in record['source_images']:
            path=(package.parent/image['path']).resolve()
            if not path.is_relative_to(package.parent) or file_hash(path)!=image['sha256']:raise ValueError('TRIAL_SOURCE_IMAGE_CHANGED')
    return summary,records


def check(job,request):
    from .engine import grade
    _,references=load(job)
    matches=[r for r in references if r['question_id']==request.get('question_id')]
    if len(matches)!=1:raise ValueError('TRIAL_QUESTION_UNKNOWN')
    return grade(matches[0],request)
