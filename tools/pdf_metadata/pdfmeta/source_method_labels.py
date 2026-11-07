"""Document-scoped labels from printed headings, independent of subject rules."""
from copy import deepcopy
from hashlib import sha256
import re
import unicodedata


VERSION = 'document-source-labels/v1'
LEVELS = ['chapter', 'lesson', 'exercise_type']
PREFIX = re.compile(r'^(CHƯƠNG|CHUYÊN\s+ĐỀ|BÀI|CHỦ\s+ĐỀ|DẠNG)(?=\s|\d|[IVX]|[.:–-]|$)\s*'
                    r'(\d+(?:[,.-]\d+)*|[IVX]+(?=\s|[.:–-]|$))?\s*[.:–-]?\s*(.*)$', re.I)
QUESTION = re.compile(r'^(Câu|Ví\s+dụ|Bài|Question|Example)\s*(\d+(?:\.\d+)*)(?=[\s.:)]|$)', re.I)
SECTION = re.compile(r'^(?:PHẦN\s+(?:\d+|[IVX]+)[.:]?\s*|[IVX]+[.]\s+|TRẮC NGHIỆM\b|TỰ LUẬN\b|ÔN TẬP\b|BÀI\s+TẬP\b)',re.I)


def fold(text):
    return re.sub(r'\s+', ' ', ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                                     if not unicodedata.combining(c)).replace('đ','d')).strip()


def clean(text):
    return re.sub(r'^[#>*_\s\uE000-\uF8FF]+','',text).strip().strip('*_').strip()


def question_key(text):
    match = QUESTION.match(clean(text))
    if not match:return None
    role = fold(match[1])
    role = {'question':'cau','example':'vi du'}.get(role,role)
    number = '.'.join(str(int(n)) for n in match[2].split('.'))
    return role,number


def read_heading(lines, index):
    """Only explicit structural prefixes or uppercase type titles create labels."""
    text = clean(lines[index])
    if re.match(r'^BÀI\s+TẬP\b',text,re.I):return None
    match = PREFIX.match(text)
    if match:
        prefix,number,title = match.groups()
        role = ('chapter' if fold(prefix) in {'chuong','chuyen de'} else
                'exercise_type' if fold(prefix)=='dang' else 'lesson')
        if not number and ':' not in text and not text.isupper():return None
        if fold(prefix)=='bai' and number and title:
            if not title.isupper() or re.search(r'[$=]|\\(?:frac|int|sqrt)\b',title):return None
    elif text.isupper() and len(text)>=20 and re.match(r'^(?:TÌM|TÍNH|ỨNG DỤNG)\s',text):
        role,number,title = 'exercise_type',None,text
    else:return None
    end = index+1
    # A title on the next uppercase line is still the same printed heading.
    while end<len(lines):
        following = clean(lines[end])
        if (not following.isupper() or len(following)<3 or PREFIX.match(following)
                or QUESTION.match(following) or SECTION.match(following)
                or re.match(r'^(?:CHÚ Ý|LƯU Ý|PHƯƠNG PHÁP|LỜI GIẢI)\b',following)
                or re.search(r'[=∩∪<>{}]|\bP\s*\(|\\(?:frac|int|sqrt)\b',following)):
            break
        if not title and role=='chapter':
            standalone = re.match(r'^([IVX]+|\d+)\s+(.+)$',following)
            if standalone:number,title = standalone.groups()
            else:title = following
        else:title = (title+' '+following).strip()
        text += ' '+following
        end += 1
    if not title:return None
    return {'role':role,'name':title.strip(),'source_number':number,'source_label':text,'end':end}


