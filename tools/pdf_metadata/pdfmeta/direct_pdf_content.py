"""Printed-label pairing of direct OCR, using the original v2 public export shape.

No reference export is accepted. Coordinates describe observed source crops,
not falsely precise glyphs. Unlabelled material remains available separately.
"""
import re

from .section_markers import hint
from .storage import read_json, write_json, write_jsonl
from .paired.transcription_v2.exports import atomic_text, compact_content
from .direct_pdf_preview import publish_preview
from .pdf_text_layout import heading


QUESTION = re.compile(r'^(?:Câu|Bài|Ví\s+dụ|Question|Example)\s*\d+[a-z]?(?=[\s.:)\-]|$)', re.I)
ANSWER = re.compile(r'^(?:Đáp\s*(?:án|số)|Answer)\s*[:.]?\s*(.*)$', re.I)
SOLUTION = re.compile(r'^(?:Lời\s+giải|Hướng\s+dẫn|Giải|Solution)\s*[:.]\s*(.+)$', re.I)


def bare_line(line):
    return re.sub(r'^[#>\s]+', '', line).strip().strip('*_').strip()


def pieces(markdown):
    """Split only printed labels; do not infer answers or generate solution steps."""
    current, lines = None, []
    for line in markdown.splitlines():
        plain = bare_line(line)
        section = hint(plain)
        role = ('heading' if heading(plain) else
                'question' if QUESTION.match(plain) else
                'solution' if (section and section['kind'] == 'SOLUTION') or SOLUTION.match(plain) else
                'answer' if ANSWER.match(plain) else None)
        if role:
            if lines:
                yield current, '\n'.join(lines).strip()
            current, lines = role, []
        lines.append(line)
    if lines:
        yield current, '\n'.join(lines).strip()


def empty_part():
    return {'markdown': '', 'choices': [], 'source_spans': [], 'raw_text_lossy': None, 'fragments': []}


