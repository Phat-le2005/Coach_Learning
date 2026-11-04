"""Local table reader with per-question checkpoints, keyed by stable question ID."""
from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path

from PIL import Image,ImageOps
from jsonschema import Draft202012Validator

from .gemini_client import content_hash
from .layout_refinement import regions,evaluate
from .safe_math import UnsupportedMath
from .sign_table import structure as sign_structure
from .variation_table import structure as variation_structure
from .storage import file_hash,read_json,write_json
from .table_glyphs import BoundaryGlyphs


class AutoTables:
    def __init__(self,ocr,output,version,event=lambda *args:None):
        self.ocr,self.output,self.version,self.event=ocr,Path(output),version,event
        self.cell_cache=ocr.output/'table-cells'
        self.cache_hits=0
        try:
            self.boundaries=BoundaryGlyphs()
            self.labels=BoundaryGlyphs(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',axis=True)
            self.fonts=self.boundaries.fonts
        except UnsupportedMath:
            self.boundaries,self.labels,self.fonts=None,None,[]
        self.validator=Draft202012Validator(read_json(Path(__file__).parents[1]/'schemas/math-table-candidate.v1.schema.json'))

    def read(self,image):
        im=image.convert('RGB')
        if im.height<64:im=im.resize((im.width*2,im.height*2),Image.Resampling.LANCZOS)
        im=ImageOps.expand(im,12,fill='white');buf=io.BytesIO();im.save(buf,format='PNG')
        weights=self.ocr.weights(['PP-FormulaNet_plus-M'])
        key=content_hash({'image':sha256(buf.getvalue()).hexdigest(),'weights':weights,
                          'packages':self.ocr.packages,'adapter':'auto-table-cell/v1'})
        path=self.cell_cache/f'{key}.json';image_path=path.with_suffix('.png')
        if weights and not path.exists():
            # Migrate only raw matching OCR, not any old table interpretation.
            import shutil
            for previous in self.ocr.output.parent.glob('versions/*/tables/cells/'+key+'.json'):
                old=read_json(previous)
                if old.get('weights')==weights and old.get('packages')==self.ocr.packages and old.get('image_sha256')==sha256(buf.getvalue()).hexdigest():
                    path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(previous,path)
                    if previous.with_suffix('.png').exists():shutil.copy2(previous.with_suffix('.png'),image_path)
                    break
        if weights and path.exists():
            self.ocr.cache_hits+=1
            return read_json(path)['latex']
        model=self.ocr.model('PP-FormulaNet_plus-M')
        # Setup may download weights; include their final identity in the cache key.
        if weights is None:
            return self.read(image)
        path.parent.mkdir(parents=True,exist_ok=True);image_path.write_bytes(buf.getvalue())
        raw=list(model.predict(str(image_path),batch_size=1))[0].json;self.ocr.calls+=1
        latex=raw.get('res',raw).get('rec_formula','')
        write_json(path,{'latex':latex,'image_sha256':file_hash(image_path),'weights':weights,
                         'packages':self.ocr.packages,'status':'OCR_CANDIDATE_NOT_VERIFIED'})
        return latex

    def question(self,source,pages,audit,document):
        selected=regions(source,pages)
        if not selected:return []
        question_key=sha256(source['question_id'].encode()).hexdigest()[:20]
        target=self.output/'questions'/f'{question_key}.json'
        identity={'source_sha256':source['source_sha256'],'question':source,'audit':audit,'regions':selected,
                  'version':self.version,'models':self.ocr.weights(['PP-FormulaNet_plus-M']),
                  'packages':self.ocr.packages,'fonts':self.fonts}
        key=content_hash(identity)
        if target.exists() and read_json(target).get('key')==key:
            records=read_json(target)['records']
            if all((self.output/r['asset_path']).exists() and file_hash(self.output/r['asset_path'])==r['crop_sha256'] for r in records):
                self.cache_hits+=1
                return records
        records=[]
        for index,region in enumerate(selected):
            self.event('table',source['question_id'])
            asset=self.output/'assets'/f'{question_key}-{index}.png';asset.parent.mkdir(parents=True,exist_ok=True)
            document.pages[region['page_number']-1].crop(tuple(region['bbox'])).to_image(resolution=240).save(asset)
            record={'question_id':source['question_id'],'source_number':source['source_number'],
                    'source_sha256':source['source_sha256'],**region,'asset_path':asset.relative_to(self.output).as_posix(),
                    'crop_sha256':file_hash(asset),'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False}
            try:
                with Image.open(asset) as im:
                    try:table=sign_structure(im,self.read)
                    except UnsupportedMath:
                        table=variation_structure(im,self.read,boundary_reader=self.boundaries.read if self.boundaries else None,
                                                  label_reader=self.labels.read if self.labels else None)
                self.validator.validate(table)
                record.update(status='STRUCTURED_CANDIDATE',table=table,formula_checks=evaluate(table,audit))
            except UnsupportedMath as error:
                record.update(status='NEEDS_LAYOUT_REVIEW',reason=str(error))
            records.append(record)
        # Recompute identity if the first OCR call bootstrapped missing weights.
        identity['models']=self.ocr.weights(['PP-FormulaNet_plus-M'])
        write_json(target,{'key':content_hash(identity),'records':records})
        return records