class Registry:
    def __init__(self, source_sha, taxonomy, chapter_match):
        self.source_sha,self.taxonomy,self.chapter_match = source_sha,taxonomy,chapter_match
        self.labels = {}

    def label(self, found, active, evidence):
        role = found['role']
        parent = None
        if role=='exercise_type':parent = active.get('lesson') or active.get('chapter')
        elif role=='lesson':parent = active.get('chapter')
        parent_code = parent['code'] if parent else None
        reference = (evidence.get('source_reference') or '') if role!='chapter' else ''
        identity = '|'.join([self.source_sha,reference,role,parent_code or '',found.get('source_number') or '',fold(found['name'])])
        code = 'DOC_'+role.upper()+'_'+sha256(identity.encode()).hexdigest()[:16]
        canonical = None
        if role=='chapter':
            canonical = self.chapter_match(found['name'])
            if canonical not in self.taxonomy['chapters']:canonical = None
        else:
            table = self.taxonomy['topics' if role=='lesson' else 'problem_types']
            parent_key = 'chapter_code' if role=='lesson' else 'topic_code'
            target_parent = parent.get('canonical_code') if parent else None
            matches = [r['code'] for r in table.values() if fold(r['name'])==fold(found['name'])
                       and target_parent and r[parent_key]==target_parent]
            if len(matches)==1:canonical = matches[0]
        result = {'code':code,'name':found['name'],'canonical_code':canonical,
                  'source_number':found.get('source_number'),'source_label':found['source_label'],
                  'parent_code':parent_code,'basis':'PRINTED_DOCUMENT_HEADING','evidence':evidence}
        self.labels[code] = dict(result,level=role)
        return result

    def apply(self, found, active, evidence):
        role = found['role']
        label = self.label(found,active,evidence)
        if role=='chapter' and active.get(role,{}).get('code')!=label['code']:
            active.clear()
        elif role=='lesson' and active.get(role,{}).get('code')!=label['code']:
            active.pop('exercise_type',None)
        active[role] = label


def document_contexts(rows, pages, taxonomy, chapter_match):
    """Find per-question context before its printed question label, not after it."""
    registry = Registry(rows[0]['source']['sha256'],taxonomy,chapter_match)
    active,previous,occurrences = {},None,{}
    native_chapter,reference = None,None
    page_references = {}
    def consume(text, pn, basis, stop_at_question=False, skip_header=False):
        lines = [s for s in text.splitlines() if s.strip()]
        index = 0
        while index<len(lines):
            if index==0 and skip_header:
                index += 1
                continue
            found = read_heading(lines,index)
            if found:
                registry.apply(found,active,{'page_number':pn,'basis':basis,'text':found['source_label'],
                                            'source_reference':reference})
                index = found['end'];continue
            key = question_key(lines[index])
            if key:
                if stop_at_question:break
                occurrences.setdefault((pn,key),[]).append(deepcopy(active))
            elif SECTION.match(clean(lines[index])) and clean(lines[index]).isupper():
                active.pop('lesson',None);active.pop('exercise_type',None)
            index += 1
    for page in sorted(pages,key=lambda p:p['page_number']):
        pn = page['page_number']
        if previous is not None and pn!=previous+1:
            active,native_chapter,reference = {},None,None
        previous = pn
        combined = page.get('native_text_from_this_pdf','')+'\n'+page.get('markdown','')
        lines = [clean(s) for s in combined.splitlines() if s.strip()]
        contents = any(fold(s) in {'muc luc','table of contents','contents'} for s in lines[:12])
        entries = sum(bool(PREFIX.match(s) or re.match(r'^\d+[.]\s+',s) or re.search(r'(?:\.\s*){6,}',s)) for s in lines)
        if contents and entries>=2:
            active,native_chapter,reference = {},None,None
            continue
        native = page.get('native_text_from_this_pdf','')
        first = next((s.strip() for s in native.splitlines() if s.strip()),'')
        recognized = chapter_match(first)
        prefix = PREFIX.match(clean(first))
        native_header = (recognized and not fold(first).startswith(('tim ','tinh '))
                         and (not prefix or fold(prefix[1]) in {'chuong','chuyen de'}))
        if native_header and recognized!=native_chapter:
            if not prefix and active.get('chapter',{}).get('canonical_code')!=recognized:
                name = re.sub(r'\s+Câu hỏi kèm lời giải.*$','',first,flags=re.I).strip()
                registry.apply({'role':'chapter','name':name,'source_number':None,'source_label':first},active,
                               {'page_number':pn,'basis':'NATIVE_RUNNING_CHAPTER_HEADER','text':first})
            native_chapter = recognized
        refs = set(re.findall(r'\bTL\s+([0-9a-f]{8,64})\b',native,re.I))
        if refs and (len(refs)>1 or reference not in refs):
            active.pop('lesson',None);active.pop('exercise_type',None)
        if len(refs)==1:reference = next(iter(refs))
        elif len(refs)>1:reference = None
        page_references[pn] = reference
        consume(page.get('native_text_from_this_pdf',''),pn,'NATIVE_TEXT_HEADING',True,bool(native_header and not prefix))
        consume(page.get('markdown',''),pn,'OCR_PRINTED_HEADING')
        if len(refs)>1:
            active.pop('lesson',None);active.pop('exercise_type',None)
    results = {}
    for row in rows:
        spans = row.get('question',{}).get('source_spans',[])
        pn = min((s['page_number'] for s in spans),default=None)
        key = question_key(row.get('question',{}).get('markdown','').split('\n',1)[0])
        queue = occurrences.get((pn,key),[])
        context = deepcopy(queue.pop(0)) if queue else {}
        # Structured native heading provenance is more precise than OCR text.
        explicit = row.get('topic_context',{})
        for name in ['chapter','lesson','topic','exercise_type']:
            source = explicit.get(name)
            if not source:continue
            label = source.get('label') or source.get('source_label') or source.get('title','')
            found = read_heading([label],0)
            if not found and name in {'lesson','topic','exercise_type'} and source.get('title'):
                found = {'role':'lesson' if name=='topic' else name,'name':source['title'],
                         'source_number':source.get('number'),'source_label':label}
            if found:
                registry.apply(found,context,{'page_number':source.get('page_number',pn),
                    'bbox':source.get('bbox'),'block_ids':source.get('block_ids',[]),
                    'basis':'EXPORTED_SOURCE_TOPIC_CONTEXT','text':label,
                    'source_reference':page_references.get(pn)})
        results[row['question_id']] = context
    return results, {'schema_version':VERSION,'source_sha256':registry.source_sha,
                     'scope':'THIS_DOCUMENT_ONLY','labels':list(registry.labels.values()),
                     'canonical_mapping':'EXACT_NAMES_OR_RECOGNIZED_CHAPTER_ONLY'}


