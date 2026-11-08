"""Frozen public metadata contract, independent of extraction/labeling strategy."""
from __future__ import annotations

import argparse
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .storage import file_hash, read_json, write_json


METADATA_VERSION = 'pdf-question-metadata/v1.0.0'
METHOD_VERSION = 'question-method/v1.0.0'
SCHEMA_PATH = Path(__file__).parents[1] / 'schemas/question-metadata.v1.schema.json'


def fixed(value, defaults):
    value = value or {}
    if not isinstance(value,dict):raise ValueError('EXPECTED_METADATA_OBJECT')
    result = {k:deepcopy(value.get(k,v)) for k,v in defaults.items()}
    extras = deepcopy(value.get('extensions') or {})
    if not isinstance(extras,dict):raise ValueError('EXPECTED_EXTENSIONS_OBJECT')
    extras.update({k:deepcopy(v) for k,v in value.items() if k not in defaults and k!='extensions'})
    result['extensions'] = extras
    return result


def evidence(value):
    if value is None:return []
    if isinstance(value,dict):value = [value]
    if not isinstance(value,list):raise ValueError('EXPECTED_EVIDENCE_ARRAY')
    return [fixed(v,{'basis':None,'field':None,'page_number':None,'bbox':None,'block_ids':[],
                     'text':None,'normalized_match':None,'source_reference':None}) for v in value]


def label(value, origin='unknown'):
    if not value:return None
    result = fixed(value,{'code':None,'name':None,'canonical_code':None,'parent_code':None,
                         'source_number':None,'source_label':None,'origin':origin,'basis':None,'evidence':[]})
    if result['source_number'] is not None:result['source_number'] = str(result['source_number'])
    basis = result['basis'] or ''
    if basis=='PRINTED_DOCUMENT_HEADING' or basis.startswith(('SOURCE_','EXISTING_CHAPTER')):
        result['origin'] = 'source'
    elif 'RULE' in basis:result['origin'] = 'inferred'
    result['evidence'] = evidence(result['evidence'])
    return result


def candidate(value):
    result = fixed(value,{'lesson_code':None,'exercise_type_code':None,'lesson':None,
                         'exercise_type':None,'rule':None,'evidence':[]})
    result['lesson'] = label(result['lesson'],'inferred')
    result['exercise_type'] = label(result['exercise_type'],'inferred')
    result['evidence'] = evidence(result['evidence'])
    return result


def normalize_method(value):
    value = value or {}
    previous = value.get('schema_version')
    pipeline = value.get('pipeline_version')
    if pipeline is None and previous and previous!=METHOD_VERSION:pipeline = previous
    result = fixed(value,{'schema_version':METHOD_VERSION,'pipeline_version':pipeline,
        'record_kind':'EXERCISE','chapter':None,'lesson':None,'exercise_type':None,'label_path':[],
        'status':'UNCLASSIFIED','classification_method':None,'review_required':True,
        'source_header_evidence':[],'document_labels':{},'candidates':[],
        'inference_candidates':[],'exercise_type_candidates':[],'flags':[]})
    result['schema_version'] = METHOD_VERSION
    result['pipeline_version'] = pipeline
    candidates = [candidate(c) for c in result['candidates']]
    inferred = [candidate(c) for c in result['inference_candidates']]
    for role in ['chapter','lesson','exercise_type']:
        code = (result[role] or {}).get('code')
        hint = 'inferred' if any((c.get(role) or {}).get('code')==code for c in candidates+inferred) else 'unknown'
        result[role] = label(result[role],hint)
    printed = fixed(result['document_labels'],{'chapter':None,'lesson':None,'exercise_type':None})
    for role in ['chapter','lesson','exercise_type']:printed[role] = label(printed[role],'source')
    result['document_labels'] = printed
    result['source_header_evidence'] = evidence(result['source_header_evidence'])
    result['candidates'],result['inference_candidates'] = candidates,inferred
    result['exercise_type_candidates'] = [label(v,'inferred') for v in result['exercise_type_candidates'] if v]
    if not result['exercise_type_candidates']:
        kinds = ([result['exercise_type']] if result['exercise_type'] else [])
        kinds += [c['exercise_type'] for c in candidates+inferred if c['exercise_type']]
        result['exercise_type_candidates'] = list({k['code']:k for k in kinds}.values())
    return result


def heading(value):
    if not value:return None
    result = fixed(value,{'kind':None,'label':None,'number':None,'title':None,'page_number':None,
                         'bbox':None,'block_ids':[],'method':None,'source_verified':None})
    if result['number'] is not None:result['number'] = str(result['number'])
    return result


