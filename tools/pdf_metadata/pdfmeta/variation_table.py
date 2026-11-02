"""Source-pixel structure for bounded variation tables; arrows are not OCR text."""
from __future__ import annotations

from collections import Counter
import re
from statistics import median

from PIL import Image,ImageFilter
import sympy as sp

from .safe_math import UnsupportedMath, assignment, parse_expression
from .sign_table import bounds, clusters, components, scalar, symbol, unstyle
from .sign_table import check as check_signs
from .math_value import record as value_record,expression as value_expression,compare as value_compare


VERSION='raster-variation-table/v1'


def geometry(image):
    gray=image.convert('L');w,h=gray.size
    if w*h>2_000_000 or w<80 or h<30:
        raise UnsupportedMath('VARIATION_RASTER_SIZE_UNSUPPORTED')
    ink={(x,y) for y in range(h) for x in range(w) if gray.getpixel((x,y))<180}
    all_hh=clusters([y for y in range(h) if sum((x,y) in ink for x in range(w))>.4*w])
    all_vv=clusters([x for x in range(w) if sum((x,y) in ink for y in range(h))>.6*h])
    hh=[a for a in all_hh if median(a)>.1*h and median(a)<.9*h]
    vv=[a for a in all_vv if median(a)>.04*w and median(a)<.96*w]
    if not 1<=len(hh)<=2 or not 1<=len(vv)<=3:
        raise UnsupportedMath('VARIATION_SEPARATOR_COUNT_UNSUPPORTED')
    divider=median(vv[0]);start=max(vv[0])+2
    blocked=[]
    end=w
    if len(vv)>=2:
        left,right=max(vv[0])+1,min(vv[1])
        density=sum(left<x<right for x,y in ink)/max(1,(right-left)*h)
        if density<.12 or right-left<.05*w:
            raise UnsupportedMath('VARIATION_MULTIPLE_COLUMNS_AMBIGUOUS')
        blocked.append({'bbox_pixel':[left,0,right,h],'kind':'HATCHED_SOURCE_REGION_NOT_A_NUMERIC_INTERVAL'})
        start=max(vv[1])+2
    if len(vv)==3:
        left=max(vv[2])+1
        density=sum(x>left for x,y in ink)/max(1,(w-left)*h)
        if density<.12:
            raise UnsupportedMath('VARIATION_RIGHT_COLUMN_AMBIGUOUS')
        blocked.append({'bbox_pixel':[left,0,w,h],'kind':'HATCHED_SOURCE_REGION_NOT_A_NUMERIC_INTERVAL'})
        end=min(vv[2])-2
    # Remove source rules/borders from glyph components without deleting them
    # from the source image. Otherwise the frame becomes a giant header glyph.
    rule_y={y for a in all_hh for y in range(min(a)-1,max(a)+2)}
    rule_x={x for a in all_vv for x in range(min(a)-1,max(a)+2)}
    ink={p for p in ink if p[0] not in rule_x and p[1] not in rule_y}
    lines=[int(median(a)) for a in hh]
    ranges=[(0,min(hh[0])-1)]
    if len(hh)==2:
        ranges += [(max(hh[0])+2,min(hh[1])-1),(max(hh[1])+2,h)]
    else:
        ranges += [(max(hh[0])+2,h)]
    rows=[]
    for top,bottom in ranges:
        data={(x,y) for x,y in ink if start<=x<end and top<y<bottom}
        label=[(x,y) for x,y in ink if x<divider-2 and top<y<bottom]
        if (top,bottom)==ranges[-1]:
            # Raster/JPEG gaps may break a thin arrow shaft from its head.
            # Join at most one-pixel gaps; record the preprocessing in output.
            mask=Image.new('L',(w,h));mask.putdata([255 if (x,y) in data else 0 for y in range(h) for x in range(w)])
            mask=mask.filter(ImageFilter.MaxFilter(3))
            data={(x,y) for y in range(max(0,top),min(h,bottom)) for x in range(start,end) if mask.getpixel((x,y))}
        cc=components(data)
        rows.append({'components':cc,'label_box':bounds(label) if label else None,'range':[top,bottom]})
    return {'rows':rows,'blocked_regions':blocked,'data_start':start,'size':[w,h]}


