"""Detach explicitly labelled following sections, preserving all source blocks."""
from copy import deepcopy
import re


HEADING = re.compile(r'^\s*(?:DẠNG\s+\d+\s*[.:]|PHẦN\s+[IVX\d]+\s*[:.]|BÀI\s*:\s*\S|CHỦ ĐỀ\s+\d+\s*[:.])', re.I)


def detach(items, pages, orphans, *, heading_pattern=HEADING, title_size=22):
    items, orphans = deepcopy(items), deepcopy(orphans)
    lookup = {p['page_number']: p for p in pages}
    audit = []
    for item in items:
        ordered = []
        for span in item['solution']['source_spans']:
            allowed = set(span['block_ids'])
            ordered.extend((span['page_number'], b) for b in lookup[span['page_number']]['blocks'] if b['block_id'] in allowed)
        seen = set()
        ordered = [(p, b) for p, b in ordered if not ((p, b['block_id']) in seen or seen.add((p, b['block_id'])))]
        found = next(((i, p, b) for i, (p, b) in enumerate(ordered) if heading_pattern.match(b['text_raw'])), None)
        if found is None:
            continue
        index, number, heading = found
        cut_top = heading['bbox'][1]
        # A new chapter can begin with a large title/logo before its lesson label.
        before = [(i, b) for i, (p, b) in enumerate(ordered[:index]) if p == number]
        if cut_top < lookup[number]['height'] * .35 and any(
                g.get('size', 0) >= title_size for _, b in before for g in b.get('glyphs', [])):
            index = next(i for i, (p, _) in enumerate(ordered) if p == number)
            cut_top = lookup[number]['content_bounds'][1]
        kept, removed = ordered[:index], ordered[index:]
        keep_ids = {(p, b['block_id']) for p, b in kept}
        original = deepcopy(item['solution'])
        spans = []
        for span in original['source_spans']:
            ids = [bid for bid in span['block_ids'] if (span['page_number'], bid) in keep_ids]
            if not ids:
                continue
            revised = {**span, 'block_ids': ids}
            revised.pop('asset_path', None)
            if span['page_number'] == number:
                last_bottom=max(b['bbox'][3] for p,b in kept if p==number and b['block_id'] in ids)
                # Stop in the whitespace after the last retained glyph, rather
                # than including the ink fringe of the following bold heading.
                revised['bbox'] = [*span['bbox'][:3], min(span['bbox'][3], cut_top - 3, last_bottom + 1.5)]
            if revised['bbox'][3] > revised['bbox'][1]:
                spans.append(revised)
        item['solution'] = {'text_raw': ''.join(b['text_raw'] + '\n' for _, b in kept), 'source_spans': spans}
        steps = []
        for step in item['reference_steps']:
            selected = [(p, b) for p, b in kept if any(s['page_number'] == p and b['block_id'] in s['block_ids'] for s in step['source_spans'])]
            if selected:
                steps.append({**step, 'text_raw': '\n'.join(b['text_raw'] for _, b in selected),
                    'source_spans': [{'page_number': p, 'bbox': b['bbox'], 'block_ids': [b['block_id']]} for p, b in selected]})
        item['reference_steps'] = steps
        detached = [{'page_number': p, 'block_id': b['block_id'], 'bbox': b['bbox'], 'text_raw': b['text_raw'],
            'previous_question_id': item['question_id'], 'reason': 'FOLLOWING_SECTION_DETACHED_FROM_SOLUTION'} for p, b in removed]
        orphans.extend(detached)
        item['review_flags'] = sorted(set(item['review_flags'] + ['FOLLOWING_SECTION_CONTEXT_DETACHED']))
        decision = {'question_id': item['question_id'], 'heading': heading['text_raw'], 'page_number': number,
            'cut_top': cut_top, 'rule': 'EXPLICIT_SECTION_LABEL_WITH_SOURCE_GEOMETRY',
            'original_solution': original, 'detached_blocks': detached, 'kept_block_count': len(kept),
            'status': 'BOUNDARY_RULE_APPLIED_NOT_ACADEMIC_APPROVAL'}
        item['boundary_resolution'] = {k: v for k, v in decision.items() if k not in {'original_solution', 'detached_blocks'}}
        audit.append(decision)
    return items, orphans, audit
