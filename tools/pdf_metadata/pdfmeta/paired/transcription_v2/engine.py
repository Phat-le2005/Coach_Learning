"""Layout-first engine with read-only reuse of checksum-verified v1 OCR."""
from pathlib import Path
from collections import OrderedDict
import hashlib
import json
import os
import shutil
import time
import re

from ...storage import configure_storage,file_hash,read_json,write_json
from ...native import box
from ...source_layout import inspect
from ...safe_math import UnsupportedMath
from ..math_recovery import FormulaReader,extract_page
from ..transcript_batch import Syntax,content_hash,now,trusted_native
from ..transcript_regions import assemble,audit_coverage,crop_box,visual_flags
from ..transcript_quality import display_decision
from . import VERSION
from .glyphs import canonical_page,glyph_lookup
from .tables import detect,for_span,cell_kind,native_text,markdown
from .layout import prepare
from .geometry import render
from .checkpoints import save_checkpoint,valid_checkpoint


class CachedReader(FormulaReader):
    def __init__(self,runtime,output,model,index,cache_mode='local'):
        super().__init__(runtime,output,model);self.index=index;self.reused=0;self.cache_mode=cache_mode
    def read(self,image):
        identity={**self.identity,'image_sha256':file_hash(image)}
        key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        target=self.output/'ocr-cache'/(key+'.json')
        if self.cache_mode!='cold' and not target.exists() and key in self.index:
            item=self.index[key];p=Path(item['path'])
            if file_hash(p)!=item['sha256']:raise ValueError('BASELINE_OCR_CACHE_CHANGED')
            old=read_json(p)
            if old.get('identity')==identity:
                write_json(target,old);self.reused+=1
        return super().read(image,use_cache=self.cache_mode!='cold')


class BoundedPages(OrderedDict):
    """Evict parsed glyph/vector objects and pdfplumber's heavy page caches."""
    def __init__(self,pdf,limit=8):
        super().__init__();self.pdf=pdf;self.limit=limit;self.peak=0
    def __getitem__(self,key):
        value=super().__getitem__(key);self.move_to_end(key);return value
    def __setitem__(self,key,value):
        super().__setitem__(key,value);self.move_to_end(key)
        while len(self)>self.limit:
            old,_=self.popitem(last=False);self.pdf.pages[old-1].close()
        self.peak=max(self.peak,len(self))


def candidate(f,page,asset,reader,secondary,syntax):
    lookup=glyph_lookup(page);gs=[lookup[k] for k in f['source_glyph_keys']]
    native=trusted_native(f,page);evidence=[];rejection=None
    if not native:
        try:
            native,evidence=render(gs,page['vectors']);signals=inspect(page,f['bbox'])
            kinds={e['kind'] for e in evidence}
            if signals.get('overlines') and 'OVERLINE' not in kinds:raise UnsupportedMath('OVERLINE_OWNERSHIP_NOT_ESTABLISHED')
            if signals.get('top_bars') and not kinds & {'FRACTION','OVERLINE'}:raise UnsupportedMath('TOP_RULE_OWNERSHIP_NOT_ESTABLISHED')
            if signals.get('absolute_bars') and not re.search(r'\||\\(?:[lr]?vert|abs)\b',native):raise UnsupportedMath('ABSOLUTE_BARS_INCOMPLETE')
            if signals.get('lower_glyphs') and not kinds & {'FRACTION','SUBSCRIPT','ASSEMBLED_BRACKET'}:raise UnsupportedMath('LOWER_GLYPH_OWNERSHIP_NOT_ESTABLISHED')
        except (UnsupportedMath,ValueError,TypeError,KeyError) as e:rejection=str(e)
        if rejection:native=None
    second=None;error=None
    if native:
        latex=native;method='V2_NATIVE_GEOMETRY_DRAFT' if evidence else 'NATIVE_SUPPORTED_GEOMETRY_DRAFT'
        check=syntax(latex);quality={'display_latex':latex if check['status']=='PASS' else None,'issues':[],
            'status':'SOURCE_GEOMETRY_DRAFT','academic_review':'PENDING','publishable':False}
    else:
        method='LOCAL_FORMULA_IMAGE_READING'
        if getattr(reader,'deferred',False):
            return {'latex_candidate':'','secondary_latex_candidate':None,'display_latex':None,
                    'syntax':{'status':'OCR_DEFERRED'},'transcription_checks':{'issues':['OCR_DEFERRED_BY_PROFILE']},
                    'method':'SOURCE_IMAGE_NATIVE_PROFILE','geometry_evidence':evidence,'geometry_rejection':rejection,
                    'region_error':None,'comparison':'DRAFT_SOURCE_CHECK_REQUIRED','status':'IMAGE_FALLBACK'}
        try:
            latex=reader.read(asset);second=secondary.read(asset);check=syntax(latex)
            quality=display_decision(''.join(g['text'] for g in gs),latex,second,check,inspect(page,f['bbox']))
        except Exception as e:
            error=type(e).__name__+': '+str(e);latex='';check={'status':'MODEL_REGION_ERROR'}
            quality={'display_latex':None,'issues':['REGION_MODEL_FAILED_IMAGE_RETAINED'],'status':'IMAGE_FALLBACK'}
    return {'latex_candidate':latex,'secondary_latex_candidate':second,'display_latex':quality['display_latex'],
        'syntax':check,'transcription_checks':quality,'method':method,'geometry_evidence':evidence,
        'geometry_rejection':rejection,'region_error':error,'comparison':'DRAFT_SOURCE_CHECK_REQUIRED',
        'status':'INFERRED_NOT_ACADEMICALLY_REVIEWED'}


