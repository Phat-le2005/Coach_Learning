"""Visible native text supplies margin geometry and printed topic provenance only.

It never replaces the image-based transcription of mathematics.
"""
from copy import deepcopy
import re

from .native import mark_margins
from .paired.fast_native import extract_page


VERSION = 'visible-pdf-text-layout/v1'
HEADING = re.compile(r'^(Dạng|Chủ\s+đề|Chương|Bài)\s*(\d+(?:[,.-]\d+)*|[IVX]+)?\s*[.:–-]\s*(.*)$', re.I)
QUESTION = re.compile(r'^(?:Câu|Ví\s+dụ|Bài)\s*(\d+)\s*[.:)]', re.I)


def heading(text):
    text = re.sub(r'^[#>*\s\uE000-\uF8FF]+', '', text).strip().strip('*_')
    match = HEADING.match(text)
    if not match or not match[3].strip():
        chapter = re.fullmatch(r'CHƯƠNG\s+(\d+|[IVX]+)', text, re.I)
        section = re.fullmatch(r'(?:[IVX]+[.]|PHẦN\s+(?:\d+|[IVX]+)[.:]?)\s+(.+)', text)
        if chapter:
            return {'kind': 'chapter', 'label': text, 'number': chapter[1], 'title': text}
        if section and section[1].isupper():
            return {'kind': 'section', 'label': text, 'number': None, 'title': section[1]}
        if text.isupper() and len(text) >= 20 and re.match(r'^(?:TÌM|TÍNH|ỨNG DỤNG)\s', text):
            return {'kind': 'exercise_type', 'label': text, 'number': None, 'title': text}
        if text.isupper() and re.match(r'^(?:TRẮC NGHIỆM|TỰ LUẬN)\b', text):
            return {'kind': 'section', 'label': text, 'number': None, 'title': text}
        return None
    kind = match[1].casefold()
    # A numbered "Bài 1: ..." is also an exercise; only unnumbered lesson
    # titles or uppercase lesson titles are unambiguous here.
    if kind == 'bài' and match[2] and not match[3].isupper():
        return None
    return {'kind': 'exercise_type' if kind == 'dạng' else 'topic' if kind.startswith('chủ') else 'chapter',
            'label': text, 'number': match[2], 'title': match[3].strip()}


def inspect_document(doc):
    records = []
    for index in range(len(doc)):
        page = doc[index]
        try:
            records.append(extract_page(page, index + 1, '', 72))
        finally:
            page.close()
    mark_margins(records)
    context = {}
    for page in records:
        page['question_contexts'] = []
        page['printed_headings'] = []
        for index, block in enumerate(page['blocks']):
            if block.get('is_margin'):
                continue
            found = heading(block['text_raw'])
            if found:
                # Titles can occupy multiple printed lines. Join only adjacent
                # uppercase continuation text; never consume a question/body line.
                last = block
                block_ids = [block['block_id']]
                bbox = list(block['bbox'])
                for following in page['blocks'][index+1:]:
                    text = following['text_raw'].strip()
                    if (following.get('is_margin') or heading(text) or QUESTION.match(text)
                            or not text.isupper() or len(text) < 12
                            or re.search(r'[=<>∩∪]', text)
                            or not 0 <= following['bbox'][1]-last['bbox'][3] <= 14):
                        break
                    found['label'] += ' ' + text
                    found['title'] = text if found['title'] == block['text_raw'] and found['kind'] == 'chapter' else found['title'] + ' ' + text
                    bbox = [min(bbox[0],following['bbox'][0]), bbox[1], max(bbox[2],following['bbox'][2]), following['bbox'][3]]
                    block_ids.append(following['block_id'])
                    last = following
                found.update(page_number=page['page_number'], bbox=bbox, block_ids=block_ids,
                             method='PRINTED_NATIVE_HEADING', source_verified=False)
                if found['kind'] == 'chapter':
                    context = {'chapter': found}
                elif found['kind'] == 'topic':
                    context.pop('exercise_type', None)
                    context['topic'] = found
                elif found['kind'] == 'section':
                    context.pop('exercise_type', None)
                    context.pop('topic', None)
                    context['section'] = found
                else:
                    context['exercise_type'] = found
                page['printed_headings'].append(found)
            match = QUESTION.match(block['text_raw'])
            if match:
                page['question_contexts'].append({'source_number': int(match[1]), 'bbox': block['bbox'],
                                                  'context': deepcopy(context)})
        page['ending_context'] = deepcopy(context)
    return {p['page_number']: p for p in records}


def content_regions(boxes, profile):
    """Intersect OCR regions with content bounds before layout/model acquisition."""
    if not profile or not any(b.get('is_margin') for b in profile['blocks']):
        return boxes
    _, top, _, bottom = profile['content_bounds']
    clipped = [[box[0], max(box[1], top), box[2], min(box[3], bottom)] for box in boxes]
    return [box for box in clipped if box[2] > box[0] and box[3] > box[1]]


def heading_only_text(profile):
    blocks = [b for b in profile['blocks'] if not b.get('is_margin')]
    owned = {key for h in profile['printed_headings'] for key in h['block_ids']}
    if blocks and all(b['block_id'] in owned for b in blocks):
        return '\n'.join(b['text_raw'] for b in blocks)
    return None


def report(profiles):
    return {'version': VERSION, 'pages': [{
        'page_number': p['page_number'], 'content_bounds': p['content_bounds'],
        'excluded_margins': [{'text': b['text_raw'], 'bbox': b['bbox'], 'role': b['margin_role']}
                             for b in p['blocks'] if b.get('is_margin')],
        'printed_headings': p['printed_headings'], 'question_contexts': p['question_contexts'],
    } for p in profiles.values()]}