def part(value):
    result = fixed(value,{'markdown':'','choices':[],'source_spans':[],'raw_text_lossy':None,'fragments':[]})
    result['source_spans'] = [fixed(s,{'page_number':None,'bbox':None,'block_ids':[],
                                     'column':None,'layout_method':None}) for s in result['source_spans']]
    fragments = []
    for value in result['fragments']:
        f = fixed(value,{'page_number':None,'bbox':None,'source_asset':None,'source_asset_sha256':None,
                         'markdown':'','choices':[],'blocks':[],'coverage':{},'source_errors':[],
                         'visual_flags':[],'status':None,'quality_audit':None})
        f['blocks'] = [fixed(b,{'kind':None,'bbox':None,'markdown':'','asset_id':None}) for b in f['blocks']]
        f['coverage'] = fixed(f['coverage'],{'method':None,'complete_formula_recall_established':None})
        fragments.append(f)
    result['fragments'] = fragments
    return result


def normalize_record(value):
    result = fixed(value,{'schema_version':METADATA_VERSION,'collection_number':None,'question_id':None,
        'chapter_title':None,'source_number':None,'source':{},'question':{},'solution':{},'answer':{},
        'tables':[],'visual_assets':[],'academic_review':'PENDING','grading_support':'NOT_ASSESSED',
        'publishable':False,'topic_context':{},'method':{}})
    if result['schema_version']!=METADATA_VERSION:
        result['extensions']['previous_schema_version'] = result['schema_version']
    result['schema_version'] = METADATA_VERSION
    result['source'] = fixed(result['source'],{'name':None,'catalog_label':None,'sha256':None,'page_count':None,
        'coordinate_unit':None,'coordinate_origin':None,'coordinate_reference':None})
    if isinstance(result['source_number'],str):
        if result['source_number'].isdigit():result['source_number'] = int(result['source_number'])
        else:
            result['extensions']['previous_source_number'] = result['source_number']
            result['source_number'] = None
    for role in ['question','solution','answer']:result[role] = part(result[role])
    result['visual_assets'] = [fixed(a,{'id':None,'kind':None,'path':None,'page_number':None,'bbox':None,
        'sha256':None,'source_sha256':None,'status':None,'review_required':None,'coordinate_reference':None,
        'detector':None,'score':None,'role':None,'question_id':None}) for a in result['visual_assets']]
    context = fixed(result['topic_context'],{'chapter':None,'lesson':None,'topic':None,'exercise_type':None,'section':None})
    for k in ['chapter','lesson','topic','exercise_type','section']:context[k] = heading(context[k])
    result['topic_context'] = context
    result['method'] = normalize_method(result['method'])
    return result


@lru_cache(maxsize=1)
def validator():
    schema = read_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_records(rows):
    failure = next(validator().iter_errors(rows),None)
    if failure is not None:
        path = '/'.join(map(str,failure.absolute_path))
        raise ValueError(f'METADATA_SCHEMA_INVALID at {path}: {failure.message}')
    return {'schema_version':METADATA_VERSION,'records':len(rows),'valid':True,'errors':0}


def project(value, original):
    """Compare source payload while ignoring added defaults and extensions."""
    if isinstance(original,dict):
        return {k:project(value[k] if k in value else value.get('extensions',{})[k],v) for k,v in original.items()}
    if isinstance(original,list):
        if len(value)!=len(original):raise ValueError('SOURCE_ARRAY_LENGTH_CHANGED')
        return [project(v,o) for v,o in zip(value,original)]
    return value


def migrate(input_path, output_path):
    input_path,output_path = Path(input_path).resolve(),Path(output_path).resolve()
    if input_path==output_path:raise ValueError('USE_SEPARATE_OUTPUT_TO_PRESERVE_INPUT')
    before = file_hash(input_path)
    original = read_json(input_path)
    if not isinstance(original,list):raise ValueError('EXPECTED_QUESTION_ARRAY')
    rows = [normalize_record(q) for q in original]
    report = validate_records(rows)
    for old,new in zip(original,rows):
        payload = {k:v for k,v in old.items() if k not in {'method','schema_version','source_number'}}
        if project(new,payload)!=payload:raise ValueError('SOURCE_PAYLOAD_CHANGED')
        for role in ['chapter','lesson','exercise_type']:
            a,b = (old.get('method') or {}).get(role),new['method'][role]
            if a and (a.get('code'),a.get('name'))!=(b['code'],b['name']):raise ValueError('PRIMARY_LABEL_CHANGED')
    if file_hash(input_path)!=before:raise ValueError('INPUT_CHANGED_DURING_MIGRATION')
    write_json(output_path,rows)
    report.update(input=str(input_path),input_sha256=before,output=str(output_path),
                  source_payload_unchanged=True,primary_labels_unchanged=True,
                  method_schema_version=METHOD_VERSION,schema_file_sha256=file_hash(SCHEMA_PATH))
    write_json(output_path.with_suffix('.schema-report.json'),report)
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser(description='Normalize old labeled exports to the frozen metadata schema; no OCR.')
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(migrate(args.input,args.output),ensure_ascii=False,indent=2))