def source_crop(raw,bbox,output,asset,dpi):
    # PDFium and pdfplumber round page dimensions differently. Allow only
    # sub-millipoint drift; genuinely out-of-page source regions still fail.
    left,top,right,bottom=raw.bbox
    clipped=(max(left,bbox[0]),max(top,bbox[1]),min(right,bbox[2]),min(bottom,bbox[3]))
    if any(abs(a-b)>.001 for a,b in zip(bbox,clipped)):
        raise ValueError('SOURCE_CROP_OUTSIDE_PAGE')
    raw.crop(clipped).to_image(resolution=dpi).save(output/asset)
    return file_hash(output/asset)


def process(q,pdf,pages,output,reader,secondary,syntax,identity):
    start=time.perf_counter();before=(reader.calls,secondary.calls,reader.hits,secondary.hits)
    num=q['collection_number'];destination=output/'assets'/f'q{num:04}';destination.mkdir(parents=True,exist_ok=True)
    row={'schema_version':VERSION,'question_id':q['question_id'],'collection_number':num,
         'source_label':q['source_label'],'chapter_id':q['chapter_id'],'chapter_title':q['chapter_title'],
         'source':q['source'],'pipeline_identity':identity,'checkpoint_identity':content_hash({'source_record':q,'pipeline':identity}),
         'source_record_sha256':content_hash(q),'parts':{},'formula_candidates':[],'tables':[],'figures':[],
         'issues':[],'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False}
    for role in ['question','solution','answer']:
        part={'markdown':'','choices':[],'source_spans':q[role].get('source_spans',[]),
              'raw_text_lossy':q[role].get('text_lossy',q[role].get('text_raw')),'fragments':[]}
        for si,span in enumerate(part['source_spans']):
            pn=span['page_number'];raw=pdf.pages[pn-1];base=f'assets/q{num:04}/{role}-{si:02}'
            source_asset=base+'-source.png';source_sha=source_crop(raw,span['bbox'],output,source_asset,150)
            if pn not in pages:
                page=canonical_page(extract_page(raw,pn,q['source']['sha256']))
                page['images']=[{'bbox':box(i)} for i in raw.images];pages[pn]=(page,detect(raw,page))
            page,alltables=pages[pn];lookup=glyph_lookup(page);tables=for_span(alltables,span)
            for ti,t in enumerate(tables):
                t=dict(t,table_id=f'{role}-{si:02}-table-{ti:02}',role=role)
                t['cells']=[dict(c) for c in t['cells']];t['asset_path']=base+f'-table-{ti:02}.png'
                t['asset_sha256']=source_crop(raw,t['bbox'],output,t['asset_path'],200)
                for cell in t['cells']:
                    gs=[lookup[k] for k in cell['source_glyph_keys']];kind=cell_kind(gs,cell['text_native_display'])
                    cell['kind']=kind;cell['display_text']=None;cell['display_latex']=None
                    if kind in {'EMPTY','TEXT','NUMBER'}:cell['display_text']=cell['text_native_display']
                    elif kind=='MATH_OR_SYMBOLS':
                        try:
                            latex,ev=render(gs,page['vectors']);check=syntax(latex)
                            if check['status']=='PASS':cell.update(display_text='$'+latex+'$',display_latex=latex,geometry_evidence=ev)
                        except (UnsupportedMath,ValueError,TypeError):pass
                    cell['status']='NATIVE_DRAFT' if cell['display_text'] is not None else 'SOURCE_IMAGE_REQUIRED'
                    if cell['display_text'] is None:
                        cell['asset_path']=base+f'-table-{ti:02}-cell-{cell["row"]:02}-{cell["column"]:02}.png'
                        cell['asset_sha256']=source_crop(raw,cell['bbox'],output,cell['asset_path'],200)
                row['tables'].append(t)
            localtables=[t for t in row['tables'] if t['role']==role and t['table_id'].startswith(f'{role}-{si:02}-')]
            masked,formulas,rows,errors,figures=prepare(page,span,tables);processed=[]
            for fi,f in enumerate(formulas):
                asset=base+f'-formula-{fi:03}.png';crop=crop_box(masked,f,span,rows)
                digest=source_crop(raw,crop,output,asset,288)
                value=candidate(f,page,output/asset,reader,secondary,syntax)
                processed.append({**f,**value,'formula_id':f'{role}-{si:02}-{fi:03}','role':role,
                    'page_number':pn,'crop_bbox':crop,'asset_path':asset,'asset_sha256':digest})
            coverage=audit_coverage(rows,processed,errors);transcription=assemble(rows,processed)
            # Tables have been masked from formula/prose ownership. Ordered
            # typed blocks preserve their original page/box instead of claiming
            # that a grid is an ordinary paragraph or a giant fraction.
            blocks=[{'kind':'TRANSCRIBED_TEXT_DRAFT','bbox':span['bbox'],'markdown':transcription['markdown']}]
            for t in localtables:
                blocks.append({'kind':'TABLE','bbox':t['bbox'],'table_id':t['table_id'],'markdown':markdown(t)})
            for ii,fig in enumerate(figures):
                b=[max(a,c) if j<2 else min(a,c) for j,(a,c) in enumerate(zip(fig['bbox'],span['bbox']))]
                asset=base+f'-figure-{ii:02}.png';sha=source_crop(raw,b,output,asset,180)
                row['figures'].append({'role':role,'page_number':pn,'bbox':b,'asset_path':asset,'asset_sha256':sha,'status':'SOURCE_IMAGE'})
                blocks.append({'kind':'FIGURE','bbox':b,'markdown':f'![Hình nguồn]({asset})'})
            flags=visual_flags(masked,span)
            flags.extend(transcription.get('choice_issues',[]))
            if any(b.get('alignment_error') and any(span['bbox'][0]<=g['bbox'][0]<=span['bbox'][2] and span['bbox'][1]<=g['bbox'][1]<=span['bbox'][3] for g in b['glyphs']) for b in page['blocks']):
                flags.append('SOURCE_LINE_ALIGNMENT_IMAGE_RETAINED')
            if localtables:flags.append('NATIVE_TABLE_GRID_EXTRACTED_DRAFT')
            if any(c['display_text'] is None for t in localtables for c in t['cells']):flags.append('TABLE_CELLS_REQUIRE_IMAGE')
            if errors:flags.append('UNMAPPED_SOURCE_ROWS')
            if any('□' in r['text'] for r in rows):flags.append('UNMAPPED_SOURCE_GLYPHS_IMAGE_RETAINED')
            if any(not f['display_latex'] for f in processed):flags.append('FORMULA_CANDIDATES_HELD_FOR_SOURCE_REVIEW')
            if coverage['uncovered_suspect_glyph_keys']:flags.append('UNCOVERED_SUSPECT_MATH_GLYPHS')
            if not rows and not localtables:flags.append('NO_READABLE_SOURCE_GLYPHS')
            text='\n\n'.join(b['markdown'] for b in blocks if b['markdown'])
            if flags:text+='\n\n![Vùng nguồn cần đối chiếu]('+source_asset+')'
            fragment={'page_number':pn,'bbox':span['bbox'],'source_asset':source_asset,'source_asset_sha256':source_sha,
                'markdown':text,'choices':transcription['choices'],'blocks':blocks,'coverage':coverage,'source_errors':errors,'visual_flags':flags}
            part['fragments'].append(fragment);part['choices'].extend(fragment['choices']);row['formula_candidates'].extend(processed)
            row['issues'].extend({'role':role,'page_number':pn,'code':flag} for flag in set(flags))
        part['markdown']='\n\n'.join(f['markdown'] for f in part['fragments']);row['parts'][role]=part
    row['transcript_status']='SOURCE_REVIEW_REQUIRED' if row['issues'] else 'TEXT_AND_LATEX_DRAFT'
    import psutil
    row['runtime']={'seconds':round(time.perf_counter()-start,3),'model_calls':reader.calls-before[0],
        'secondary_model_calls':secondary.calls-before[1],'ocr_cache_hits':reader.hits-before[2]+secondary.hits-before[3],
        'rss_bytes':psutil.Process().memory_info().rss,'cloud_calls':0}
    return row


def worker(items,documents,output,runtime,katex,identity,index,options=None):
    import pdfplumber,psutil
    configure_storage(Path(runtime));os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
    if os.name=='nt':psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    options=options or {};output=Path(output)
    local=output/'workers'/options.get('chunk_id',str(os.getpid()));local.mkdir(parents=True,exist_ok=True)
    if options.get('native_only'):
        class DeferredReader:
            calls=hits=reused=0
            deferred=True
        reader=DeferredReader();secondary=DeferredReader()
    else:
        reader=CachedReader(runtime,local,'PP-FormulaNet_plus-M',index,options.get('cache_mode','local'))
        secondary=CachedReader(runtime,local,'PP-FormulaNet_plus-S',index,options.get('cache_mode','local'))
    syntax=Syntax(katex);completed=0;resumed=0;peak_pages=0
    try:
        for digest in sorted({q['source']['sha256'] for q in items}):
            path=Path(documents[digest])
            if file_hash(path)!=digest:raise ValueError('SOURCE_HASH_CHANGED')
            with pdfplumber.open(path) as pdf:
                pages=BoundedPages(pdf,options.get('max_page_cache',8))
                for q in sorted((q for q in items if q['source']['sha256']==digest),key=lambda q:min(
                    (s['page_number'] for role in ['question','solution','answer'] for s in q[role]['source_spans']),default=0)):
                    target=output/'records'/('q-'+content_hash(q['question_id'])[:24]+'.json')
                    write_json(local/'current.json',{'at':now(),'number':q['collection_number'],'question_id':q['question_id'],'stage':'LAYOUT_TRANSCRIPTION'})
                    expected=content_hash({'source_record':q,'pipeline':identity})
                    if valid_checkpoint(output,q,identity):
                        completed+=1;resumed+=1;continue
                    try:row=process(q,pdf,pages,output,reader,secondary,syntax,identity)
                    except Exception as e:
                        import traceback
                        write_json(output/'failures'/target.name,{'question_id':q['question_id'],'number':q['collection_number'],
                            'error':type(e).__name__+': '+str(e),'traceback':traceback.format_exc(),'pipeline_identity':identity})
                        print('[v2-failed]',q['collection_number'],str(e),flush=True);continue
                    save_checkpoint(output,row);completed+=1;peak_pages=max(peak_pages,pages.peak)
                    write_json(local/'progress.json',{'at':now(),'completed':completed,'total':len(items),
                        'number':q['collection_number'],'ocr_calls':reader.calls+secondary.calls,
                        'reused_v1_cache':reader.reused+secondary.reused})
                    print('[v2]',q['collection_number'],'tables',len(row['tables']),'formulas',len(row['formula_candidates']),flush=True)
            if file_hash(path)!=digest:raise ValueError('SOURCE_MODIFIED_DURING_RUN')
    finally:syntax.close()
    return {'completed':completed,'resumed':resumed,'ocr_calls':reader.calls+secondary.calls,
            'ocr_cache_hits':reader.hits+secondary.hits,'reused_v1_cache':reader.reused+secondary.reused,
            'peak_cached_pages':peak_pages,'cache_mode':options.get('cache_mode','local')}
