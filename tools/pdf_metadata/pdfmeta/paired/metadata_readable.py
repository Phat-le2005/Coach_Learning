"""Format metadata for people without rewriting source text or grading states.

Standard-library-only, also callable by the standalone PDF renderer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def has_unmapped_glyphs(text):
    """Detect damaged encodings, without claiming clean text preserves math layout."""
    return any(char == '\ufffd' or 0xE000 <= ord(char) <= 0xF8FF
               or 0xF0000 <= ord(char) <= 0xFFFFD or 0x100000 <= ord(char) <= 0x10FFFD
               for char in (text or ''))


FRONT_FIELDS=('collection_number','source_label','chapter_title','question','solution','answer',
    'source','collection_pdf_pages','academic_review','grading_support','publishable','question_id')


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):result.update(chunk)
    return result.hexdigest()


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix(path.suffix+'.pending')
    pending.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    pending.replace(path)


def export(source,output=None):
    source=Path(source).resolve();output=Path(output or source.parent).resolve()
    if source.suffix.lower()!='.jsonl':raise ValueError('JSONL_INPUT_REQUIRED')
    output.mkdir(parents=True,exist_ok=True);fingerprint=digest(source)
    name=source.stem+'.pretty.json';pretty=output/name;pending=pretty.with_suffix('.json.pending')
    entries=[];chapters={};documents={};seen=set()
    try:
        with source.open(encoding='utf-8-sig') as raw,pending.open('w',encoding='utf-8',newline='\n') as target:
            target.write('[\n')
            for line in raw:
                if not line.strip():continue
                q=json.loads(line)
                if not isinstance(q,dict) or not isinstance(q.get('question_id'),str):raise ValueError('QUESTION_ID_REQUIRED')
                if q['question_id'] in seen:raise ValueError('DUPLICATE_QUESTION_ID')
                seen.add(q['question_id'])
                ordered={k:q[k] for k in FRONT_FIELDS if k in q}
                ordered.update((k,v) for k,v in q.items() if k not in ordered)
                text=json.dumps(ordered,ensure_ascii=False,indent=2,allow_nan=False)
                if entries:target.write(',\n')
                target.write('  '+text.replace('\n','\n  '))
                key='metadata-records/'+fingerprint[:16]+'/q-'+hashlib.sha256(q['question_id'].encode()).hexdigest()[:24]+'.json'
                save(output/key,ordered)
                chapter=q.get('chapter_id') or 'unclassified';title=q.get('chapter_title') or 'Chưa phân nhóm'
                chapter_row=chapters.setdefault(chapter,{'id':chapter,'title':title,'count':0});chapter_row['count']+=1
                src=q.get('source',{});doc_id=src.get('sha256') or q.get('document_id') or src.get('name') or 'unknown'
                doc=documents.setdefault(doc_id,{'id':doc_id,'name':src.get('name') or 'Chưa ghi nguồn','count':0});doc['count']+=1
                source_pages=sorted({s['page_number'] for role in ['question','solution','answer']
                    for s in q.get(role,{}).get('source_spans',[])})
                entries.append({'id':q['question_id'],'number':q.get('collection_number',len(entries)+1),
                    'label':q.get('source_label') or 'Câu '+str(q.get('source_number','')),'chapter_id':chapter,
                    'document_id':doc_id,'record':key,'preview':q.get('question',{}).get('text_lossy','')[:220],
                    'source_name':doc['name'],'source_pages':source_pages,'pdf_pages':q.get('collection_pdf_pages',[]),
                    'damaged_text_roles':[role for role,key in [('question','text_lossy'),('solution','text_lossy'),('answer','text_raw')]
                        if has_unmapped_glyphs(q.get(role,{}).get(key))]})
            target.write('\n]\n')
        if digest(source)!=fingerprint:raise ValueError('CANONICAL_METADATA_CHANGED_DURING_FORMATTING')
        pending.replace(pretty)
    except BaseException:
        pending.unlink(missing_ok=True);raise
    context_path=source.parent/'index-data.json'
    if context_path.is_file():
        context=json.loads(context_path.read_text(encoding='utf-8'))
        if {q.get('question_id') for q in context.get('questions',[])}==seen:
            # Account for inventoried PDFs that contributed zero selected pairs.
            for doc in context.get('documents',[]):
                key=doc.get('source_pdf_sha256')
                if key and key not in documents:
                    documents[key]={'id':key,'name':Path(doc.get('label','Chưa ghi nguồn')).name,'count':0}
    # The catalogue stays small; only the selected record and its images load.
    save(output/'metadata-catalog.json',{'schema_version':'readable-metadata-catalog/v1',
        'count':len(entries),'source_sha256':fingerprint,'pretty_file':name,
        'chapters':list(chapters.values()),'documents':list(documents.values()),'questions':entries})
    shutil.copy2(Path(__file__).with_name('metadata_readable.html'),output/'metadata.html')
    report={'questions':len(entries),'chapters':len(chapters),'documents':len(documents),
        'source_jsonl':str(source),'source_sha256':fingerprint,'pretty_json':str(pretty),
        'pretty_sha256':digest(pretty),'viewer':str(output/'metadata.html'),
        'record_directory':'metadata-records/'+fingerprint[:16],
        'policy':'PRESENTATION_ONLY_SOURCE_VALUES_AND_REVIEW_STATES_UNCHANGED','inference_calls':0}
    save(output/'metadata-format.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path);a=p.parse_args()
    print(json.dumps(export(a.input,a.output),ensure_ascii=False,indent=2))
