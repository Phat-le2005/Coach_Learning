"""Offline text/math/visual review; all model content is treated as text."""
import json
from pathlib import Path
import shutil

from .paired.transcription_v2.exports import atomic_text


def publish_preview(output, pages, content, assets, source, unassigned):
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
                **{role: c[role]['markdown'] for role in ['question', 'solution', 'answer']},
                'source_assets': [{'role': role, 'page': f['page_number'], 'path': f['source_asset']}
                                  for role in ['question', 'solution', 'answer'] for f in c[role]['fragments']
                                  if any(b['kind'] == 'TEXT' for b in f['blocks'])],
                'visual_assets': c.get('visual_assets', [])} for c in content],
            'pages': [{'number': p['page_number'], 'markdown': p['native_text_from_this_pdf'] + '\n\n' + p['markdown']}
                      for p in pages], 'visual_assets': assets, 'unassigned_fragments': len(unassigned),
            'failed_regions': sum(r.get('status') == 'INCOMPLETE' for p in pages for r in p['regions']),
            'review_regions': sum(r.get('status') == 'REVIEW_REQUIRED' for p in pages for r in p['regions'])}
    payload = json.dumps(data, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    payload = payload.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    template = Path(__file__).with_name('direct_pdf_review.html').read_text(encoding='utf-8')
    with atomic_text(output / 'review.html') as stream:
        stream.write(template.replace('__OCR_REVIEW_DATA__', payload))
