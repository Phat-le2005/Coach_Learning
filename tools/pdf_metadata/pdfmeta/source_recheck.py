"""Deterministic source replay before routing; never asks a model to approve."""
from copy import deepcopy
from pathlib import Path
import re

from .storage import file_hash,read_json
from .safe_math import UnsupportedMath
from .source_layout import inspect
from .paired.math_recovery import extract_page
from .paired.transcript_batch import Syntax
from .paired.transcript_regions import assemble
from .paired.transcript_quality import check_source_tokens
from .paired.transcription_v2.engine import BoundedPages
from .paired.transcription_v2.glyphs import canonical_page,glyph_lookup
from .paired.transcription_v2.geometry import render
from .paired.transcription_v2.layout import prepare


def structure_issues(latex,signals):
    guards={'absolute_bars':r'\||\\(?:[lr]?vert|abs)\b','overlines':r'\\(?:bar|overline)\b',
            'lower_glyphs':r'_','top_bars':r'\\(?:sqrt|frac|dfrac|tfrac|overline|bar)\b'}
    return ['SOURCE_STRUCTURE_MISSING_'+key.upper() for key,pattern in guards.items()
            if signals.get(key) and not re.search(pattern,latex)]


class SourceReplay:
    def __init__(self,plan,katex):
        self.documents={d['sha256']:Path(d['path']).resolve() for d in read_json(Path(plan))['documents']}
        self.syntax=Syntax(Path(katex).resolve());self.pdf=None;self.digest=None;self.pages=None;self.verified=set()
        try:
            if self.syntax('x^2')['status']!='PASS':raise ValueError('SOURCE_REPLAY_KATEX_PREFLIGHT_FAILED')
        except BaseException:
            self.syntax.close();raise
    def close(self):
        if self.pdf:self.pdf.close()
        self.syntax.close()
        for digest in self.verified:
            if file_hash(self.documents[digest])!=digest:raise ValueError('SOURCE_CHANGED_DURING_RECHECK')
    def page(self,digest,pn):
        import pdfplumber
        if self.digest!=digest:
            if self.pdf:self.pdf.close()
            path=self.documents[digest]
            if file_hash(path)!=digest:raise ValueError('SOURCE_PDF_HASH_MISMATCH')
            self.pdf=pdfplumber.open(path);self.pages=BoundedPages(self.pdf,8);self.digest=digest;self.verified.add(digest)
        if pn not in self.pages:
            raw=self.pdf.pages[pn-1];page=canonical_page(extract_page(raw,pn,digest))
            page['images']=[{'bbox':[i['x0'],i['top'],i['x1'],i['bottom']]} for i in raw.images]
            self.pages[pn]=page
        return self.pages[pn]
    def __call__(self,original):
        row=deepcopy(original);actions=[];digest=row['source']['sha256']
        for formula in row['formula_candidates']:
            if not formula.get('display_latex'):continue
            page=self.page(digest,formula['page_number']);lookup=glyph_lookup(page)
            gs=[lookup[k] for k in formula['source_glyph_keys']];signals=inspect(page,formula['bbox'])
            before=formula['display_latex'];latex=before
            if signals['absolute_bars'] and structure_issues(latex,{'absolute_bars':signals['absolute_bars']}):
                try:
                    latex,proof=render(gs,page['vectors'])
                    if self.syntax(latex)['status']!='PASS':raise UnsupportedMath('SOURCE_REPLAY_SYNTAX_FAILED')
                    actions.append({'kind':'VECTOR_ABSOLUTE_RECOVERY','formula_id':formula['formula_id'],
                                    'before':before,'after':latex,'source_evidence':proof})
                except (UnsupportedMath,ValueError,TypeError):pass
            reasons=check_source_tokens(''.join(g['text'] for g in gs),latex)+structure_issues(latex,signals)
            if reasons:
                formula['display_latex']=None
                row['issues'].append({'role':formula['role'],'page_number':formula['page_number'],
                                      'code':'SOURCE_REPLAY_FORMULA_REQUIRES_IMAGE'})
                actions.append({'kind':'HELD_FORMULA','formula_id':formula['formula_id'],'reasons':reasons})
            else:formula['display_latex']=latex
        for role,part in row['parts'].items():
            choices=[]
            for index,fragment in enumerate(part['fragments']):
                page=self.page(digest,fragment['page_number']);prefix=f'{role}-{index:02}'
                tables=[t for t in row['tables'] if t['role']==role and t['table_id'].startswith(prefix+'-')]
                span={'bbox':fragment['bbox'],'page_number':fragment['page_number']}
                try:
                    _,_,rows,_,_=prepare(page,span,tables)
                    formulas=[f for f in row['formula_candidates'] if f['role']==role and f['formula_id'].startswith(prefix+'-')]
                    result=assemble(rows,formulas)
                    if result['choices']!=fragment['choices']:
                        actions.append({'kind':'CHOICES_REASSEMBLED_FROM_SOURCE_COORDINATES','role':role,'page':fragment['page_number']})
                    fragment['choices']=result['choices'];choices.extend(result['choices'])
                    for block in fragment['blocks']:
                        if block['kind']=='TRANSCRIBED_TEXT_DRAFT':block['markdown']=result['markdown']
                    fragment['markdown']='\n\n'.join(b['markdown'] for b in fragment['blocks'] if b.get('markdown'))
                    for reason in result.get('choice_issues',[]):
                        row['issues'].append({'role':role,'page_number':fragment['page_number'],'code':reason})
                except (ValueError,KeyError,TypeError,UnsupportedMath) as error:
                    row['issues'].append({'role':role,'page_number':fragment['page_number'],'code':'SOURCE_REPLAY_ASSEMBLY_REQUIRES_IMAGE'})
                    choices.extend(fragment['choices'])
                    actions.append({'kind':'HELD_ASSEMBLY','role':role,'error':type(error).__name__})
            part['choices']=choices;part['markdown']='\n\n'.join(f['markdown'] for f in part['fragments'])
        row['source_recheck']={'status':'REPLAYED_AGAINST_ORIGINAL_PDF','actions':actions,
                               'mathematical_accuracy_established':False,'model_calls':0}
        return row
