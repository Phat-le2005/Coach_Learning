"""Separate-process, local-only layout acquisition before Qwen text OCR."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .direct_pdf_regions import plan_visual_regions
from .storage import configure_storage, file_hash, inference_versions, read_json, write_json

VERSION = 'direct-pdf-layout/v1'
MODEL = 'PP-DocLayoutV3'
THRESHOLD = .4


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def model_identity(runtime):
    root = Path(runtime) / 'paddlex/official_models' / MODEL
    paths = [root / name for name in ['inference.pdiparams', 'inference.json', 'inference.yml']]
    if not all(p.is_file() for p in paths):
        raise ValueError('LOCAL_LAYOUT_MODEL_MISSING_PP_DOCLAYOUTV3')
    return {'name': MODEL, 'files': {p.name: file_hash(p) for p in paths}, 'packages': inference_versions()}


def layout_identity(pdf, runtime, dpi, *, model=None):
    return digest({'source_sha256': file_hash(Path(pdf)), 'dpi': dpi, 'model': model or model_identity(runtime),
                   'threshold': THRESHOLD, 'version': VERSION,
                   'code': file_hash(Path(__file__)),
                   'geometry_code': file_hash(Path(__file__).with_name('direct_pdf_regions.py'))})


class Detector:
    def __init__(self, runtime):
        configure_storage(Path(runtime))
        os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
        from paddleocr import LayoutDetection
        self.model = LayoutDetection(model_name=MODEL,
            model_dir=str(Path(runtime) / 'paddlex/official_models' / MODEL),
            device='cpu', cpu_threads=3, enable_mkldnn=False)

    def predict(self, path):
        value = list(self.model.predict(str(path), batch_size=1, threshold=THRESHOLD))[0].json
        raw = value.get('res', value)
        # Convert numpy scalars/coordinates without retaining tensors or model objects.
        return json.loads(json.dumps(raw.get('boxes', []), default=lambda v: v.tolist() if hasattr(v, 'tolist') else str(v)))


def _valid_record(output, record):
    try:
        source = (output / record['source_image']).resolve()
        if not source.is_relative_to((output / 'assets').resolve()) or file_hash(source) != record['source_image_sha256']:
            return False
        for node in record['nodes']:
            if node['kind'] != 'VISUAL':
                continue
            asset = node['visual_asset']
            path = (output / asset['path']).resolve()
            if not path.is_relative_to((output / 'visual_assets').resolve()) or file_hash(path) != asset['sha256']:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def cached_layout(pdf, runtime, output, pages, dpi):
    try:
        manifest = read_json(Path(output) / 'layout.json')
        if manifest['identity'] != layout_identity(pdf, runtime, dpi) or manifest['page_selection'] != pages:
            return None
        if not all(_valid_record(Path(output), r) for r in manifest['regions']):
            return None
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        return None


def ensure_layout(pdf, runtime, output, pages, dpi):
    manifest = cached_layout(pdf, runtime, output, pages, dpi)
    if manifest is None:
        # The model and Paddle runtime exit with this process before Qwen starts.
        subprocess.run([sys.executable, '-B', '-u', '-m', 'pdfmeta.direct_pdf_layout',
                        '--pdf', str(pdf), '--runtime', str(runtime), '--output', str(output),
                        '--pages', pages, '--dpi', str(dpi)], check=True)
        manifest = cached_layout(pdf, runtime, output, pages, dpi)
    if manifest is None:
        raise ValueError('LAYOUT_CHECKPOINT_NOT_VERIFIED')
    return manifest


def prepare(pdf, runtime, output, *, pages='all', dpi=240, detector=None, model=None):
    import pypdfium2 as pdfium
    from .direct_pdf_ocr import selected_pages, page_regions, pdf_box
    pdf, runtime, output = Path(pdf).resolve(), Path(runtime).resolve(), Path(output).resolve()
    identity = layout_identity(pdf, runtime, dpi, model=model)
    prediction_model = model or model_identity(runtime)
    source_sha = file_hash(pdf)
    records = []
    calls = hits = 0
    with pdfium.PdfDocument(pdf) as doc:
        chosen = selected_pages(pages, len(doc))
        for pn in chosen:
            page = doc[pn - 1]
            try:
                boxes, image_mode = page_regions(page)
                width, height = page.get_size()
                bitmap = page.render(scale=dpi / 72)
                try:
                    image = bitmap.to_pil().copy()
                finally:
                    bitmap.close()
                try:
                    for ri, box in enumerate(boxes, 1):
                        record_path = output / f'layout/page-{pn:04}-region-{ri:03}.json'
                        previous = read_json(record_path) if record_path.exists() else {}
                        if previous.get('identity') == identity and previous.get('bbox') == list(box) and _valid_record(output, previous):
                            records.append(previous)
                            hits += 1
                            continue
                        asset = f'assets/page-{pn:04}-region-{ri:03}.png'
                        target = output / asset
                        target.parent.mkdir(parents=True, exist_ok=True)
                        sx, sy = image.width / width, image.height / height
                        with image.crop((int(box[0] * sx), int(box[1] * sy), round(box[2] * sx), round(box[3] * sy))) as crop:
                            crop.save(target)
                            prediction_key = digest({'model': prediction_model, 'image': file_hash(target),
                                                     'threshold': THRESHOLD, 'adapter': VERSION})
                            if previous.get('prediction_identity') == prediction_key:
                                detections = previous['detections']
                                hits += 1
                            else:
                                if detector is None:
                                    detector = Detector(runtime)
                                print(f'[layout] page {pn} region {ri}/{len(boxes)}', flush=True)
                                detections = detector.predict(target)
                                calls += 1
                            nodes = plan_visual_regions(crop, detections, dpi)
                            for order, node in enumerate(nodes):
                                node['order'] = order
                                node['bbox_pdf'] = pdf_box(node['bbox'], box, crop)
                                if node['kind'] != 'VISUAL':
                                    continue
                                visual_id = digest({'pdf': source_sha, 'page': pn,
                                                    'bbox': [round(v, 3) for v in node['bbox_pdf']]})[:24]
                                relative = f'visual_assets/page-{pn:04}/{visual_id}.png'
                                path = output / relative
                                path.parent.mkdir(parents=True, exist_ok=True)
                                with crop.crop(node['bbox']) as visual:
                                    visual.save(path)
                                node['visual_asset'] = {'id': visual_id, 'kind': node['visual_kind'], 'path': relative,
                                    'page_number': pn, 'bbox': node['bbox_pdf'], 'sha256': file_hash(path),
                                    'status': 'PRESERVED_AS_IMAGE', 'review_required': node['review_required'],
                                    'detector': node['detector'], 'score': node['score'], 'source_sha256': source_sha}
                        record = {'identity': identity, 'page_number': pn, 'region_number': ri, 'bbox': list(box),
                                  'image_mode': image_mode, 'source_image': asset,
                                  'source_image_sha256': file_hash(target), 'nodes': nodes, 'detections': detections,
                                  'prediction_identity': prediction_key}
                        write_json(record_path, record)
                        records.append(record)
                finally:
                    image.close()
            finally:
                page.close()
    if file_hash(pdf) != source_sha:
        raise ValueError('INPUT_PDF_CHANGED_DURING_LAYOUT')
    manifest = {'version': VERSION, 'identity': identity, 'input_sha256': source_sha, 'input_pdf': str(pdf),
                'page_selection': pages, 'selected_pages': chosen, 'dpi': dpi, 'regions': records,
                'model_calls_this_run': calls, 'cache_hits_this_run': hits, 'external_reference_inputs': []}
    write_json(output / 'layout.json', manifest)
    assets = {n['visual_asset']['id']: n['visual_asset'] for r in records for n in r['nodes'] if n['kind'] == 'VISUAL'}
    write_json(output / 'visual-assets.json', list(assets.values()))
    print(f'[layout] {len(assets)} visual assets; calls={calls}, cache hits={hits}', flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['pdf', 'runtime', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--pages', default='all')
    parser.add_argument('--dpi', type=int, default=240)
    prepare(**vars(parser.parse_args()))


if __name__ == '__main__':
    main()
