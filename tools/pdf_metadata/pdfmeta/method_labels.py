"""Add reviewable chapter/lesson/problem-type candidates to an existing export.

Source headings establish chapter context. Local text rules propose finer labels
from the repository taxonomy; no model, database import or academic approval runs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
import unicodedata

from .storage import file_hash, read_json, write_json, write_jsonl
from .source_method_labels import document_contexts, apply_document_labels, native_document_contexts
from .metadata_contract import (normalize_record, label as normalize_label, validate_records,
                                METADATA_VERSION, METHOD_VERSION)


VERSION = 'question-method-candidates/v2'
DEFAULT_TAXONOMY = Path(__file__).parents[3] / 'backend/data/fixtures/curriculum/math_g12_full_tree_v0_1'
CHAPTER_PATTERNS = {
    'DERIVATIVE_APPLICATIONS': r'ung dung dao ham|khao sat va ve do thi',
    'INTEGRALS': r'nguyen ham|tich phan',
    'GROUPED_DATA_DISPERSION': r'thong ke so lieu ghep nhom|do muc do phan tan|so dac trung.*ghep nhom',
    'PROBABILITY_CHAPTER': r'xac suat co dieu kien|cong thuc bayes',
    'VECTORS_GEOMETRY': r'vecto va he toa do|vect[oơ].*khong gian',
    'OXYZ_CHAPTER': r'phuong phap toa do trong khong gian|\boxyz\b',
}


def plain(text):
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', text.replace('đ', 'd')).strip()


def load_taxonomy(root):
    root = Path(root)
    names = ['chapters', 'topics', 'problem_types']
    result = {name: {r['code']: r for r in read_json(root / (name+'.json'))
                     if r.get('is_active', True)} for name in names}
    for topic in result['topics'].values():
        if topic['chapter_code'] not in result['chapters']:raise ValueError('TAXONOMY_TOPIC_PARENT_MISSING')
    for kind in result['problem_types'].values():
        if kind['topic_code'] not in result['topics']:raise ValueError('TAXONOMY_TYPE_PARENT_MISSING')
    result['identity'] = {name: file_hash(root/(name+'.json')) for name in names}
    result['source'] = str(root.resolve())
    return result


def chapter_code(text):
    text = plain(text)
    matches = [code for code, pattern in CHAPTER_PATTERNS.items() if re.search(pattern, text)]
    return matches[0] if len(matches) == 1 else None


def page_chapters(pages):
    """Use only the printed header, never a contents list or expected answer."""
    result, active, previous = {}, None, None
    for page in sorted(pages, key=lambda p:p['page_number']):
        pn = page['page_number']
        if previous is not None and pn != previous+1:active = None
        previous = pn
        native = page.get('native_text_from_this_pdf', '').strip()
        first = next((s.strip() for s in native.splitlines() if s.strip()), '')
        found = chapter_code(first)
        if found:
            active = {'code': found, 'evidence': {'basis': 'SOURCE_NATIVE_PAGE_HEADER',
                      'page_number': pn, 'text': first}}
        if active:
            result[pn] = deepcopy(active)
            if active['evidence']['page_number'] != pn:
                result[pn]['evidence']['basis'] = 'PRECEDING_NATIVE_HEADER_ON_CONSECUTIVE_PAGES'
    return result


def goal_text(row):
    text = row.get('question', {}).get('markdown', '')
    # Distractors must not assign the chapter/lesson of an unrelated option.
    text = re.split(r'(?m)^\s*[ABCD][.)]\s+', text, maxsplit=1)[0]
    return plain(text)


def propose(row, chapter):
    text = goal_text(row)
    raw = row.get('question', {}).get('markdown', '')
    proposals = []
    def has(pattern):return bool(re.search(pattern, text))
    def add(topic, kind, rule, pattern, evidence_text=None, field='question.markdown'):
        match = re.search(pattern, text if evidence_text is None else evidence_text)
        proposals.append({'lesson_code': topic, 'exercise_type_code': kind, 'rule': rule,
                          'evidence': {'field': field, 'normalized_match': match[0] if match else '',
                                       'basis': 'QUESTION_TEXT_RULE_CANDIDATE'}})
    parameter = has(r'tham so|(?:tim|xac dinh|gia tri|tap hop).{0,100}\bm\b')
    graph = has(r'do thi|hinh ve|duong cong')
    variation = has(r'bang bien thien')
    derivative_sign = has(r'bang xet dau|dau (?:cua )?dao ham|dao ham.{0,60}(?:duong|am)|(?:bang bien thien|do thi).{0,60}(?:cua dao ham|cua ham dao ham)')
    world = has(r'van toc|gia toc|chuyen dong|chi phi|loi nhuan|doanh thu|san xuat|the tich|dien tich|hang rao|be nuoc|hop (?:khong nap|chu nhat|co nap)|san luong|\bnguoi\b|cong ty|quang duong')
    global_extrema = has(r'gia tri lon nhat|gia tri nho nhat|lon nhat|nho nhat|\bgtln\b|\bgtnn\b')
    if chapter == 'DERIVATIVE_APPLICATIONS':
        if world and global_extrema:
            add('DERIVATIVE_APPLICATION_TOPIC', 'REAL_WORLD_DERIVATIVE_OPTIMIZATION', 'derivative.real_world_optimization',
                r'lon nhat|nho nhat|\bgtln\b|\bgtnn\b')
        else:
            if has(r'dong bien|nghich bien|don dieu'):
                kind = ('PARAMETER_MONOTONICITY' if parameter else
                        'MONOTONICITY_FROM_DERIVATIVE_SIGN' if derivative_sign else
                        'MONOTONICITY_FROM_VARIATION_TABLE' if variation else
                        'MONOTONICITY_FROM_GRAPH' if graph else 'MONOTONICITY_FROM_EXPRESSION')
                add('MONOTONICITY_TOPIC', kind, 'derivative.monotonicity', r'dong bien|nghich bien|don dieu')
            if has(r'cuc tri|cuc dai|cuc tieu'):
                kind = ('PARAMETER_EXTREMA_COUNT' if parameter and has(r'so (?:diem )?cuc|co.{0,25}(?:cuc tri|cuc dai|cuc tieu)') else
                        None if parameter else
                        'EXTREMA_FROM_DERIVATIVE_SIGN' if derivative_sign else
                        'EXTREMA_FROM_VARIATION_TABLE' if variation else
                        'EXTREMA_FROM_GRAPH' if graph else 'FIND_FUNCTION_EXTREMA')
                add('EXTREMA_TOPIC', kind, 'derivative.extrema', r'cuc tri|cuc dai|cuc tieu')
            if global_extrema:
                kind = 'GLOBAL_EXTREMA_DERIVATIVE_INTERVAL' if has(r'tren doan') else 'GLOBAL_EXTREMA_SIMPLE_DOMAIN'
                if graph or variation:kind = 'GLOBAL_EXTREMA_RECOGNITION'
                add('GLOBAL_EXTREMA_TOPIC', kind, 'derivative.global_extrema', r'lon nhat|nho nhat|\bgtln\b|\bgtnn\b')
        if has(r'tiem can'):
            kinds = [('dung','VERTICAL_ASYMPTOTE_RATIONAL'),('ngang','HORIZONTAL_ASYMPTOTE_RATIONAL'),('xien','OBLIQUE_ASYMPTOTE_RATIONAL')]
            found = [(word,kind) for word,kind in kinds if has(r'tiem can '+word)]
            if not found:found = [('',None)]
            for word,kind in found:
                add('FUNCTION_ANALYSIS_TOPIC','ASYMPTOTE_FROM_GRAPH' if graph else kind,
                    'derivative.asymptote',r'tiem can'+(' '+word if word else ''))
        if not proposals and has(r'tam doi xung|truc doi xung'):
            add('FUNCTION_ANALYSIS_TOPIC','GRAPH_SYMMETRY_IDENTIFICATION','derivative.graph_symmetry',r'tam doi xung|truc doi xung')
        if not proposals and has(r'khao sat|ve do thi|do thi|duong cong'):
            kind = None
            if has(r'khao sat|ve do thi'):
                if has(r'bac ba'):kind = 'COMPLETE_FUNCTION_ANALYSIS_CUBIC'
                elif has(r'bac nhat.*bac nhat'):kind = 'COMPLETE_FUNCTION_ANALYSIS_LINEAR_FRACTION'
                elif has(r'bac hai.*bac nhat'):kind = 'COMPLETE_FUNCTION_ANALYSIS_QUADRATIC_OVER_LINEAR'
            elif has(r'ham so nao|ham nao|nhan dang|do thi nao'):kind = 'GRAPH_IDENTIFICATION_FROM_FEATURES'
            add('FUNCTION_ANALYSIS_TOPIC',kind,'derivative.graph_or_analysis',r'khao sat|ve do thi|do thi|duong cong')
    elif chapter == 'INTEGRALS':
        volume_goal = has(r'(?:tinh|tim|xac dinh)\s+(?:tong\s+)?the tich|the tich.{0,30}(?:bang bao nhieu|can tinh)')
        area_goal = has(r'(?:tinh|tim|xac dinh)\s+(?:tong\s+)?dien tich|dien tich.{0,30}(?:bang bao nhieu|can tinh)')
        if has(r'dien tich') and (not volume_goal or area_goal):
            add('INTEGRAL_GEOMETRIC_APPLICATION_TOPIC','AREA_BY_INTEGRAL','integral.area',r'dien tich')
        if has(r'the tich|tron xoay|thiet dien'):
            kind = 'VOLUME_BY_CROSS_SECTION' if has(r'thiet dien|cat.{0,35}mat phang') else 'VOLUME_BY_INTEGRAL' if has(r'tron xoay|quay') else None
            add('INTEGRAL_GEOMETRIC_APPLICATION_TOPIC',kind,'integral.volume',r'the tich|tron xoay|thiet dien')
        if not proposals and has(r'van toc|gia toc|quang duong|chuyen dong|luu luong|tich luy|san luong|dan so|doanh thu|chi phi|loi nhuan'):
            add('INTEGRAL_PRACTICAL_APPLICATION_TOPIC','PRACTICAL_ACCUMULATION','integral.practical_accumulation',
                r'van toc|gia toc|quang duong|chuyen dong|luu luong|tich luy|san luong|dan so|doanh thu|chi phi|loi nhuan')
        if not proposals and has(r'nguyen ham'):
            kind = 'ANTIDERIVATIVE_WITH_CONDITION' if has(r'thoa man|biet|dieu kien') else 'CALCULATE_ANTIDERIVATIVE'
            add('ANTIDERIVATIVE_TOPIC',kind,'integral.antiderivative',r'nguyen ham')
        if not proposals and has(r'tich phan'):
            kind = 'INTEGRAL_PROPERTIES' if has(r'tinh chat') else 'CALCULATE_DEFINITE_INTEGRAL'
            add('DEFINITE_INTEGRAL_TOPIC',kind,'integral.definite',r'tich phan')
        if not proposals and re.search(r'\\(?:[dt]?int|int)\b|∫', raw):
            bounded = bool(re.search(r'(?:\\int|∫)\s*[_^]',raw))
            add('DEFINITE_INTEGRAL_TOPIC' if bounded else 'ANTIDERIVATIVE_TOPIC',
                'CALCULATE_DEFINITE_INTEGRAL' if bounded else 'CALCULATE_ANTIDERIVATIVE',
                'integral.explicit_operator',r'\\int|∫')
        if not proposals and has(r"(?:dao ham|f\s*['′])") and has(r'cho ham so|ham so.{0,50}thoa man'):
            add('ANTIDERIVATIVE_TOPIC','ANTIDERIVATIVE_WITH_CONDITION','integral.derivative_with_conditions',r"dao ham|f\s*['′]")
    elif chapter == 'GROUPED_DATA_DISPERSION':
        metrics = [name for name,pattern in [('range',r'khoang bien thien'),('iqr',r'khoang tu phan vi'),
                   ('variance',r'phuong sai'),('sd',r'do lech chuan')] if has(pattern)]
        compare = has(r'so sanh|dong deu hon|on dinh hon|deu hon|phan tan hon')
        if len(metrics)>=2 and set(metrics)!={'variance','sd'}:
            add('GROUPED_DISPERSION_APPLICATION_TOPIC','MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS',
                'statistics.multiple_measures',r'khoang bien thien|khoang tu phan vi|phuong sai|do lech chuan')
        else:
            for metric in metrics:
                topic,kind,pattern = {
                    'range':('GROUPED_RANGE_IQR_TOPIC','CALCULATE_GROUPED_RANGE',r'khoang bien thien'),
                    'iqr':('GROUPED_RANGE_IQR_TOPIC','CALCULATE_GROUPED_IQR',r'khoang tu phan vi'),
                    'variance':('GROUPED_VARIANCE_SD_TOPIC','CALCULATE_GROUPED_VARIANCE',r'phuong sai'),
                    'sd':('GROUPED_VARIANCE_SD_TOPIC','CALCULATE_GROUPED_STANDARD_DEVIATION',r'do lech chuan')}[metric]
                if compare:
                    topic='GROUPED_DISPERSION_COMPARISON_TOPIC'
                    kind={'range':'COMPARE_GROUPED_RANGE','iqr':'COMPARE_GROUPED_IQR',
                          'variance':'COMPARE_GROUPED_VARIANCE_SD','sd':'COMPARE_GROUPED_VARIANCE_SD'}[metric]
                if not any(c['exercise_type_code']==kind for c in proposals):add(topic,kind,'statistics.'+metric,pattern)
        if not proposals and has(r'tu phan vi'):
            add('GROUPED_RANGE_IQR_TOPIC',None,'statistics.quartiles',r'tu phan vi')
        if not proposals and has(r'cac so dac trung do muc do phan tan'):
            add('GROUPED_DISPERSION_APPLICATION_TOPIC','MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS',
                'statistics.request_all_measures',r'cac so dac trung do muc do phan tan')
        if not proposals and has(r'hieu so.{0,100}bat ki|hieu so.{0,60}hai'):
            add('GROUPED_RANGE_IQR_TOPIC','CALCULATE_GROUPED_RANGE','statistics.pairwise_difference_bound',r'hieu so')
        if not proposals:
            solution=plain(row.get('solution',{}).get('markdown',''))
            if re.search(r'khoang bien thien|khoang tu phan vi|do lech chuan|phuong sai',solution):
                add('GROUPED_DISPERSION_APPLICATION_TOPIC','CONCLUDE_FROM_GROUPED_DISPERSION',
                    'statistics.source_solution_measures',r'khoang bien thien|khoang tu phan vi|do lech chuan|phuong sai',
                    solution,'solution.markdown')
    elif chapter == 'PROBABILITY_CHAPTER':
        solution=plain(row.get('solution',{}).get('markdown',''))
        named_bayes=r'(?:ap dung|theo|su dung).{0,25}cong thuc bayes'
        named_total=r'(?:ap dung|theo|su dung).{0,25}cong thuc (?:tinh )?xac suat toan phan'
        if re.search(named_bayes,solution):
            add('TOTAL_PROBABILITY_BAYES_TOPIC','BAYES_POSTERIOR','probability.source_solution_bayes',
                named_bayes,solution,'solution.markdown')
        elif re.search(named_total,solution):
            add('TOTAL_PROBABILITY_BAYES_TOPIC','TOTAL_PROBABILITY','probability.source_solution_total',
                named_total,solution,'solution.markdown')
        elif has(r'so do (?:hinh )?cay|hinh cay'):
            add('PROBABILITY_TREE_TOPIC','TREE_OR_TOTAL_PROBABILITY','probability.tree',r'so do (?:hinh )?cay|hinh cay')
        elif has(r'bayes'):
            add('TOTAL_PROBABILITY_BAYES_TOPIC','BAYES_POSTERIOR','probability.named_bayes',r'bayes')
        elif has(r'xac suat toan phan'):
            add('TOTAL_PROBABILITY_BAYES_TOPIC','TOTAL_PROBABILITY','probability.named_total',r'xac suat toan phan')
        elif has(r'xac suat.{0,120}biet rang|biet rang.{0,220}xac suat|xac suat co dieu kien|\bp\s*\([^)]*(?:\||\\mid)'):
            add('CONDITIONAL_PROBABILITY_TOPIC','CONDITIONAL_PROBABILITY_DIRECT',
                'probability.conditional_request',r'xac suat|\bp\s*\(')
    return proposals


def label_record(row, contexts, taxonomy, printed=None, labels_from='source-and-rules'):
    spans = row.get('question', {}).get('source_spans', [])
    page_numbers = sorted({s['page_number'] for s in spans})
    source = [contexts[p] for p in page_numbers if p in contexts]
    existing_code = chapter_code(row.get('chapter_title', ''))
    codes = {s['code'] for s in source}
    if existing_code:codes.add(existing_code)
    if printed and printed.get('chapter',{}).get('canonical_code'):
        codes.add(printed['chapter']['canonical_code'])
    code = next(iter(codes)) if len(codes)==1 else None
    chapter = None
    if code in taxonomy['chapters']:
        chapter = {'code':code,'name':taxonomy['chapters'][code]['name'],
                   'basis':'SOURCE_HEADER' if source else 'EXISTING_CHAPTER_TITLE'}
    proposed = propose(row,code) if chapter and labels_from=='source-and-rules' else []
    candidates,unsupported = [],False
    for c in proposed:
        topic = taxonomy['topics'].get(c['lesson_code'])
        if not topic or topic['chapter_code'] != code:
            unsupported = True
            continue
        c['lesson'] = {'code':topic['code'],'name':topic['name']}
        c['exercise_type'] = None
        if c['exercise_type_code']:
            kind = taxonomy['problem_types'].get(c['exercise_type_code'])
            if not kind or kind['topic_code'] != topic['code']:
                unsupported = True
                c['exercise_type_code'] = None
            else:c['exercise_type'] = {'code':kind['code'],'name':kind['name']}
        candidates.append(c)
    lessons = {c['lesson_code'] for c in candidates}
    types = {c['exercise_type_code'] for c in candidates if c['exercise_type_code']}
    flags = []
    if unsupported:flags.append('FALLBACK_RULE_NOT_IN_SELECTED_TAXONOMY')
    if len(codes)>1:flags.append('CONFLICTING_SOURCE_CHAPTERS')
    if not chapter:flags.append('CHAPTER_EVIDENCE_MISSING')
    if len(lessons)>1:flags.append('MULTIPLE_LESSON_CANDIDATES')
    if len(types)>1:flags.append('MULTIPLE_EXERCISE_TYPE_CANDIDATES')
    lesson = candidates[0]['lesson'] if len(lessons)==1 else None
    kind = next((c['exercise_type'] for c in candidates if c['exercise_type']),None) if lesson and len(types)==1 else None
    if chapter and not candidates:flags.append('NO_FINER_LABEL_EVIDENCE')
    if not row.get('question',{}).get('markdown','').strip():flags.append('EMPTY_QUESTION_TEXT')
    method = {'schema_version':VERSION,'chapter':chapter,'lesson':lesson,'exercise_type':kind,
            'label_path':[v['name'] for v in [chapter,lesson,kind] if v],
            'status':'DRAFT_CANDIDATE' if candidates else 'CHAPTER_ONLY' if chapter else 'UNCLASSIFIED',
            'classification_method':'SOURCE_CHAPTER_AND_LOCAL_TEXT_RULES','review_required':True,
            'source_header_evidence':list({(s['evidence']['page_number'],s['evidence']['text']):s['evidence'] for s in source}.values()),
            'candidates':candidates,'flags':flags}
    return apply_document_labels(method,printed)


def run(input_path, pages_path, output, taxonomy_root=DEFAULT_TAXONOMY, labels_from='source-and-rules', source_pdf=None):
    if labels_from not in {'source','source-and-rules'}:raise ValueError('INVALID_LABEL_POLICY')
    input_path,pages_path,output = map(lambda p:Path(p).resolve(),(input_path,pages_path,output))
    if output == input_path.parent:raise ValueError('USE_SEPARATE_OUTPUT_TO_PRESERVE_ORIGINAL_EXPORT')
    digest,pages_digest = file_hash(input_path),file_hash(pages_path)
    rows,pages = read_json(input_path),read_json(pages_path)
    if not rows:raise ValueError('NO_QUESTIONS')
    if len({r['question_id'] for r in rows})!=len(rows):raise ValueError('DUPLICATE_QUESTION_IDS')
    if any('method' in r for r in rows):raise ValueError('METHOD_FIELD_ALREADY_EXISTS')
    if len({r['source']['sha256'] for r in rows})!=1:raise ValueError('MIXED_SOURCE_EXPORTS')
    identity_path = pages_path.parent/'run-identity.json'
    if identity_path.is_file():
        expected = read_json(identity_path).get('input_sha256')
        if expected and expected != rows[0]['source']['sha256']:raise ValueError('PAGES_EXPORT_SOURCE_HASH_MISMATCH')
    taxonomy = load_taxonomy(taxonomy_root)
    contexts = page_chapters(pages)
    kinds = {}
    if source_pdf:
        source_pdf = Path(source_pdf).resolve()
        if file_hash(source_pdf)!=rows[0]['source']['sha256']:raise ValueError('ORIGINAL_PDF_HASH_MISMATCH')
        printed,catalog,kinds = native_document_contexts(rows,source_pdf,taxonomy,chapter_code)
    else:printed,catalog = document_contexts(rows,pages,taxonomy,chapter_code)
    labeled,overlay = [],[]
    for row in rows:
        kind = kinds.get(row['question_id'],'EXERCISE')
        method = label_record(row,contexts,taxonomy,printed.get(row['question_id']),
                              'source' if kind!='EXERCISE' else labels_from)
        method['record_kind'] = kind
        if kind!='EXERCISE':
            method['flags'].append(kind)
            method['status'] = 'SOURCE_HEADING_RECORD'
        inferred = method.get('inference_candidates',method['candidates'])
        types = [method['exercise_type']] if method['exercise_type'] else []
        types.extend(c['exercise_type'] for c in inferred if c.get('exercise_type'))
        method['exercise_type_candidates'] = list({t['code']:t for t in types}.values())
        if kind=='EXERCISE' and not method['exercise_type_candidates']:
            method['flags'].append('EXERCISE_TYPE_EVIDENCE_MISSING')
        elif kind=='EXERCISE' and not method['exercise_type']:
            method['flags'].append('EXERCISE_TYPE_CANDIDATES_REQUIRE_REVIEW')
        normalized = normalize_record(dict(row,method=method))
        labeled.append(normalized)
        overlay.append({'question_id':row['question_id'],'collection_number':row['collection_number'],'method':normalized['method']})
    validation = validate_records(labeled)
    catalog['labels'] = [dict(level=item['level'],**normalize_label({k:v for k,v in item.items() if k!='level'},'source'))
                         for item in catalog['labels']]
    output.mkdir(parents=True,exist_ok=True)
    full = output/'content.method.pretty.json'
    write_json(full,labeled)
    write_jsonl(output/'methods.jsonl',overlay)
    write_json(output/'methods.pretty.json',overlay)
    write_json(output/'document-taxonomy.json',catalog)
    write_json(output/'schema-validation.json',validation)
    stats = {'schema_version':'method-labeling-report/v1.0.0','pipeline_version':VERSION,
        'metadata_schema_version':METADATA_VERSION,'method_schema_version':METHOD_VERSION,'questions':len(rows),
        'chapters':dict(Counter(m['method']['chapter']['name'] if m['method']['chapter'] else 'UNCLASSIFIED' for m in overlay)),
        'with_chapter':sum(bool(m['method']['chapter']) for m in overlay),
        'with_lesson':sum(bool(m['method']['lesson']) for m in overlay),
        'with_exercise_type':sum(bool(m['method']['exercise_type']) for m in overlay),
        'with_printed_document_labels':sum(any(m['method']['document_labels'][role] for role in
                                             ('chapter','lesson','exercise_type')) for m in overlay),
        'with_exercise_type_candidates':sum(bool(m['method']['exercise_type_candidates']) for m in overlay),
        'heading_records':len(kinds),'exercise_records':len(rows)-len(kinds),
        'label_policy':labels_from,'document_label_count':len(catalog['labels']),
        'statuses':dict(Counter(m['method']['status'] for m in overlay)),
        'flags':dict(Counter(f for m in overlay for f in m['method']['flags'])),
        'lessons':dict(Counter(m['method']['lesson']['name'] for m in overlay if m['method']['lesson'])),
        'input_path':str(input_path),'input_sha256':digest,'pages_sha256':pages_digest,
        'processed_pages':len(pages),'source_pdf_page_count':rows[0]['source'].get('page_count'),
        'source_artifacts_root':str(input_path.parent),'rules_sha256':file_hash(Path(__file__)),
        'verified_source_pdf':str(source_pdf) if source_pdf else None,
        'source_heading_rules_sha256':file_hash(Path(__file__).with_name('source_method_labels.py')),
        'taxonomy_source':taxonomy['source'],'taxonomy_hashes':taxonomy['identity'],
        'taxonomy_scope':'CANONICAL_RULE_FALLBACK_ONLY_DOCUMENT_LABELS_HAVE_THEIR_OWN_SCOPE',
        'output':str(full),'ocr_calls':0,'model_calls':0,'academic_review':'PENDING',
        'source_transcription_modified':False}
    if file_hash(input_path)!=digest or file_hash(pages_path)!=pages_digest:raise ValueError('SOURCE_EXPORT_CHANGED_DURING_LABELING')
    write_json(output/'method-report.json',stats)
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--pages',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--taxonomy-root',type=Path,default=DEFAULT_TAXONOMY)
    parser.add_argument('--labels-from',choices=['source','source-and-rules'],default='source-and-rules')
    parser.add_argument('--source-pdf',type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.input,args.pages,args.output,args.taxonomy_root,args.labels_from,args.source_pdf),ensure_ascii=False,indent=2))