def export_content(output, pages, source):
    records, unassigned = [], []
    assets = {}
    if (output / 'layout.json').exists():
        layout = read_json(output / 'layout.json')
        if layout.get('input_sha256') == source['sha256']:
            assets = {n['visual_asset']['id']: dict(n['visual_asset']) for r in layout['regions']
                      for n in r['nodes'] if n.get('visual_asset')}
    current, role = None, None
    context = {}
    previous_page = None
    for page in pages:
        native_used = set()
        if previous_page is not None and page['page_number'] != previous_page + 1:
            current, role = None, None
            context = {}
        previous_page = page['page_number']
        for region in page['regions']:
            for block in region.get('blocks', []):
                if block.get('visual_asset'):
                    assets[block['asset_id']] = dict(block['visual_asset'])
                if block['kind'] in {'TABLE', 'VISUAL'}:
                    parts = [(None, block['markdown'])]
                else:
                    parts = pieces(block['markdown'])
                for label, text in parts:
                    if not text:
                        continue
                    if label == 'heading':
                        found = heading(bare_line(text.splitlines()[0]))
                        if found:
                            found.update(page_number=page['page_number'], bbox=block['bbox'],
                                         method='PRINTED_OCR_HEADING', source_verified=False)
                            if found['kind'] == 'chapter':context = {'chapter': found}
                            elif found['kind'] == 'topic':
                                context.pop('exercise_type', None)
                                context['topic'] = found
                            elif found['kind'] == 'section':
                                context.pop('exercise_type', None)
                                context.pop('topic', None)
                                context['section'] = found
                            else:context['exercise_type'] = found
                        current, role = None, None
                        unassigned.append({'page_number': page['page_number'], 'block': block, 'markdown': text,
                                           'reason': 'PRINTED_HEADING_CONTEXT'})
                        continue
                    if label == 'question':
                        match = re.search(r'(?:Câu|Bài|Ví\s+dụ|Question|Example)\s*(\d+)', bare_line(text), re.I)
                        source_number = int(match[1]) if match else None
                        native_index = next((i for i, c in enumerate(page.get('question_contexts', []))
                                             if i not in native_used and c['source_number'] == source_number), None)
                        native = page['question_contexts'][native_index] if native_index is not None else None
                        if native_index is not None:native_used.add(native_index)
                        topic_context = native['context'] if native else context
                        number = len(records) + 1
                        current = {'collection_number': number,
                                   'question_id': f"{source['sha256'][:24]}:p{page['page_number']:04}:r{region['region_number']:03}:q{number:04}",
                                   'chapter_title': topic_context.get('chapter', {}).get('title', source['name'].rsplit('.', 1)[0]), 'source': source,
                                   'source_number': source_number, 'topic_context': dict(topic_context),
                                   'parts': {r: empty_part() for r in ['question', 'solution', 'answer']},
                                   'tables': [], 'visual_assets': []}
                        records.append(current)
                        role = 'question'
                    elif label:
                        role = label
                    # Unlabelled text and visuals continue the active part across
                    # consecutive pages and embedded image boundaries. Only a
                    # printed label changes the question/role; a page gap resets it.
                    if current is None or role is None:
                        unassigned.append({'page_number': page['page_number'], 'block': block, 'markdown': text})
                        continue
                    part = current['parts'][role]
                    span = {'page_number': page['page_number'], 'bbox': block['bbox'], 'block_ids': [],
                            'column': None, 'layout_method': block.get('acquisition_method',
                                'PRESERVED_VISUAL_SOURCE' if block['kind'] == 'VISUAL' else 'DIRECT_VISUAL_OCR_CROP')}
                    fragment = {'page_number': page['page_number'], 'bbox': block['bbox'],
                                'source_asset': block['source_image'], 'source_asset_sha256': block['source_image_sha256'],
                                'markdown': text, 'choices': [],
                                'blocks': [{'kind': block['kind'], 'bbox': block['bbox'], 'markdown': text,
                                            **({'asset_id': block['asset_id']} if block.get('asset_id') else {})}],
                                'coverage': {'method': 'SOURCE_IMAGE_PRESERVATION' if block['kind'] == 'VISUAL' else 'RASTER_CROP_OCR_NOT_GLYPH_COVERAGE',
                                             'complete_formula_recall_established': False},
                                'source_errors': block.get('errors', []),
                                'visual_flags': [('SOURCE_VISUAL_PRESERVED' if block['kind'] == 'VISUAL' else 'OCR_NOT_SOURCE_VERIFIED'),
                                                 'ROLE_BOUNDARY_HEURISTIC', *block.get('flags', []),
                                                 *(['VISUAL_BOUNDARY_REVIEW_REQUIRED'] if block['kind'] == 'VISUAL' and block.get('uncertain') else [])],
                                'status': block['status'],
                                **({'quality_audit': block['quality_audit']} if block.get('quality_audit') else {})}
                    part['source_spans'].append(span)
                    part['fragments'].append(fragment)
                    if block.get('visual_asset'):
                        visual = dict(block['visual_asset'], role=role, question_id=current['question_id'])
                        if not any(a['id'] == visual['id'] for a in current['visual_assets']):
                            current['visual_assets'].append(visual)
                        assets[visual['id']] = visual
                    if block['kind'] == 'TABLE':
                        table = dict(block['table'], role=role)
                        current['tables'].append(table)
    for row in records:
        for part in row['parts'].values():
            part['markdown'] = '\n\n'.join(f['markdown'] for f in part['fragments'])
    contents = [compact_content(row) for row in records]
    write_json(output / 'content.draft.pretty.json', contents)
    write_jsonl(output / 'content.draft.jsonl', contents)
    write_json(output / 'content.unassigned.pretty.json', unassigned)
    write_json(output / 'visual-assets.json', list(assets.values()))
    topics = {}
    for row in contents:
        topic = next((row.get('topic_context', {}).get(k) for k in ['exercise_type', 'topic', 'chapter']
                      if row.get('topic_context', {}).get(k)), None)
        if topic:
            topics.setdefault(topic['label'], []).append(row['collection_number'])
    write_json(output / 'topics.json', {'method': 'PRINTED_SOURCE_HEADINGS', 'topics': [
        {'label': label, 'question_numbers': numbers, 'count': len(numbers)} for label, numbers in topics.items()],
        'unclassified_questions': [r['collection_number'] for r in contents if not any(
            r.get('topic_context', {}).get(k) for k in ['exercise_type', 'topic', 'chapter'])]})
    write_json(output / 'content-structure.json', {
        'method': 'PRINTED_LABEL_HEURISTIC', 'questions': len(contents),
        'status': 'BOUNDARIES_REQUIRE_REVIEW' if contents else 'NO_PRINTED_QUESTION_LABELS',
        'chapter_title_method': 'PRINTED_HEADING_OR_INPUT_FILENAME_FALLBACK',
        'questions_with_solutions': sum(bool(c['solution']['markdown']) for c in contents),
        'unassigned_fragments': len(unassigned), 'question_boundaries_verified': False,
        'uses_reference_json': False, 'source_coordinates': 'INPUT_PDF_ONLY'})
    publish_preview(output, pages, contents, list(assets.values()), source, unassigned)
    return len(contents)


def publish_pages(output, pages, source):
    write_json(output / 'pages.ocr.pretty.json', pages)
    with atomic_text(output / 'document.ocr.md') as stream:
        for page in pages:
            stream.write(f"## Page {page['page_number']}\n\n" + page['native_text_from_this_pdf'] + '\n\n' + page['markdown'] + '\n\n')
    return export_content(output, pages, source)
