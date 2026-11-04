"""Frozen page-layout smoke on a PDF outside the fixed solved-pair sample.

This PDF has no accepted solved pairs. Page diagnostics never manufacture a
solution or become grading content. OCR is bounded by a declared region budget.
"""
import argparse
from pathlib import Path
import json

from ...storage import configure_storage,file_hash,read_json,write_json
from ..transcript_batch import Syntax,content_hash
from .batch import code_identity,viewer
from .engine import CachedReader,process


class BudgetReader:
    def __init__(self,reader,limit):self.reader=reader;self.limit=limit
    @property
    def calls(self):return self.reader.calls
    @property
    def hits(self):return self.reader.hits
    def read(self,image):
        if self.calls>=self.limit:raise ValueError('HOLDOUT_OCR_BUDGET_REACHED_IMAGE_RETAINED')
        return self.reader.read(image)


def run(args):
    import pdfplumber
    plan=read_json(args.plan);source=Path(plan['source']['path']);output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    if file_hash(source)!=plan['source']['sha256']:raise ValueError('HOLDOUT_SOURCE_HASH_CHANGED')
    configure_storage(args.runtime);identity=content_hash({'code':code_identity(),'plan':plan,'scope':plan['scope'],'ocr_budget_per_model':60})
    primary=BudgetReader(CachedReader(args.runtime.resolve(),output,'PP-FormulaNet_plus-M',{}),60)
    secondary=BudgetReader(CachedReader(args.runtime.resolve(),output,'PP-FormulaNet_plus-S',{}),60)
    syntax=Syntax(args.katex.resolve());pages={};items=[];report={'scope':plan['scope'],'pipeline_identity':identity,
        'frozen_page_selection':plan['pages'],'solved_pairs_created':0,'mathematical_accuracy_established':False,'cloud_calls':0,'publishable':False}
    write_json(output/'frozen-run.json',{'plan':plan,'code_identity':code_identity(),'identity':identity})
    try:
        with pdfplumber.open(source) as pdf:
            for pn in plan['pages']:
                raw=pdf.pages[pn-1]
                q={'question_id':'page-smoke:'+plan['source']['sha256'][:16]+':'+str(pn),'collection_number':pn,
                    'source_label':'Trang '+str(pn),'chapter_id':'derivative_applications','chapter_title':'Chẩn đoán trang PDF ngoài mẫu',
                    'source':{'sha256':plan['source']['sha256'],'name':plan['source']['label']},
                    'question':{'source_spans':[{'page_number':pn,'bbox':[0,0,raw.width,raw.height]}]},
                    'solution':{'source_spans':[]},'answer':{'source_spans':[]}}
                row=process(q,pdf,pages,output,primary,secondary,syntax,identity)
                row['scope']=plan['scope'];row['is_question_solution_pair']=False
                target='records/page-'+str(pn)+'.json';write_json(output/target,row)
                items.append({'question_id':q['question_id'],'number':pn,'label':q['source_label'],'chapter_id':q['chapter_id'],
                    'chapter_title':q['chapter_title'],'source_name':q['source']['name'],'evaluation':False,'status':row['transcript_status'],
                    'issues':len(row['issues']),'formulas':len(row['formula_candidates']),'record':target})
                report.update(completed_pages=len(items),formula_regions=sum(i['formulas'] for i in items),
                    table_regions=sum(len(read_json(output/i['record'])['tables']) for i in items),ocr_calls=primary.calls+secondary.calls)
                write_json(output/'report.json',report);print('[holdout-v2]',pn,'tables',len(row['tables']),'formulas',len(row['formula_candidates']),flush=True)
    finally:syntax.close()
    if file_hash(source)!=plan['source']['sha256']:raise ValueError('HOLDOUT_SOURCE_MODIFIED')
    viewer(output,args.katex.resolve())
    report.update(status='COMPLETE_SCOPED_PAGE_SMOKE',completed_questions=len(items),selected_questions=len(plan['pages']),
        evaluation_completed=0,source_documents=1,pages=plan['pages'])
    write_json(output/'catalog.json',{'report':report,'questions':items});write_json(output/'report.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['plan','output','runtime','katex']:p.add_argument('--'+name,type=Path,required=True)
    print(json.dumps(run(p.parse_args()),indent=2,ensure_ascii=False))
