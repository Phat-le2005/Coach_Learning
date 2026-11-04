"""Artifact integrity and source-glyph comparisons, never inferred accuracy."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from ...storage import read_json,file_hash,write_json


def records(root):
    return {q['question_id']:q for p in (root/'records').glob('*.json') if (q:=read_json(p))}


def assets(root,qs):
    errors=[];seen={}
    for q in qs.values():
        if q.get('publishable') or q.get('academic_review')!='PENDING' or q.get('grading_support')!='NOT_ASSESSED':errors.append('UNEXPECTED_GRADING_APPROVAL')
        for f in q['formula_candidates']:
            seen[f['asset_path']]=f['asset_sha256']
        for t in q.get('tables',[]):
            seen[t['asset_path']]=t['asset_sha256']
            for c in t['cells']:
                if c.get('asset_path'):seen[c['asset_path']]=c['asset_sha256']
        for f in q.get('figures',[]):seen[f['asset_path']]=f['asset_sha256']
        for part in q['parts'].values():
            for f in part['fragments']:seen[f['source_asset']]=f['source_asset_sha256']
            for path in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',part['markdown']):
                if not (root/path).is_file():errors.append('MISSING_MARKDOWN_ASSET:'+path)
        for role in q['parts']:
            for pn in {f['page_number'] for f in q['formula_candidates'] if f['role']==role}:
                math={k for f in q['formula_candidates'] if f['role']==role and f['page_number']==pn for k in f['source_glyph_keys']}
                table={k for t in q.get('tables',[]) if t['role']==role and t['page_number']==pn for k in t['source_glyph_keys']}
                if math & table:errors.append('TABLE_MATH_OVERLAP:'+q['question_id'])
    for path,sha in seen.items():
        p=root/path
        if not p.is_file() or file_hash(p)!=sha:errors.append('ASSET_HASH_MISMATCH:'+path)
    return {'referenced_images':len(seen),'errors':errors}


def compare(v1,v2):
    counts=Counter();details=[]
    for qid,old in v1.items():
        if qid not in v2:counts['MISSING_V2_ITEM']+=1;continue
        new=v2[qid]
        for f in old['formula_candidates']:
            key=(f['role'],f['page_number']);original=set(f['source_glyph_keys'])
            fs=[n for n in new['formula_candidates'] if (n['role'],n['page_number'])==key]
            tables={k for t in new.get('tables',[]) if (t['role'],t['page_number'])==key for k in t['source_glyph_keys']}
            shown={k for n in fs if n['display_latex'] for k in n['source_glyph_keys']}
            held={k for n in fs if not n['display_latex'] for k in n['source_glyph_keys']}
            if original and original<=tables:status='RECLASSIFIED_AS_TABLE'
            elif original and original<=shown:status='FULL_GLYPH_COVERAGE_DISPLAY_DRAFT'
            elif original and original<=held:status='FULL_GLYPH_COVERAGE_IMAGE_FALLBACK'
            elif original and original<=shown|held|tables:status='SPLIT_ACROSS_TYPED_REGIONS'
            elif original & (shown|held|tables):status='PARTIAL_GLYPH_COVERAGE_REQUIRES_AUDIT'
            else:status='NO_V2_FORMULA_OR_TABLE_OWNERSHIP_REQUIRES_AUDIT'
            origin='V1_DISPLAYED' if f['display_latex'] else 'V1_HELD'
            counts[origin+':'+status]+=1
            details.append({'question_id':qid,'number':old['collection_number'],'formula_id':f['formula_id'],'origin':origin,
                'status':status,'old_glyphs':len(original),'new_glyphs_covered':len(original & (shown|held|tables))})
    return {'method':'ORIGINAL_SOURCE_GLYPH_KEYS_NOT_REGION_COUNT_OR_ACCURACY','counts':dict(counts),'regions':details}


def run(args):
    root=Path.cwd();baseline=read_json(args.baseline)
    changed=[p for p,sha in baseline.items() if not (root/p).is_file() or file_hash(root/p)!=sha]
    old,new=records(args.v1),records(args.v2);asset_audit=assets(args.v2,new)
    result={'v1_files_checked':len(baseline),'v1_files_changed':changed,'v1_items':len(old),'v2_items':len(new),
        'same_item_ids':set(old)==set(new),'assets':asset_audit,'comparison':compare(old,new),
        'grading_ready':False,'mathematical_accuracy_established':False}
    write_json(args.v2/'comparison-v1-v2.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='comparison'},ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['v1','v2','baseline']:p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
