"""Separate-process, local-only layout acquisition before Qwen text OCR."""
from __future__ import annotations

import argparse
import ast
import hashlib
from importlib.metadata import version as package_version
import json
import io
import os
from pathlib import Path
import subprocess
import sys

from .direct_pdf_regions import plan_visual_regions
from .storage import configure_storage, file_hash, inference_versions, read_json, write_json
from .pdf_text_layout import inspect_document, content_regions, heading_only_text, report as text_layout_report

VERSION = 'direct-pdf-layout/v1'
MODEL = 'PP-DocLayoutV3'
THRESHOLD = .4
CACHE_VERSION = 2


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def model_identity(runtime):
    root = Path(runtime) / 'paddlex/official_models' / MODEL
    paths = [root / name for name in ['inference.pdiparams', 'inference.json', 'inference.yml']]
    if not all(p.is_file() for p in paths):
        raise ValueError('LOCAL_LAYOUT_MODEL_MISSING_PP_DOCLAYOUTV3')
    return {'name': MODEL, 'files': {p.name: file_hash(p) for p in paths}, 'packages': inference_versions()}


def function_identity(path, names):
    """Hash relevant definitions, excluding unrelated OCR/backend/UI edits."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8-sig'))
    definitions = {n.name: ast.dump(n, include_attributes=False) for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name in names}
    if set(definitions) != set(names):
        raise ValueError('LAYOUT_GEOMETRY_DEFINITION_MISSING')
    return digest(definitions)


def raster_identity(source_sha, dpi):
    return digest({'source_sha256': source_sha, 'dpi': dpi,
                   'render': function_identity(__file__, ['_render_page', '_crop_page']),
                   'packages': {n: package_version(n) for n in ('pypdfium2', 'Pillow')}})


def layout_identity(pdf, runtime, dpi, *, model=None, source_sha=None):
    source_sha = source_sha or file_hash(Path(pdf))
    return digest({'source_sha256': source_sha, 'dpi': dpi, 'model': model or model_identity(runtime),
                   'threshold': THRESHOLD, 'version': VERSION, 'cache_version': CACHE_VERSION,
                   'raster': raster_identity(source_sha, dpi),
                   'assembly': function_identity(__file__, ['_build_record']),
                   'page_geometry': function_identity(Path(__file__).with_name('direct_pdf_ocr.py'), ['page_regions', 'pdf_box']),
                   'geometry_code': file_hash(Path(__file__).with_name('direct_pdf_regions.py')),
                   'text_layout': {name: file_hash(Path(__file__).parent / name)
                                   for name in ['pdf_text_layout.py', 'native.py', 'paired/fast_native.py']}})


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


def _valid_source(output, record, hashes=None):
    try:
        source = (output / record['source_image']).resolve()
        if not source.is_relative_to((output / 'assets').resolve()):
            return False
        if hashes is None:
            return file_hash(source) == record['source_image_sha256']
        if source not in hashes:
            hashes[source] = file_hash(source)
        return hashes[source] == record['source_image_sha256']
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _valid_record(output, record, hashes=None):
    try:
        if not _valid_source(output, record, hashes):
            return False
        for node in record['nodes']:
            if node['kind'] not in {'TEXT', 'VISUAL'}:
                return False
            if node['kind'] != 'VISUAL':
                continue
            asset = node['visual_asset']
            path = (output / asset['path']).resolve()
            if not path.is_relative_to((output / 'visual_assets').resolve()) or file_hash(path) != asset['sha256']:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def cached_layout(pdf, runtime, output, pages, dpi, *, model=None, identity=None, source_sha=None):
    try:
        from .direct_pdf_ocr import selected_pages
        manifest = read_json(Path(output) / 'layout.json')
        source_sha = source_sha or file_hash(Path(pdf))
        identity = identity or layout_identity(pdf, runtime, dpi, model=model, source_sha=source_sha)
        if (manifest['identity'] != identity or manifest.get('cache_version') != CACHE_VERSION
                or manifest['input_sha256'] != source_sha or manifest['dpi'] != dpi):
            return None
        chosen = selected_pages(pages, manifest['page_count'])
        if manifest['selected_pages'] != chosen:
            return None
        counts = manifest['page_region_counts']
        expected = {(pn, ri) for pn in chosen for ri in range(1, counts[str(pn)] + 1)}
        records = manifest['regions']
        actual = [(r['page_number'], r['region_number']) for r in records]
        if (not expected or any(counts[str(pn)] < 1 for pn in chosen)
                or len(actual) != len(expected) or set(actual) != expected or actual != sorted(actual)):
            return None
        hashes = {}
        if not all(r['identity'] == identity and r.get('source_sha256') == source_sha
                   and r.get('dpi') == dpi and _valid_record(Path(output), r, hashes) for r in records):
            return None
        return dict(manifest, page_selection=pages, model_calls_this_run=0, cache_hits_this_run=len(records),
                    rendered_pages_this_run=0, source_crops_reused_this_run=0,
                    upgraded_records_this_run=0, cache_status='COMPLETE_CACHE_REUSED')
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


def _render_page(page, dpi):
    bitmap = page.render(scale=dpi / 72)
    try:
        return bitmap.to_pil().copy()
    finally:
        bitmap.close()


def _crop_page(image, box, width, height):
    sx, sy = image.width / width, image.height / height
    return image.crop((int(box[0] * sx), int(box[1] * sy), round(box[2] * sx), round(box[3] * sy)))


def _build_record(crop, detections, *, output, pdf_box, box, pn, ri, dpi, source_sha,
                  identity, raster, prediction_key, asset, image_sha, page, image_mode):
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
            'coordinate_reference': 'VISIBLE_PAGE_TOP_LEFT_PDF_POINT',
            'detector': node['detector'], 'score': node['score'], 'source_sha256': source_sha}
    return {'identity': identity, 'cache_version': CACHE_VERSION, 'source_sha256': source_sha,
            'dpi': dpi, 'raster_identity': raster, 'page_number': pn, 'region_number': ri, 'bbox': list(box),
            'page_size': list(page.get_size()), 'source_cropbox': list(page.get_cropbox()),
            'image_mode': image_mode, 'source_image': asset, 'source_image_sha256': image_sha,
            'nodes': nodes, 'detections': detections, 'prediction_identity': prediction_key}


def _read_record(path):
    try:
        value = read_json(path)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _assets(records):
    return {n['visual_asset']['id']: n['visual_asset'] for r in records for n in r['nodes'] if n['kind'] == 'VISUAL'}


def _write_assets(output, records):
    write_json(output / 'visual-assets.json', list(_assets(records).values()))


def _valid_asset_registry(output, records):
    try:
        rows = read_json(output / 'visual-assets.json')
        actual = {r['id']: r for r in rows}
        expected = _assets(records)
        return (len(rows) == len(actual) and set(actual) == set(expected)
                and all(all(actual[key].get(k) == v for k, v in asset.items())
                        for key, asset in expected.items()))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def prepare(pdf, runtime, output, *, pages='all', dpi=240, detector=None, model=None):
    import pypdfium2 as pdfium
    from PIL import Image
    from .direct_pdf_ocr import selected_pages, page_regions, pdf_box
    pdf, runtime, output = Path(pdf).resolve(), Path(runtime).resolve(), Path(output).resolve()
    if output == runtime or output == pdf:
        raise ValueError('SEPARATE_OUTPUT_REQUIRED')
    if not 72 <= dpi <= 400:
        raise ValueError('INVALID_LAYOUT_DPI')
    source_sha = file_hash(pdf)
    prediction_model = model or model_identity(runtime)
    identity = layout_identity(pdf, runtime, dpi, model=prediction_model, source_sha=source_sha)
    raster = raster_identity(source_sha, dpi)
    legacy_job_verified = False
    # Old records lack individual PDF/DPI bindings: require the enclosing job's
    # source proof and rebuild their nodes from its verified PNGs, not the PDF.
    for name in ['run-identity.json', 'layout.json']:
        if (output / name).exists():
            previous_job = read_json(output / name)
            if ((previous_job.get('input_sha256') and previous_job['input_sha256'] != source_sha)
                    or (previous_job.get('dpi') and previous_job['dpi'] != dpi)):
                raise ValueError('INPUT_OR_DPI_CHANGED_USE_NEW_OUTPUT')
            legacy_job_verified |= (previous_job.get('input_sha256') == source_sha
                                    and previous_job.get('dpi') == dpi)
    complete = cached_layout(pdf, runtime, output, pages, dpi, model=prediction_model,
                             identity=identity, source_sha=source_sha)
    if complete is not None:
        write_json(output / 'layout.json', complete)
        if not _valid_asset_registry(output, complete['regions']):
            _write_assets(output, complete['regions'])
        print(f'[layout] complete cache reused: {len(complete["selected_pages"])} pages, '
              f'{len(complete["regions"])} regions; calls=0, rendered pages=0', flush=True)
        return complete
    records = []
    calls = hits = renders = reused = upgraded = 0
    counts = {}
    with pdfium.PdfDocument(pdf) as doc:
        page_count = len(doc)
        profiles = inspect_document(doc)
        write_json(output / 'text-layout.json', text_layout_report(profiles))
        chosen = selected_pages(pages, page_count)
        for pn in chosen:
            page = doc[pn - 1]
            image = None
            try:
                boxes, image_mode = page_regions(page)
                boxes = content_regions(boxes, profiles[pn])
                counts[str(pn)] = len(boxes)
                width, height = page.get_size()
                for ri, box in enumerate(boxes, 1):
                    record_path = output / f'layout/page-{pn:04}-region-{ri:03}.json'
                    previous = _read_record(record_path)
                    geometry_matches = (previous.get('bbox') == list(box)
                        and previous.get('page_size') == [width, height]
                        and previous.get('source_cropbox') == list(page.get_cropbox())
                        and previous.get('page_number') == pn and previous.get('region_number') == ri
                        and previous.get('image_mode') == image_mode)
                    if (geometry_matches and previous.get('identity') == identity
                            and previous.get('source_sha256') == source_sha and previous.get('dpi') == dpi
                            and _valid_record(output, previous)):
                        records.append(previous)
                        hits += 1
                        continue
                    bound_source = (previous.get('source_sha256') == source_sha and previous.get('dpi') == dpi
                                    and previous.get('raster_identity') == raster)
                    legacy_source = (legacy_job_verified and 'cache_version' not in previous
                                     and 'source_sha256' not in previous and 'raster_identity' not in previous)
                    can_reuse = geometry_matches and (bound_source or legacy_source) and _valid_source(output, previous)
                    crop = None
                    if can_reuse:
                        try:
                            with Image.open(output / previous['source_image']) as saved:
                                crop = saved.copy()
                            reused += 1
                        except (OSError, ValueError):
                            can_reuse = False
                    if not can_reuse:
                        if image is None:
                            image = _render_page(page, dpi)
                            renders += 1
                        crop = _crop_page(image, box, width, height)
                    try:
                        if can_reuse:
                            image_sha = previous['source_image_sha256']
                            asset = previous['source_image']
                        else:
                            encoded = io.BytesIO()
                            crop.save(encoded, format='PNG')
                            encoded = encoded.getvalue()
                            image_sha = hashlib.sha256(encoded).hexdigest()
                            asset = f'assets/source/page-{pn:04}-region-{ri:03}-{image_sha[:16]}.png'
                            target = output / asset
                            target.parent.mkdir(parents=True, exist_ok=True)
                            if not target.exists() or file_hash(target) != image_sha:
                                target.write_bytes(encoded)
                        target = output / asset
                        prediction_key = digest({'model': prediction_model, 'image': image_sha,
                                                 'threshold': THRESHOLD, 'adapter': VERSION})
                        if heading_only_text(profiles[pn]):
                            detections = []
                        elif previous.get('prediction_identity') == prediction_key and isinstance(previous.get('detections'), list):
                            detections = previous['detections']
                            hits += 1
                        else:
                            if detector is None:
                                detector = Detector(runtime)
                            print(f'[layout] page {pn} region {ri}/{len(boxes)}', flush=True)
                            detections = detector.predict(target)
                            calls += 1
                        record = _build_record(crop, detections, output=output, pdf_box=pdf_box, box=box,
                            pn=pn, ri=ri, dpi=dpi, source_sha=source_sha, identity=identity, raster=raster,
                            prediction_key=prediction_key, asset=asset, image_sha=image_sha, page=page, image_mode=image_mode)
                        write_json(record_path, record)
                        records.append(record)
                        if previous and previous.get('cache_version') != CACHE_VERSION:
                            upgraded += 1
                    finally:
                        crop.close()
            finally:
                if image is not None:
                    image.close()
                page.close()
            if pn == chosen[0] or pn == chosen[-1] or pn % 50 == 0:
                print(f'[layout-cache] page {pn}: calls={calls}, cache hits={hits}, '
                      f'rendered pages={renders}, source crops reused={reused}', flush=True)
    if file_hash(pdf) != source_sha:
        raise ValueError('INPUT_PDF_CHANGED_DURING_LAYOUT')
    manifest = {'version': VERSION, 'cache_version': CACHE_VERSION, 'identity': identity,
                'input_sha256': source_sha, 'input_pdf': str(pdf), 'page_count': page_count,
                'page_selection': pages, 'selected_pages': chosen, 'page_region_counts': counts,
                'dpi': dpi, 'regions': records, 'model_calls_this_run': calls, 'cache_hits_this_run': hits,
                'rendered_pages_this_run': renders, 'source_crops_reused_this_run': reused,
                'upgraded_records_this_run': upgraded, 'cache_status': 'PREPARED', 'external_reference_inputs': []}
    write_json(output / 'layout.json', manifest)
    _write_assets(output, records)
    print(f'[layout] {len(_assets(records))} visual assets; calls={calls}, cache hits={hits}, '
          f'rendered pages={renders}, source crops reused={reused}', flush=True)
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
