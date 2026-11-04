"""Repair split option rows only when source cells establish ownership."""
from statistics import median
import re


def meaningful(text):
    return bool(re.search(r'[^\s.,;:]',text))


def recover(rows,formulas,owned,insertions):
    anchors=[];label_keys=set()
    for row in rows:
        for match in row['labels']:
            gs=[g for g in row['glyphs'] if match.start()<=g['offset']<match.end()]
            if not gs:return None
            anchors.append({'label':match[0][0],'x':min(g['bbox'][0] for g in gs),
                            'y':median(g['bbox'][3] for g in gs),'top':min(g['bbox'][1] for g in gs),
                            'size':median(g['size'] for g in gs)})
            label_keys.update(g['key'] for g in gs)
    if len(anchors)!=4 or {a['label'] for a in anchors}!=set('ABCD'):return None
    size=median(a['size'] for a in anchors);bands=[]
    for anchor in sorted(anchors,key=lambda a:(a['y'],a['x'])):
        if not bands or abs(anchor['y']-bands[-1][0]['y'])>size*.65:bands.append([])
        bands[-1].append(anchor)
    for band in bands:band.sort(key=lambda a:a['x'])
    def owner(g):
        x=(g['bbox'][0]+g['bbox'][2])/2;y=(g['bbox'][1]+g['bbox'][3])/2
        if y<min(a['top'] for a in bands[0])-size*1.25:return None
        for i,band in enumerate(bands):
            bottom=(band[0]['y']+bands[i+1][0]['top'])/2 if i+1<len(bands) else band[0]['y']+size*2
            if y>bottom:continue
            candidates=[a for a in band if x>=a['x']-size*.5]
            return candidates[-1]['label'] if candidates else None
        return None
    gs={g['key']:g for row in rows for g in row['glyphs']};formula_owner={}
    for formula in formulas:
        owners={owner(gs[k]) for k in formula['source_glyph_keys']}
        if len(owners)!=1:return None
        for k in formula['source_glyph_keys']:formula_owner[k]=next(iter(owners))
    buckets={k:[] for k in [None,*'ABCD']}
    for row in rows:
        pieces={k:[] for k in buckets};last=None;by_offset={g['offset']:g for g in row['glyphs']}
        for offset,char in enumerate(row['text']):
            g=by_offset.get(offset)
            if g:
                if g['key'] in label_keys:continue
                last=formula_owner.get(g['key'],owner(g))
                if g['key'] in insertions:pieces[last].append(insertions[g['key']])
                if g['key'] not in owned:pieces[last].append(g['text'])
            elif char.isspace() and pieces[last]:pieces[last].append(' ')
        for key,values in pieces.items():
            text=''.join(values).strip()
            if text:buckets[key].append(text)
    choices=[{'label':label,'markdown':'\n'.join(buckets[label]).strip()} for label in 'ABCD']
    if not all(meaningful(c['markdown']) for c in choices):return None
    return {'markdown':'\n'.join(buckets[None]).strip(),'choices':choices}
