"""Same-PDF geometry/prose anchors; never substitute native mathematical text."""
import re

from .pdf_text_layout import QUESTION, heading

VERSION = 'source-crop-boundaries/v1'
END_QUESTION = re.compile(r'^(?:Trả\s*lời|Đáp\s*(?:án|số)|Lời\s*giải|Hướng\s*dẫn|Giải|Solution|Answer)\b', re.I)


def question_bands(profile):
    bands, active = [], None
    for block in (profile or {}).get('blocks', []):
        if block.get('is_margin'):
            continue
        text, box = block['text_raw'].strip(), block['bbox']
        start = QUESTION.match(text)
        if active and (start or END_QUESTION.match(text) or heading(text)):
            bands.append(active)
            active = None
        if start:
            active = list(box)
        elif active:
            active = [min(active[0], box[0]), min(active[1], box[1]),
                      max(active[2], box[2]), max(active[3], box[3])]
    if active:
        bands.append(active)
    return bands


def pixel_bands(profile, origin, image):
    sx, sy = image.width / (origin[2] - origin[0]), image.height / (origin[3] - origin[1])
    return [[(b[0]-origin[0])*sx, (b[1]-origin[1])*sy,
             (b[2]-origin[0])*sx, (b[3]-origin[1])*sy] for b in question_bands(profile)]


def crop_context(profile, box):
    context = {'version': VERSION}
    for band in question_bands(profile):
        overlap = min(box[2], band[2]) - max(box[0], band[0])
        if overlap <= 0:
            continue
        context['question_cut_top'] = context.get('question_cut_top', False) or band[1]+1 < box[1] < band[3]-1
        context['question_cut_bottom'] = context.get('question_cut_bottom', False) or band[1]+1 < box[3] < band[3]-1
    # Only a complete, visible native prose line at the bottom can bound an OCR
    # suffix. Font-encoded formula fragments are never used as a text replacement.
    visible = [b for b in (profile or {}).get('blocks', []) if not b.get('is_margin')
               and b['bbox'][0] >= box[0]-1 and b['bbox'][2] <= box[2]+1
               and b['bbox'][1] >= box[1]-1 and b['bbox'][3] <= box[3]+1]
    if visible:
        last = max(visible, key=lambda b: b['bbox'][3])
        tail = re.search(r'((?:[^\W\d_]{2,}\s+){3,}[^\W\d_]{2,})[.,;:!?]?\s*$', last['text_raw'], re.UNICODE)
        if tail and 0 <= box[3]-last['bbox'][3] <= 8:
            context['tail_anchor'] = ' '.join(tail[1].split()[-6:])
            context['tail_anchor_bbox'] = last['bbox']
    return context


def guard_tail(row, context):
    flags = list(row.get('flags', []))
    if context.get('question_cut_top') or context.get('question_cut_bottom') or context.get('forced_split'):
        flags.append('SOURCE_CROP_CONTINUATION_REVIEW_REQUIRED')
    anchor = context.get('tail_anchor')
    text = row['markdown']
    audit = {'version': VERSION, 'status': 'NO_RELIABLE_PROSE_ANCHOR'}
    if anchor:
        pattern = r'[\s*_~$]+'.join(re.escape(w) for w in anchor.split())
        matches = list(re.finditer(pattern, text, re.I))
        audit.update(source_tail_anchor=anchor, source_tail_bbox=context['tail_anchor_bbox'])
        if not matches:
            audit['status'] = 'ANCHOR_NOT_ALIGNED'
            flags.append('SOURCE_CROP_TAIL_REVIEW_REQUIRED')
        else:
            end = matches[-1].end()
            # A terminal punctuation mark belongs to the visible sentence.
            punctuation = re.match(r'[.,;:!?]*', text[end:])[0]
            end += len(punctuation)
            if text[end:].strip():
                audit.update(status='UNSUPPORTED_CONTINUATION_REMOVED', removed_characters=len(text[end:]))
                text = text[:end].rstrip()
                flags.append('MODEL_CONTINUATION_OUTSIDE_CROP_REMOVED')
            else:
                audit['status'] = 'SOURCE_END_ALIGNED'
    uncertain = row.get('uncertain', True) or any(f in flags for f in (
        'SOURCE_CROP_CONTINUATION_REVIEW_REQUIRED', 'SOURCE_CROP_TAIL_REVIEW_REQUIRED',
        'MODEL_CONTINUATION_OUTSIDE_CROP_REMOVED'))
    return dict(row, markdown=text, boundary_context=context, boundary_audit=audit,
                flags=list(dict.fromkeys(flags)), uncertain=uncertain,
                status='INCOMPLETE' if row.get('errors') else 'REVIEW_REQUIRED' if uncertain else 'OK')
