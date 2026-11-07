"""Offline text/math/visual review; all model content is treated as text."""
import json
from pathlib import Path
import shutil

from .paired.transcription_v2.exports import atomic_text
from .math_display import prepare, VERSION as DISPLAY_VERSION
from .storage import read_json, write_json


def publish_preview(output, pages, content, assets, source, unassigned):
    rendering = []
    def display(text, owner, role):
        result = prepare(text)
        rendering.append({'owner': owner, 'role': role, 'repairs': result['repairs'], 'issues': result['issues'],
                          'math_tokens': sum(t['kind']=='math' for t in result['tokens'])})
        return result
    katex = Path(__file__).parents[3] / 'frontend/node_modules/katex/dist'
    vendor = output / 'vendor'
    vendor.mkdir(parents=True, exist_ok=True)
    for name in ['katex.min.js', 'katex.min.css']:
        if (katex / name).is_file() and not (vendor / name).exists():
            shutil.copy2(katex / name, vendor / name)
    if (katex / 'fonts').is_dir() and not (vendor / 'fonts').exists():
        shutil.copytree(katex / 'fonts', vendor / 'fonts')
    data = {'source': source, 'questions': [{
                'number': c['collection_number'], 'id': c['question_id'],
                'source_number': c.get('source_number'), 'topic_context': c.get('topic_context', {}),
                **{role: c[role]['markdown'] for role in ['question', 'solution', 'answer']},
                'display': {role: display(c[role]['markdown'], c['question_id'], role)
                            for role in ['question', 'solution', 'answer']},
                'source_assets': [{'role': role, 'page': f['page_number'], 'path': f['source_asset']}
                                  for role in ['question', 'solution', 'answer'] for f in c[role]['fragments']
                                  if any(b['kind'] == 'TEXT' for b in f['blocks'])],
                'visual_assets': c.get('visual_assets', [])} for c in content],
            'pages': [{'number': p['page_number'], 'markdown': p['native_text_from_this_pdf'] + '\n\n' + p['markdown'],
                       'display': display(p['native_text_from_this_pdf'] + '\n\n' + p['markdown'], p['page_number'], 'page')}
                      for p in pages], 'visual_assets': assets, 'unassigned_fragments': len(unassigned),
            'failed_regions': sum(r.get('status') == 'INCOMPLETE' for p in pages for r in p['regions']),
            'review_regions': sum(r.get('status') == 'REVIEW_REQUIRED' for p in pages for r in p['regions'])}
    payload = json.dumps(data, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    payload = payload.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    template = Path(__file__).with_name('direct_pdf_review.html').read_text(encoding='utf-8')
    with atomic_text(output / 'review.html') as stream:
        stream.write(template.replace('__OCR_REVIEW_DATA__', payload))
    write_json(output / 'rendering-report.json', {'version': DISPLAY_VERSION, 'source_text_modified': False,
               'mathematical_accuracy_established': False, 'parts': rendering})


def refresh(output):
    """Rebuild presentation from saved exports, without OCR or transcript edits."""
    output = Path(output).resolve()
    pages = read_json(output / 'pages.ocr.pretty.json')
    content = read_json(output / 'content.draft.pretty.json')
    if not content:
        raise ValueError('NO_EXPORTED_QUESTION_SOURCE')
    source = content[0]['source']
    if any(c['source']['sha256'] != source['sha256'] for c in content):
        raise ValueError('MIXED_SOURCE_EXPORTS')
    assets = read_json(output / 'visual-assets.json')
    unassigned = read_json(output / 'content.unassigned.pretty.json')
    publish_preview(output, pages, content, assets, source, unassigned)
    return {'review_html': str(output / 'review.html'), 'questions': len(content), 'ocr_calls': 0,
            'transcription_modified': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Refresh saved PDF review with the current renderer; no OCR.')
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(refresh(parser.parse_args().output), ensure_ascii=False, indent=2))
