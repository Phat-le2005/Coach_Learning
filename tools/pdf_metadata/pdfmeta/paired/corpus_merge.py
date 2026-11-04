"""Merge all profiled documents, never silently omit a failed or empty source."""
import json
from pathlib import Path
import shutil

from ..storage import file_hash,read_json,write_json,write_jsonl
from .corpus import CHAPTERS,code_identity


def merge(root,output,archive):
    root,output,archive=Path(root).resolve(),Path(output).resolve(),Path(archive).resolve()
    profile=read_json(root/'profile.json');output.mkdir(parents=True,exist_ok=True)
    (output/'assets').mkdir(exist_ok=True);(output/'questions').mkdir(exist_ok=True)
    records=[];documents=[];queue=[];page_queue=[];images={};seen=set();summaries=[]
    for chapter in CHAPTERS:
        for source in profile:
            if source['chapter']!=chapter:continue
            work=root/'documents'/source['sha256'][:24];report_path=work/'solved/report.json'
            if not report_path.is_file():raise ValueError('DOCUMENT_NOT_ACCOUNTED_FOR: '+source['document_id'])
            report=read_json(report_path)
            if report.get('source_code_hash')!=code_identity():raise ValueError('DOCUMENT_ADAPTER_REQUIRES_RERUN')
            if report['source_pdf_sha256']!=source['sha256'] or file_hash(Path(source['path']))!=source['sha256']:
                raise ValueError('CORPUS_DOCUMENT_SOURCE_CHANGED')
            if file_hash(Path(report['questions_jsonl']))!=report['questions_sha256']:raise ValueError('DOCUMENT_QUESTIONS_CHANGED')
            if file_hash(Path(report['review_jsonl']))!=report['review_sha256']:raise ValueError('DOCUMENT_REVIEW_QUEUE_CHANGED')
            page_queue.extend({'document_id':source['document_id'],'chapter_id':chapter,**entry}
                for entry in read_json(work/'solved/page-review-queue.json'))
            effective={**report,'chapter_title':CHAPTERS[chapter],'source_adapter_selected_pairs':report['selected_pairs'],
                'review_reasons':dict(report['review_reasons'])}
            documents.append(effective);record_start=len(records);held=0
            for line in Path(report['questions_jsonl']).read_text(encoding='utf-8').splitlines():
                q=json.loads(line)
                if q['question_id'] in seen:raise ValueError('DUPLICATE_CORPUS_QUESTION_ID')
                if q['source']['sha256']!=source['sha256'] or q['chapter_id']!=chapter:raise ValueError('QUESTION_SOURCE_OR_CHAPTER_MISMATCH')
                if q['pair_status']!='PAIRED_LAYOUT_CANDIDATE' or q['publishable'] is not False:raise ValueError('UNEXPECTED_CORPUS_PROMOTION')
                # OCR can miss a new heading and attach another exercise as a
                # proof. Keep these occurrences for a dedicated source review,
                # rather than presenting them as solved source pairs.
                if any('ocr-' in bid for role in ['question','solution','answer']
                        for span in q[role]['source_spans'] for bid in span['block_ids']):
                    queue.append({'document_id':source['document_id'],'chapter_id':chapter,
                        'question_id':q['question_id'],'source_number':q['source_number'],'source_label':q.get('source_label'),
                        'source_pdf_sha256':source['sha256'],'reasons':['OCR_PAIR_REQUIRES_SOURCE_REVIEW'],
                        'source_regions':[{k:v for k,v in s.items() if k not in {'asset_path','asset_sha256'}}
                            for s in q['collection_source_spans']]})
                    held+=1;continue
                seen.add(q['question_id']);q['collection_number']=len(records)+1
                for span in q['collection_source_spans']:
                    original=(work/'solved'/span['asset_path']).resolve()
                    if not original.is_relative_to(work/'solved') or file_hash(original)!=span['asset_sha256']:raise ValueError('CORPUS_SOURCE_ASSET_CHANGED')
                    key='assets/'+source['document_id']+'-'+original.name;target=output/key
                    if not target.exists() or file_hash(target)!=span['asset_sha256']:shutil.copy2(original,target)
                    span['asset_path']=key;images[key]={'sha256':span['asset_sha256'],'url':key}
                import hashlib
                record_path='questions/q-'+hashlib.sha256(q['question_id'].encode()).hexdigest()[:24]+'.json'
                write_json(output/record_path,q)
                summaries.append({'question_id':q['question_id'],'number':q['collection_number'],'source_number':q['source_number'],
                    'source_label':q.get('source_label'),'chapter_id':chapter,'record':record_path,
                    'preview':q['question']['text_lossy'][:180],'source_name':q['source']['name']})
                records.append(q)
            effective['selected_pairs']-=held;effective['unselected_occurrences']+=held
            if held:effective['review_reasons']['OCR_PAIR_REQUIRES_SOURCE_REVIEW']=held
            covered={s['page_number'] for q in records[record_start:] for s in q['collection_source_spans']}
            queued={s['page_number'] for s in page_queue if s['document_id']==source['document_id']}
            for n in set(range(1,source['pages']+1))-covered-queued:
                page_queue.append({'document_id':source['document_id'],'chapter_id':chapter,'page_number':n,
                    'reason':'NO_ACCEPTED_SOLVED_REGION_ON_PAGE_AFTER_CURATION'})
            effective['page_review_count']=sum(s['document_id']==source['document_id'] for s in page_queue)
            for line in Path(report['review_jsonl']).read_text(encoding='utf-8').splitlines():
                queue.append({'document_id':source['document_id'],'chapter_id':chapter,**json.loads(line)})
    chapters=[{'id':c,'title':t,'documents':sum(d['chapter_id']==c for d in documents),
        'source_pages':sum(d['pages'] for d in documents if d['chapter_id']==c),
        'questions':sum(q['chapter_id']==c for q in records)} for c,t in CHAPTERS.items()]
    import hashlib
    generation=hashlib.sha256(json.dumps({'documents':[(d['source_pdf_sha256'],d['source_code_hash'],d['questions_sha256'])
        for d in documents],'curation_code':file_hash(Path(__file__))},sort_keys=True).encode()).hexdigest()[:24]
    data={'schema_version':'solved-corpus/v1','title':'Toán 12 - Câu hỏi kèm lời giải',
        'generation_id':generation,
        'source':{'name':archive.name,'sha256':file_hash(archive),'kind':'PDF' if archive.suffix.lower()=='.pdf' else 'SOURCE_ARCHIVE_NOT_A_SINGLE_PDF',
            'page_count':sum(d['pages'] for d in documents)},'chapters':chapters,'documents':documents,
        'questions':records,'unpaired_questions':[],'images':images,
        'policy':{'production_grade':False,'academic_review':'PENDING','question_count_is_occurrences_not_unique_problems':True,
            'native_text_is_lossy':True,'formulas_preserved_as_source_images':True,'ocr_question_pairs_exported':False,'cloud_api_calls':0}}
    write_json(output/'questions.metadata.json',data);write_jsonl(output/'questions.metadata.jsonl',records)
    write_jsonl(output/'review-queue.jsonl',queue)
    write_jsonl(output/'page-review-queue.jsonl',page_queue)
    write_json(output/'index-data.json',{'title':data['title'],'chapters':chapters,'documents':documents,'questions':summaries})
    shutil.copy2(Path(__file__).with_name('corpus_index.html'),output/'index.html')
    report={'schema_version':'solved-corpus-report/v1','documents_accounted_for':len(documents),'source_pages':data['source']['page_count'],
        'generation_id':generation,
        'selected_pairs':len(records),'unselected_occurrences':len(queue),'chapters':chapters,
        'local_text_ocr_calls':sum(d['ocr_calls'] for d in documents),'ocr_errors':sum(len(d['ocr_errors']) for d in documents),
        'page_review_count':sum(d['page_review_count'] for d in documents),'metadata_json':str(output/'questions.metadata.json'),
        'metadata_jsonl':str(output/'questions.metadata.jsonl'),'review':str(output/'index.html'),
        'metadata_sha256':file_hash(output/'questions.metadata.json'),'cloud_api_calls':0,'production_grade':False}
    report['local_text_ocr_pages']=sum(len(d['ocr_pages']) for d in documents)
    report['local_text_ocr_cache_hits']=sum(d['ocr_cache_hits'] for d in documents)
    report['page_review_jsonl']=str(output/'page-review-queue.jsonl')
    report['review_reasons']={}
    for entry in queue:
        for reason in entry['reasons']:report['review_reasons'][reason]=report['review_reasons'].get(reason,0)+1
    write_json(output/'report.json',report);write_json(root/'corpus-result.json',report)
    return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);a=p.parse_args()
    print(json.dumps(merge(a.root,a.output,a.archive),ensure_ascii=False,indent=2))