def group_header(boxes):
    boxes=sorted(boxes,key=lambda b:b[0])
    if not boxes:
        raise UnsupportedMath('VARIATION_HEADER_EMPTY')
    gap=max(b[3]-b[1] for b in boxes)*1.35
    grouped=[]
    for box in boxes:
        if grouped and box[0]-grouped[-1][2]<gap:
            a=grouped[-1];grouped[-1]=[a[0],min(a[1],box[1]),box[2],max(a[3],box[3])]
        else:
            grouped.append(box)
    if not 2<=len(grouped)<=8:
        raise UnsupportedMath('VARIATION_BOUNDARY_COUNT_UNSUPPORTED')
    return grouped


def boundary(latex):
    text=unstyle(latex).replace(' ','')
    if text in {r'+\infty',r'\infty','+∞','∞'}:
        return '+inf'
    if text in {r'-\infty','-∞','−∞'}:
        return '-inf'
    return value_record(text)['canonical_expression']


def number(value):
    return value_expression(value)


def arrow(points):
    box=bounds(points);width,height=box[2]-box[0],box[3]-box[1]
    if width<12 or height<8:
        raise UnsupportedMath('VARIATION_ARROW_TOO_SMALL')
    columns={}
    for x,y in points:
        columns.setdefault(x,[]).append(y)
    xy=[(x,median(ys)) for x,ys in sorted(columns.items())]
    # Require a monotone diagonal shaft; compact numerals cannot become arrows.
    if len(xy)<width*.75:
        raise UnsupportedMath('VARIATION_ARROW_SHAFT_DISCONNECTED')
    mean_x=sum(x for x,y in xy)/len(xy);mean_y=sum(y for x,y in xy)/len(xy)
    slope=sum((x-mean_x)*(y-mean_y) for x,y in xy)/sum((x-mean_x)**2 for x,y in xy)
    residual=sum(abs(y-(mean_y+slope*(x-mean_x))) for x,y in xy)/len(xy)
    if abs(slope)<.12 or abs(slope)>4 or residual>max(2,height*.08):
        raise UnsupportedMath('VARIATION_ARROW_DIRECTION_AMBIGUOUS')
    # A visible arrowhead must be at the right endpoint, wider than the shaft.
    ordered=sorted(columns)
    right=ordered[max(0,len(ordered)-max(4,int(width*.12))):]
    middle=ordered[len(ordered)//3:2*len(ordered)//3]
    thickness=lambda xs:max(max(columns[x])-min(columns[x])+1 for x in xs)
    if thickness(right)<max(4,thickness(middle)*1.6):
        raise UnsupportedMath('VARIATION_ARROWHEAD_NOT_AT_RIGHT_ENDPOINT')
    return {'direction':'INCREASING' if slope<0 else 'DECREASING','bbox_pixel':box,
            'slope_image_coordinates':round(slope,5),'mean_residual_pixels':round(residual,3)}


def structure(image,recognize,*,boundary_reader=None,label_reader=None):
    geo=geometry(image)
    w,h=image.size
    def read(box):
        if not box:
            raise UnsupportedMath('VARIATION_ROW_LABEL_MISSING')
        return recognize(image.crop((max(0,box[0]-3),max(0,box[1]-3),min(w,box[2]+3),min(h,box[3]+3))))
    def read_boundary(box):
        raw=read(box)
        try:
            value=boundary(raw)
        except UnsupportedMath:
            value=None
        ocr_value=value
        font=None
        if boundary_reader:
            try:
                font=boundary_reader(image.crop(tuple(box)))
            except UnsupportedMath:
                pass
        if font:
            alternative=boundary(font['text'])
            if value is not None and value!=alternative:
                raise UnsupportedMath('VARIATION_OCR_FONT_BOUNDARY_CONFLICT')
            value=alternative
        if value is None:
            raise UnsupportedMath('VARIATION_BOUNDARY_UNREADABLE')
        return value,{'ocr_latex_raw':raw,'font_template':font,
                      'basis':'OCR_AND_FONT_AGREE' if font and ocr_value==value else 'UNVERIFIED_OCR_OR_FONT_CANDIDATE'}
    points=[]
    for box in group_header([bounds(c) for c in geo['rows'][0]['components']]):
        value,evidence=read_boundary(box)
        points.append({'value':value,'math_value':value_record(value),'recognition_evidence':evidence,'bbox_pixel':box,'x_pixel':(box[0]+box[2])/2})
    order=[value_compare(a['value'],b['value']) for a,b in zip(points,points[1:])]
    if any(o in {'EQ','GT'} for o in order):
        raise UnsupportedMath('VARIATION_BOUNDARIES_NOT_INCREASING')
    axis_raw=read(geo['rows'][0]['label_box']);axis=unstyle(axis_raw)
    axis_template=None
    if not re.fullmatch('[A-Za-z]',axis) and label_reader:
        axis_template=label_reader(image.crop(tuple(geo['rows'][0]['label_box'])))
        axis=axis_template['text']
    if not re.fullmatch('[A-Za-z]',axis):
        raise UnsupportedMath('VARIATION_AXIS_LABEL_AMBIGUOUS')
    label_raw=read(geo['rows'][-1]['label_box']);label=unstyle(label_raw)
    function_template=None
    try:
        parsed=assignment(label+'=0')
    except UnsupportedMath:
        if not label_reader:
            raise
        function_template=label_reader(image.crop(tuple(geo['rows'][-1]['label_box'])))
        label=function_template['text']
        parsed=assignment(label+'=0')
    if parsed['derivative_order'] or parsed['variable'] not in {None,axis}:
        raise UnsupportedMath('VARIATION_FUNCTION_LABEL_AMBIGUOUS')
    derivative_label=None
    if len(geo['rows'])==3:
        derivative_label=read(geo['rows'][1]['label_box'])
        dp=assignment(unstyle(derivative_label)+'=0')
        if dp['label']!=parsed['label'] or dp['derivative_order']!=1 or dp['variable'] not in {None,axis}:
            raise UnsupportedMath('VARIATION_DERIVATIVE_LABEL_MISMATCH')
    intervals=[{'left':a['value'],'right':b['value']} for a,b in zip(points,points[1:])]
    critical=[]
    for component in geo['rows'][-1]['components']:
        box=bounds(component);center=(box[0]+box[2])/2
        # Long diagonal components are source arrows. Other cells remain values.
        if box[2]-box[0]>.25*(points[-1]['x_pixel']-points[0]['x_pixel']) or (box[2]-box[0]>35 and box[3]-box[1]>20):
            mark=arrow(component)
            owner=next((i for i,(a,b) in enumerate(zip(points,points[1:])) if a['x_pixel']<=center<=b['x_pixel']),None)
            if owner is None or 'direction' in intervals[owner]:
                raise UnsupportedMath('VARIATION_ARROW_INTERVAL_AMBIGUOUS')
            intervals[owner].update(mark)
        else:
            near=next((p for p in points if abs(center-p['x_pixel'])<max(8,(box[2]-box[0])*.8)),None)
            if near is None:
                raise UnsupportedMath('VARIATION_VALUE_POSITION_UNSUPPORTED')
            critical.append({'at':near['value'],'component':component})
    # Merge adjacent digits around the same critical point, without fabricating value.
    values=[]
    for at in dict.fromkeys(v['at'] for v in critical):
        parts=[p for v in critical if v['at']==at for p in v['component']]
        box=bounds(parts);value,evidence=read_boundary(box)
        values.append({'at':at,'value':value,'math_value':value_record(value),'recognition_evidence':evidence,'bbox_pixel':box})
    if any('direction' not in i for i in intervals):
        raise UnsupportedMath('VARIATION_MISSING_ARROW')
    source_points=[]
    if len(geo['rows'])==3:
        for c in geo['rows'][1]['components']:
            box=bounds(c);center=(box[0]+box[2])/2;mark=symbol(c)
            owner=next((i for i,(a,b) in enumerate(zip(points,points[1:])) if a['x_pixel']<center<b['x_pixel'] and abs(center-a['x_pixel'])>max(8,(box[2]-box[0])*.7) and abs(center-b['x_pixel'])>max(8,(box[2]-box[0])*.7)),None)
            if mark in {'+','-'} and owner is not None:
                if 'source_sign' in intervals[owner]:
                    raise UnsupportedMath('VARIATION_DUPLICATE_SIGN')
                intervals[owner].update(source_sign=mark,sign_bbox_pixel=box)
            else:
                near=next((p for p in points if abs(center-p['x_pixel'])<max(8,(box[2]-box[0])*.8)),None)
                raw=read(box)
                if near is None or scalar(raw)!='0':
                    raise UnsupportedMath('VARIATION_SIGN_OR_ZERO_AMBIGUOUS')
                source_points.append({'at':near['value'],'value':'0','bbox_pixel':box,'latex_raw':raw})
        if any('source_sign' not in i for i in intervals):
            raise UnsupportedMath('VARIATION_MISSING_DERIVATIVE_SIGN')
    flags=['SOURCE_TRANSCRIPTION_NOT_VERIFIED']
    if 'UNKNOWN' in order:
        flags.append('SYMBOLIC_BOUNDARY_ORDER_NOT_VERIFIED')
    if axis_template or function_template or any(p['recognition_evidence']['basis']!='OCR_AND_FONT_AGREE' for p in points+values):
        flags.append('FONT_OR_OCR_FALLBACK_REQUIRES_SOURCE_REVIEW')
    if geo['blocked_regions']:
        flags.append('HATCHED_DOMAIN_CONDITION_NOT_DECODED')
    return {'schema_version':'variation-table-candidate/v1','algorithm':VERSION,'axis':axis,'axis_latex_raw':axis_raw,
        'axis_template_evidence':axis_template,
        'function_label':parsed['label'],'row_label_latex':label,'row_label_latex_raw':label_raw,
        'function_template_evidence':function_template,
        'derivative_label_latex_raw':derivative_label,'boundaries':points,'intervals':intervals,
        'arrow_preprocessing':'SOURCE_THRESHOLD_180_ONE_PIXEL_DILATION',
        'point_values':source_points,'function_values':values,'blocked_regions':geo['blocked_regions'],
        'quality_flags':flags,
        'status':'RASTER_AND_OCR_CANDIDATE_NOT_VISUALLY_VERIFIED','academic_review':'PENDING',
        'grading_support':'NOT_ASSESSED','publishable':False}


def check(table,derivative):
    # Source arrows supply a direction; they never inherit signs from formulas.
    intervals=[{**i,'source_sign':'+' if i['direction']=='INCREASING' else '-'} for i in table['intervals']]
    result=check_signs({**table,'intervals':intervals},derivative)
    if result['status']=='NOT_ASSESSED':
        return result
    result['kind']='VARIATION_ARROW_AND_DERIVATIVE_IDENTITY'
    result['source_arrow_sign_agreement']=[{'left':i['left'],'right':i['right'],
        'status':'PASS' if i.get('source_sign',a['source_sign'])==a['source_sign'] else 'FAIL'}
        for i,a in zip(table['intervals'],intervals)]
    if any(f['status']=='FAIL' for f in result['source_arrow_sign_agreement']):
        result['status']='FAIL'
    return result


def check_values(table,base):
    if base['label']!=table['function_label'] or base['derivative_order'] or base['variable'] not in {None,table['axis']}:
        return {'status':'NOT_ASSESSED','reason':'TABLE_VALUE_FUNCTION_MISMATCH'}
    var=sp.Symbol(table['axis']);expr=base['expression']
    if expr.free_symbols-{var} or not expr.is_rational_function(var):
        return {'status':'NOT_ASSESSED','reason':'ONLY_PARAMETER_FREE_RATIONAL_VALUES_SUPPORTED'}
    numerator,denominator=sp.fraction(sp.cancel(expr))
    if max(sp.degree(numerator,var),sp.degree(denominator,var))>8:
        return {'status':'NOT_ASSESSED','reason':'TABLE_VALUE_DEGREE_LIMIT'}
    findings=[]
    for point in table.get('function_values',[]):
        at,expected=number(point['at']),number(point['value'])
        if at.free_symbols or expected.free_symbols:
            return {'status':'NOT_ASSESSED','reason':'SYMBOLIC_VALUE_REQUIRES_ASSUMPTIONS'}
        if at in {sp.oo,-sp.oo}:
            actual=sp.limit(expr,var,at)
        elif any(d.subs(var,at)==0 for d in base['denominators']):
            findings.append({'at':point['at'],'status':'FAIL','reason':'VALUE_AT_SOURCE_EXCLUDED_POINT'})
            continue
        else:
            actual=expr.subs(var,at)
        findings.append({'at':point['at'],'source_value':point['value'],'expected_value':str(actual),
                         'status':'PASS' if actual==expected else 'FAIL'})
    return {'status':'FAIL' if any(f['status']=='FAIL' for f in findings) else 'PASS' if findings else 'NOT_ASSESSED',
            'kind':'FUNCTION_VALUES_FROM_SOURCE_FORMULA','findings':findings,
            'scope':'CONDITIONAL_ON_TRANSCRIPTION_NOT_SOURCE_OR_ANSWER_APPROVAL'}