def apply_document_labels(method, printed):
    if not printed:return method
    result = deepcopy(method)
    result['document_labels'] = printed
    chapter = printed.get('chapter')
    if chapter and chapter.get('canonical_code')!=(result.get('chapter') or {}).get('code'):
        result['lesson'],result['exercise_type'],result['candidates'] = None,None,[]
    lesson = printed.get('lesson')
    if lesson and lesson.get('canonical_code')!=(result.get('lesson') or {}).get('code'):
        if result['candidates']:result['inference_candidates'] = deepcopy(result['candidates'])
        result['exercise_type'],result['candidates'] = None,[]
    for role in LEVELS:
        if role in printed:result[role] = printed[role]
    result['label_path'] = [result[r]['name'] for r in LEVELS if result[r]]
    inferred = (bool(result.get('inference_candidates')) or
                any(result[r] and result[r].get('basis')!='PRINTED_DOCUMENT_HEADING' for r in ['lesson','exercise_type']))
    result['classification_method'] = 'DOCUMENT_HEADINGS_WITH_RULE_CANDIDATES' if inferred else 'PRINTED_DOCUMENT_HEADINGS'
    result['status'] = 'MIXED_SOURCE_AND_RULE_CANDIDATES' if inferred else 'SOURCE_LABELS_NEED_REVIEW'
    result['flags'] = [f for f in result['flags'] if not (
        f=='CHAPTER_EVIDENCE_MISSING' and result['chapter'] or
        f=='NO_FINER_LABEL_EVIDENCE' and (result['lesson'] or result['exercise_type']))]
    return result


def heading_rows(blocks):
    """Join PDF text runs on the same baseline for heading recognition only."""
    groups=[]
    for block in sorted(blocks,key=lambda b:((b['bbox'][1]+b['bbox'][3])/2,b['bbox'][0])):
        cy=(block['bbox'][1]+block['bbox'][3])/2
        group=next((g for g in reversed(groups[-3:]) if abs(g[0]-cy)<=4),None)
        if group:group[1].append(block)
        else:groups.append([cy,[block]])
    rows=[]
    for _,parts in groups:
        parts.sort(key=lambda b:b['bbox'][0])
        text='';previous=None
        for b in parts:
            gap=b['bbox'][0]-previous['bbox'][2] if previous else 0
            join=' ' if previous and gap>1.8 and not b['text_raw'].startswith(('.',',',':',';')) else ''
            text+=join+b['text_raw'];previous=b
        rows.append({'text_raw':text,'block_id':parts[0]['block_id'],
                     'block_ids':[b['block_id'] for b in parts],
                     'bbox':[min(b['bbox'][0] for b in parts),min(b['bbox'][1] for b in parts),
                             max(b['bbox'][2] for b in parts),max(b['bbox'][3] for b in parts)]})
    return sorted(rows,key=lambda b:(b['bbox'][1],b['bbox'][0]))


