"""A physically separate collection containing solved occurrences only."""
from copy import deepcopy
from pathlib import Path
import base64

from PIL import Image

from ..storage import file_hash, read_json, write_json
from .dataset import export, from_html
from .viewer import render


def collect(job, output):
    job, output = Path(job).resolve(), Path(output).resolve()
    report = read_json(job/'paired.json')
    if report['structural_errors']:
        raise ValueError('RESOLVE_STRUCTURAL_ERRORS_BEFORE_COLLECTION_EXPORT')
    payload = from_html(report['single_file_html'])
    payload = deepcopy(payload)
    original_count = len(payload['questions'])
    payload['questions'] = [q for q in payload['questions'] if q['pair_status']=='PAIRED_LAYOUT_CANDIDATE']
    if not payload['questions']:
        raise ValueError('NO_SOLVED_QUESTION_OCCURRENCES')
    for number, q in enumerate(payload['questions'],1):
        q['collection_number'] = number
    used = {s['asset_path'] for q in payload['questions'] for role in ['question','solution','answer']
            for s in q[role]['source_spans'] if s.get('asset_path')}
    payload['images'] = {k:v for k,v in payload['images'].items() if k in used}
    payload['unassigned_blocks'] = []
    payload['page_coverage'] = []
    payload['collection'] = {'kind':'SOLVED_SOURCE_OCCURRENCES_ONLY','selected':len(payload['questions']),
        'excluded_unpaired_occurrences':original_count-len(payload['questions']),
        'source_paired_html_sha256':file_hash(Path(report['single_file_html']))}
    output.mkdir(parents=True,exist_ok=True)
    assets=output/'assets';assets.mkdir(exist_ok=True)
    for q in payload['questions']:
        grouped={}
        for role in ['question','solution','answer']:
            for span in q[role]['source_spans']:
                grouped.setdefault(span['page_number'],[]).append(span)
        q['collection_source_spans']=[]
        for page_number,spans in sorted(grouped.items()):
            page=read_json(job/f'native/pages/page-{page_number:03}.json')
            bbox=[min(s['bbox'][0] for s in spans),min(s['bbox'][1] for s in spans),
                  max(s['bbox'][2] for s in spans),max(s['bbox'][3] for s in spans)]
            image_path=job/'native'/page['image_path']
            key=f"assets/combined-{q['collection_number']:04}-p{page_number:03}.png"
            target=output/key
            with Image.open(image_path) as image:
                sx,sy=image.width/page['width'],image.height/page['height']
                image.crop((max(0,int(bbox[0]*sx)),max(0,int(bbox[1]*sy)),
                    min(image.width,round(bbox[2]*sx)),min(image.height,round(bbox[3]*sy)))).save(target)
            payload['images'][key]={'sha256':file_hash(target),'data_url':'data:image/png;base64,'+base64.b64encode(target.read_bytes()).decode()}
            q['collection_source_spans'].append({'page_number':page_number,'bbox':bbox,
                'block_ids':sorted({b for s in spans for b in s['block_ids']}),'asset_path':key})
    html = output/'cau-hoi-co-loi-giai.html'
    render(html,payload)
    exports = export(html,output)
    manifest = {'selected_questions':len(payload['questions']),
        'excluded_unpaired_occurrences':original_count-len(payload['questions']),
        'standalone_html':str(html),'source_pdf_sha256':payload['source']['sha256'],
        'source_paired_html':report['single_file_html'], **exports}
    write_json(output/'collection.json',manifest)
    return manifest
