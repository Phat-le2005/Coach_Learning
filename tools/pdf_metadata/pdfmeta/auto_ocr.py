"""Lazy local OCR adapters shared by the one-PDF workflow; no cloud provider."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from PIL import Image

from .storage import file_hash,inference_versions,read_json,write_json


VERSION='auto-local-ocr/v1'


def apply_section_hints(page):
    from .section_markers import hint
    effective=deepcopy(page)
    for block in effective['blocks']:
        block.pop('section_marker_candidate',None)
        marker=hint(block['text_raw'])
        if marker:block['section_marker_candidate']=marker
    return effective


def needs_text_ocr(page):
    content=[b for b in page['blocks'] if not b.get('is_margin')]
    count=sum(len(b['text_raw'].strip()) for b in content)
    area=page['width']*page['height']
    image_area=sum((i['bbox'][2]-i['bbox'][0])*(i['bbox'][3]-i['bbox'][1]) for i in page.get('images',[]))
    # Source books can put several native captions above image-only exercises.
    # Those captions must not prevent OCR of the actual question and solution.
    return count<60 or (image_area>.2*area and count<400)


class LocalOCR:
    def __init__(self,runtime,output,event=lambda *args:None):
        self.runtime,self.output,self.event=Path(runtime),Path(output),event
        self.models={};self.calls=0;self.cache_hits=0
        self._weight_cache={}
        self.packages=inference_versions()

    def model(self,name):
        if name not in self.models:
            self.event('model',name)
            from paddleocr import FormulaRecognition,LayoutDetection,PaddleOCR
            kwargs=dict(device='cpu',cpu_threads=3,enable_mkldnn=False)
            root=self.runtime/'paddlex/official_models'
            if name=='general-text':
                self.models[name]=PaddleOCR(text_detection_model_name='PP-OCRv5_mobile_det',
                    text_recognition_model_name='latin_PP-OCRv5_mobile_rec',use_doc_orientation_classify=False,
                    use_doc_unwarping=False,use_textline_orientation=False,**kwargs)
            else:
                cls=LayoutDetection if name=='PP-DocLayoutV3' else FormulaRecognition
                self.models[name]=cls(model_name=name,**({'model_dir':str(root/name)} if (root/name/'inference.pdiparams').exists() else {}),**kwargs)
        return self.models[name]

    def weights(self,names):
        root=self.runtime/'paddlex/official_models'
        result={}
        for name in names:
            path=root/name/'inference.pdiparams'
            if not path.exists():
                return None
            stat=path.stat();identity=(stat.st_size,stat.st_mtime_ns)
            old=self._weight_cache.get(str(path))
            if not old or old[0]!=identity:
                self._weight_cache[str(path)]=(identity,file_hash(path))
            result[name+'/inference.pdiparams']=self._weight_cache[str(path)][1]
        return result

    def text_page(self,page,image_path):
        names=['PP-OCRv5_mobile_det','latin_PP-OCRv5_mobile_rec']
        cache=self.output/'text'/f"page-{page['page_number']:03}.json"
        identity={'source_sha256':page['source_sha256'],'image_sha256':file_hash(image_path),
                  'packages':self.packages,'adapter':VERSION,'models':self.weights(names)}
        if cache.exists() and identity['models'] and read_json(cache).get('identity')==identity:
            self.cache_hits+=1
            return apply_section_hints(read_json(cache)['page'])
        model=self.model('general-text');identity['models']=self.weights(names)
        self.event('text_ocr',page['page_number'])
        result=list(model.predict(str(image_path)))[0].json
        raw=result.get('res',result);self.calls+=1
        with Image.open(image_path) as image:
            sx,sy=page['width']/image.width,page['height']/image.height
        texts=raw.get('rec_texts',[]);polys=raw.get('rec_polys',raw.get('dt_polys',[]));scores=raw.get('rec_scores',[])
        blocks=[]
        for index,(text,poly) in enumerate(zip(texts,polys)):
            if not str(text).strip():continue
            xx=[float(p[0])*sx for p in poly];yy=[float(p[1])*sy for p in poly]
            bbox=[max(0,min(xx)),max(0,min(yy)),min(page['width'],max(xx)),min(page['height'],max(yy))]
            if bbox[2]<=bbox[0] or bbox[3]<=bbox[1]:continue
            blocks.append({'block_id':f"p{page['page_number']:03}-ocr-{index:04}",'block_type':'ocr_line',
                'text_raw':str(text),'bbox':bbox,'glyphs':[],'reading_order':index,
                'ocr_score_uncalibrated':float(scores[index]) if index<len(scores) else None,
                'review_flags':['OCR_TEXT_NOT_SOURCE_VERIFIED'],'is_margin':False})
        blocks.sort(key=lambda b:(round(b['bbox'][1]/3),b['bbox'][0]))
        effective={**deepcopy(page),'blocks':blocks,'parser_id':'PP-OCRv5-Latin','extraction_status':'OCR_CANDIDATE',
                   'content_bounds':[0,0,page['width'],page['height']]}
        raw=json.loads(json.dumps(raw,default=lambda value:value.tolist() if hasattr(value,'tolist') else str(value)))
        write_json(cache,{'identity':identity,'page':effective,'raw_result':raw})
        return apply_section_hints(effective)

    def formula_page(self,page,image_path,pdf_page):
        names=['PP-DocLayoutV3','PP-FormulaNet_plus-S']
        target=self.output/'formula'/f"page-{page['page_number']:03}.blocks.json"
        identity={'source_sha256':page['source_sha256'],'image_sha256':file_hash(image_path),
                  'packages':self.packages,'adapter':VERSION,'models':self.weights(names),'dpi':240,'threshold':.4}
        if target.exists() and identity['models'] and read_json(target).get('identity')==identity:
            self.cache_hits+=1
            return read_json(target)
        detector=self.model(names[0]);recognizer=self.model(names[1]);identity['models']=self.weights(names)
        self.event('formula_ocr',page['page_number'])
        with Image.open(image_path) as im:w,h=im.size
        raw=list(detector.predict(str(image_path),batch_size=1,threshold=.4))[0].json
        raw=raw.get('res',raw);blocks=[];self.calls+=1
        for index,box in enumerate(raw.get('boxes',[])):
            if box['label'] not in {'formula','inline_formula','display_formula'}:continue
            x0,y0,x1,y1=box['coordinate']
            bbox=[max(0,x0*page['width']/w-2),max(0,y0*page['height']/h-2),
                  min(page['width'],x1*page['width']/w+2),min(page['height'],y1*page['height']/h+2)]
            if bbox[2]-bbox[0]<2 or bbox[3]-bbox[1]<2:continue
            crop=target.parent/f"p{page['page_number']:03}-formula-{index:03}.png";crop.parent.mkdir(parents=True,exist_ok=True)
            pdf_page.crop(tuple(bbox)).to_image(resolution=240).save(crop)
            result=list(recognizer.predict(str(crop),batch_size=1))[0].json;self.calls+=1
            blocks.append({'block_id':f"p{page['page_number']:03}-formula-{index:03}",'block_type':box['label'],
                'text_raw':result.get('res',result).get('rec_formula',''),'bbox':bbox,'reading_order':index})
        record={'identity':identity,'page_number':page['page_number'],'source_sha256':page['source_sha256'],
                'parser_id':'PP-FormulaNet_plus-S','blocks':blocks,'status':'INFERRED_NOT_REVIEWED'}
        write_json(target,record)
        return record

    def imported_formulas(self,cache_root,page,image_path):
        """Reuse source-hash-matched old raw checkpoints, never editorial edits."""
        result=[]
        for folder in ['fast-hybrid','formula-fallback']:
            path=cache_root/folder/f"page-{page['page_number']:03}.blocks.json"
            if not path.exists():continue
            raw=read_json(path)
            if raw.get('source_sha256')!=page['source_sha256']:continue
            if folder=='fast-hybrid':
                key=raw.get('cache_key',{})
                if (key.get('image_sha256')!=file_hash(image_path) or key.get('packages')!=self.packages
                        or key.get('model_weights_sha256')!=self.weights(['PP-DocLayoutV3','PP-FormulaNet_plus-S'])):
                    continue
            elif raw.get('model_weights_sha256')!=(self.weights(['PP-FormulaNet_plus-M']) or {}).get('PP-FormulaNet_plus-M/inference.pdiparams'):
                continue
            result.append(raw)
        if result:self.cache_hits+=len(result)
        return result