def native_document_contexts(rows, pdf, taxonomy, chapter_match):
    """Use source glyph positions when a verified text PDF is available.

    Heading contexts stop at each question's source coordinates. OCR title
    mistakes and old exported context inheritance cannot override this path.
    """
    import pypdfium2 as pdfium
    from .pdf_text_layout import inspect_document
    registry = Registry(rows[0]['source']['sha256'],taxonomy,chapter_match)
    with pdfium.PdfDocument(pdf) as doc:profiles = inspect_document(doc)
    from .native import margin_key
    key=lambda text:re.sub(r'\s+','',margin_key(text)).casefold()
    margins={key(b['text_raw']) for p in profiles.values() for b in p['blocks'] if b.get('is_margin')}
    wanted = {}
    for row in rows:
        spans = row.get('question',{}).get('source_spans',[])
        pn = min((s['page_number'] for s in spans),default=None)
        if pn is None:continue
        text_lines = [s for s in row.get('question',{}).get('markdown','').splitlines() if s.strip()]
        h = read_heading(text_lines,0) if text_lines else None
        heading_record = bool(h and h['end']==len(text_lines))
        boxes = [s['bbox'] for s in spans if s['page_number']==pn]
        anchor = max(b[3] for b in boxes) if heading_record else min(b[1] for b in boxes)
        wanted.setdefault(pn,[]).append((anchor,row['question_id'],heading_record))
    active,results,record_kinds = {},{},{}
    for pn,page in profiles.items():
        blocks = heading_rows([b for b in page['blocks'] if not b.get('is_margin')])
        blocks = [b for b in blocks if key(b['text_raw']) not in margins]
        lines = [b['text_raw'] for b in blocks]
        events = []
        index = 0
        while index<len(lines):
            found = read_heading(lines,index)
            if found:
                used = blocks[index:found['end']]
                box = [min(b['bbox'][0] for b in used),min(b['bbox'][1] for b in used),
                       max(b['bbox'][2] for b in used),max(b['bbox'][3] for b in used)]
                events.append((box[1],found,{'page_number':pn,'bbox':box,'block_ids':[k for b in used for k in b['block_ids']],
                    'basis':'VISIBLE_NATIVE_PDF_HEADING','text':found['source_label']}))
                index = found['end'];continue
            if (SECTION.match(clean(lines[index])) and (clean(lines[index]).isupper()
                    or re.match(r'^PHẦN\s+(?:\d+|[IVX]+)[.:]?',clean(lines[index]),re.I))):
                events.append((blocks[index]['bbox'][1],None,{}))
            index += 1
        cursor = 0
        def apply_event(event):
            _,found,evidence = event
            if found:
                # These are in-body titles, after running margins were removed.
                # Repeated lesson covers begin a fresh part even if names match.
                if found['role']=='chapter' and evidence['bbox'][1]>35:
                    active.pop('lesson',None);active.pop('exercise_type',None)
                elif found['role']=='lesson' and evidence['bbox'][1]>35:
                    active.pop('exercise_type',None)
                registry.apply(found,active,evidence)
            else:
                active.pop('exercise_type',None)
                number=(active.get('lesson') or {}).get('source_number') or ''
                if not re.search(r'[,\-]',number):active.pop('lesson',None)
        for anchor,qid,is_heading in sorted(wanted.get(pn,[])):
            while cursor<len(events) and events[cursor][0]<=anchor+3:
                apply_event(events[cursor]);cursor += 1
            results[qid] = deepcopy(active)
            if is_heading:record_kinds[qid] = 'SOURCE_HEADING_NOT_EXERCISE'
        while cursor<len(events):
            apply_event(events[cursor]);cursor += 1
    catalog={'schema_version':VERSION,'source_sha256':registry.source_sha,'scope':'THIS_DOCUMENT_ONLY',
             'labels':list(registry.labels.values()),'acquisition':'VERIFIED_NATIVE_PDF_GLYPH_POSITIONS',
             'canonical_mapping':'EXACT_NAMES_OR_RECOGNIZED_CHAPTER_ONLY'}
    return results,catalog,record_kinds
