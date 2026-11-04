"""Route whole source-backed questions into explicit downstream usages."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
from decimal import Decimal,InvalidOperation

from .storage import read_json, write_json, write_jsonl, file_hash
from .paired.transcript_batch import content_hash
from .paired.choice_layout import meaningful


POLICY='whole-question-source-first-final-answer/v2'
ANSWER=re.compile(r'^\s*(?:Chọn|Đáp\s*án\s*:?)\s*([ABCD])(?:[.\s:]|$)',re.I|re.M)


def explicit_answer(row):
    part=row['parts'].get('answer',{})
    raw_answer=part.get('raw_text_lossy') or ''
    displayed=re.sub(r'^\s*Đáp\s*án\s*:\s*','',part.get('markdown',''),flags=re.I)
    number_raw=decimal_answer(raw_answer);number_display=decimal_answer(displayed)
    if part.get('source_spans') and part.get('fragments') and number_raw is not None and number_raw==number_display:
        return {'kind':'NUMBER','expected_decimal':str(number_raw),'comparison':'EXACT_DECIMAL_COMMA_OR_DOT',
                'evidence':'EXPLICIT_SOURCE_ANSWER_REGION','academic_review':'PENDING'}
    literal_raw=re.sub(r'\s+','',raw_answer).rstrip('.')
    literal_display=re.sub(r'\s+','',displayed).rstrip('.')
    if part.get('source_spans') and part.get('fragments') and literal_raw in list('ABCD') and literal_raw==literal_display:
        return {'kind':'MULTIPLE_CHOICE','expected_label':literal_raw,
                'evidence':'EXPLICIT_SOURCE_ANSWER_REGION','academic_review':'PENDING'}
    raw=row['parts']['solution'].get('raw_text_lossy') or ''
    rendered=row['parts']['solution']['markdown']
    source=set(m[0].upper() for m in ANSWER.findall(raw))
    display=set(m[0].upper() for m in ANSWER.findall(rendered))
    if len(source)==1 and source==display:
        return {'kind':'MULTIPLE_CHOICE','expected_label':next(iter(source)),
                'evidence':'EXPLICIT_SOURCE_SOLUTION_LABEL','academic_review':'PENDING'}
    return None


def decimal_answer(text):
    text=re.sub(r'\s+','',text).strip('$').replace('−','-').rstrip('.')
    if len(text)>60 or not re.fullmatch(r'[+-]?\d+(?:[,.]\d+)?',text):return None
    if re.fullmatch(r'[+-]?\d{1,3}(?:[,.]\d{3})+',text):return None
    try:return Decimal(text.replace(',','.'))
    except InvalidOperation:return None


def compare_source_answer(item,supplied):
    if item.get('usage_group')!='core_candidates' or not item.get('answer_spec'):
        return {'status':'NOT_ASSESSED','production_grade':False,'score':None}
    spec=item['answer_spec']
    if spec['kind']=='NUMBER':
        value=decimal_answer(str(supplied))
        if value is None:return {'status':'INVALID_ANSWER_FORMAT','production_grade':False,'score':None}
        match=value==Decimal(spec['expected_decimal'])
    elif spec['kind']=='MULTIPLE_CHOICE':
        value=str(supplied).strip().upper()
        if value not in 'ABCD' or len(value)!=1:return {'status':'INVALID_ANSWER_FORMAT','production_grade':False,'score':None}
        match=value==spec['expected_label']
    else:return {'status':'NOT_ASSESSED','production_grade':False,'score':None}
    return {'status':'MATCHES_SOURCE_ANSWER' if match else 'DIFFERS_FROM_SOURCE_ANSWER',
            'scope':'FINAL_ANSWER_AGAINST_PRINTED_SOURCE_KEY','production_grade':False,'score':None}


def classify(row,asset_errors=()):
    reasons=list(asset_errors)
    for role in ['question','solution']:
        part=row['parts'][role]
        if not part['source_spans'] or not part['fragments']:reasons.append(role.upper()+'_SOURCE_MISSING')
    if reasons:return 'held_items',reasons,None
    answer=explicit_answer(row)
    if any(i['code']=='SOURCE_RECHECK_NOT_RUN' for i in row['issues']):
        return 'image_reference',['SOURCE_RECHECK_NOT_RUN'],answer
    choices=row['parts']['question']['choices']
    if answer and answer['kind']=='MULTIPLE_CHOICE':
        source_labels=re.findall(r'(?<!\w)([ABCD])[.)]\s',row['parts']['question'].get('raw_text_lossy',''))
        if source_labels!=list('ABCD'):return 'image_reference',['SOURCE_CHOICE_LABELS_NOT_COMPLETE_ABCD'],None
    if answer:
        # Full original question/solution images are preserved. Text uncertainty
        # blocks step grading, not matching a separately legible source answer.
        for question in row['parts']['question']['source_spans']:
            for key in row['parts'].get('answer',{}).get('source_spans',[]):
                if question['page_number']==key['page_number'] and 'bbox' in question and 'bbox' in key:
                    a,b=question['bbox'],key['bbox']
                    if min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1]):
                        return 'held_items',['QUESTION_OVERLAPS_ANSWER_REGION'],None
        return 'core_candidates',[],answer
    if [c['label'] for c in choices]!=list('ABCD') or not all(meaningful(c['markdown']) for c in choices):
        reasons.append('CHOICES_NOT_COMPLETE_ABCD')
    reasons.extend(sorted({i['code'] for i in row['issues']}))
    if any(not f.get('display_latex') for f in row['formula_candidates'] if f['role'] in ['question','solution']):
        reasons.append('FORMULAS_REQUIRE_SOURCE_IMAGE')
    if any(c.get('display_text') is None for t in row['tables'] for c in t['cells']):reasons.append('TABLE_REQUIRES_SOURCE_IMAGE')
    if not answer:reasons.append('NO_UNAMBIGUOUS_EXPLICIT_SOURCE_ANSWER')
    return ('image_reference' if reasons else 'core_candidates'),sorted(set(reasons)),answer


def export(transcripts,output,*,plan=None,katex=None):
    from .paired.transcription_v2.checkpoints import asset_hashes,record_validator
    transcripts,output=Path(transcripts).resolve(),Path(output).resolve()
    if transcripts==output:raise ValueError('SEPARATE_CURATED_OUTPUT_REQUIRED')
    report=read_json(transcripts/'report.json');identity=report['pipeline_identity']
    output.mkdir(parents=True,exist_ok=True);groups={k:[] for k in ['core_candidates','image_reference','held_items']}
    catalog=[];all_rows=[];copied={};source_before={}
    from .source_recheck import SourceReplay
    replay=SourceReplay(plan,katex) if plan and katex else None
    paths=list((transcripts/'records').glob('*.json'))
    def order(path):
        q=read_json(path)
        return q['source']['sha256'],min((s['page_number'] for p in q['parts'].values() for s in p['source_spans']),default=0)
    try:
      for path in sorted(paths,key=order):
        row=read_json(path)
        if row.get('pipeline_identity')!=identity:continue
        source_before[str(path)]=file_hash(path);errors=[]
        record_validator().validate(row)
        if replay:
            try:row=replay(row)
            except (OSError,ValueError,KeyError) as error:
                errors.append('SOURCE_RECHECK_FAILED:'+type(error).__name__)
                row['source_recheck']={'status':'FAILED','error':str(error)[:300]}
        else:row['issues'].append({'code':'SOURCE_RECHECK_NOT_RUN'})
        for relative,digest in asset_hashes(row).items():
            source=(transcripts/relative).resolve();target=(output/relative).resolve()
            if not source.is_relative_to(transcripts/'assets') or not target.is_relative_to(output/'assets'):
                errors.append('ASSET_PATH_INVALID');continue
            if not source.is_file() or file_hash(source)!=digest:
                errors.append('SOURCE_ASSET_MISSING_OR_CHANGED');continue
            if relative in copied and copied[relative]!=digest:raise ValueError('ASSET_IDENTITY_CONFLICT')
            if not target.is_file() or file_hash(target)!=digest:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            copied[relative]=digest
        group,reasons,answer=classify(row,errors)
        item={'schema_version':'curated-question/v1','question_id':row['question_id'],
              'collection_number':row['collection_number'],'chapter_id':row['chapter_id'],
              'chapter_title':row['chapter_title'],'source':row['source'],'usage_group':group,
              'routing_policy':POLICY,'routing_reasons':reasons,'parts':row['parts'],
              'answer_spec':answer,'reference_solution':{'markdown':row['parts']['solution']['markdown'],
                  'source_fragments':row['parts']['solution']['fragments'],'step_candidates':[],
                  'step_grading':'NOT_ASSESSED'},
              'academic_review':'PENDING','publishable':False,'production_grade':False,
              'grading_support':'SOURCE_FINAL_ANSWER_CANDIDATE' if group=='core_candidates' else 'NOT_ASSESSED',
              'source_record_sha256':source_before[str(path)],'source_pipeline_identity':identity,
              'source_recheck':row.get('source_recheck'),'math_expressions':row['formula_candidates']}
        typed_choices=not answer or answer['kind']!='MULTIPLE_CHOICE' or ([c['label'] for c in row['parts']['question']['choices']]==list('ABCD') and all(meaningful(c['markdown']) for c in row['parts']['question']['choices']))
        item['presentation_mode']='TEXT_AND_LATEX_DRAFT' if typed_choices and not row['issues'] and all(f.get('display_latex') for f in row['formula_candidates']) else 'SOURCE_IMAGES'
        item['text_review_reasons']=sorted({i['code'] for i in row['issues']})
        item['supported_grading_scope']='SOURCE_FINAL_ANSWER_ONLY' if group=='core_candidates' else 'NONE'
        item['step_grading_ready']=False
        item['assessment_ready']=False
        if item['presentation_mode']=='SOURCE_IMAGES' and answer and answer['kind']=='MULTIPLE_CHOICE':
            item['source_question_may_highlight_correct_option']=True
        groups[group].append(item);all_rows.append(item)
        record='records/q-'+content_hash(row['question_id'])[:24]+'.json';write_json(output/record,item)
        catalog.append({'number':row['collection_number'],'question_id':row['question_id'],
                        'chapter':row['chapter_title'],'group':group,'reasons':reasons,'record':record})
    finally:
      if replay:replay.close()
    for group,items in groups.items():write_jsonl(output/(group+'.jsonl'),items)
    write_jsonl(output/'metadata.final.jsonl',all_rows);write_json(output/'metadata.final.pretty.json',all_rows)
    summary={'status':'CURATED_DRAFT_COMPLETE' if report['status']=='COMPLETE_DRAFT' and len(all_rows)==report['selected_questions'] else 'CURATED_PARTIAL_DRAFT',
             'policy':POLICY,'questions':len(all_rows),'counts':{g:len(items) for g,items in groups.items()},
             'images_verified':len(copied),'core_candidates_are_academically_approved':False,
             'production_grading_ready':0,'upstream_status':report['status'],
             'source_records_unchanged':all(file_hash(Path(p))==sha for p,sha in source_before.items()),
             'reason_counts':dict(Counter(r for q in all_rows for r in q['routing_reasons'])),
             'cloud_api_calls':0,'final_jsonl':str(output/'metadata.final.jsonl')}
    summary['answer_kinds']=dict(Counter(q['answer_spec']['kind'] for q in groups['core_candidates']))
    summary['image_backed_final_answer_candidates']=sum(q['presentation_mode']=='SOURCE_IMAGES' for q in groups['core_candidates'])
    summary['step_grading_ready']=0
    write_json(output/'summary.json',summary);write_json(output/'catalog.json',{'summary':summary,'questions':catalog})
    shutil.copy2(Path(__file__).with_name('curation_view.html'),output/'index.html')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--transcripts',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--plan',type=Path);p.add_argument('--katex',type=Path)
    p.add_argument('--check-record',type=Path);p.add_argument('--answer')
    a=p.parse_args()
    if a.check_record:result=compare_source_answer(read_json(a.check_record),a.answer or '')
    else:
        if not a.transcripts or not a.output:p.error('Use --transcripts and --output, or --check-record and --answer.')
        result=export(a.transcripts,a.output,plan=a.plan,katex=a.katex)
    print(json.dumps(result,ensure_ascii=False,indent=2))
