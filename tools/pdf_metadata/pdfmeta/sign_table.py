"""Bounded two-row raster sign tables. Never infer missing source signs from math."""
from __future__ import annotations

from collections import deque
import re
from statistics import median

from PIL import Image
import sympy as sp

from .safe_math import UnsupportedMath, assignment


VERSION = "raster-sign-table/v1"


def clusters(values, distance=1):
    result = []
    for value in sorted(values):
        if result and value-result[-1][-1] <= distance:
            result[-1].append(value)
        else:
            result.append([value])
    return result


def components(ink):
    todo, result = set(ink), []
    while todo:
        origin = todo.pop()
        queue, points = deque([origin]), [origin]
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                point = x+dx, y+dy
                if point in todo:
                    todo.remove(point)
                    points.append(point)
                    queue.append(point)
        if len(points) >= 3:
            result.append(points)
    return result


def bounds(points):
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points)+1, max(p[1] for p in points)+1]


def symbol(points):
    box = bounds(points)
    w, h = box[2]-box[0], box[3]-box[1]
    if w < 4:
        return "OTHER"
    row = max(sum(y == p[1] for p in points) for y in range(box[1], box[3]))
    column = max(sum(x == p[0] for p in points) for x in range(box[0], box[2]))
    if w >= h*2.5 and len(points)/(w*h) >= .4:
        return "-"
    if .6 <= w/h <= 1.6 and row >= w*.8 and column >= h*.8:
        return "+"
    return "OTHER"


def analyze(image: Image.Image):
    image = image.convert("L")
    w, h = image.size
    if w*h > 2_000_000 or w < 80 or h < 20:
        raise UnsupportedMath("TABLE_RASTER_SIZE_UNSUPPORTED")
    ink = {(x,y) for y in range(h) for x in range(w) if image.getpixel((x,y)) < 180}
    horizontal = clusters([y for y in range(h) if sum((x,y) in ink for x in range(w)) >= .6*w])
    vertical = clusters([x for x in range(w) if sum((x,y) in ink for y in range(h)) >= .6*h])
    if len(horizontal) != 1 or len(vertical) != 1:
        raise UnsupportedMath("ONLY_TWO_ROW_ONE_SEPARATOR_SIGN_TABLE_SUPPORTED")
    hy, vx = horizontal[0], vertical[0]
    y, x = median(hy), median(vx)
    if not .2*h < y < .8*h or not .04*w < x < .4*w:
        raise UnsupportedMath("TABLE_SEPARATOR_GEOMETRY_AMBIGUOUS")
    clean = {(a,b) for a,b in ink if not min(hy)-1 <= b <= max(hy)+1 and not min(vx)-1 <= a <= max(vx)+1}
    axis_ink = [(a,b) for a,b in clean if a < min(vx)-1 and b < min(hy)-1]
    label_ink = [(a,b) for a,b in clean if a < min(vx)-1 and b > max(hy)+1]
    if not axis_ink or not label_ink:
        raise UnsupportedMath("TABLE_ROW_LABEL_IMAGE_MISSING")
    cells = components({(a,b) for a,b in clean if a > max(vx)+1})
    header = sorted([bounds(c) for c in cells if max(p[1] for p in c) < y], key=lambda b:b[0])
    body = sorted([c for c in cells if min(p[1] for p in c) > y], key=lambda c:bounds(c)[0])
    if not header or not body or len(header) > 30 or len(body) > 20:
        raise UnsupportedMath("TABLE_CELL_COUNT_UNSUPPORTED")
    gap = median(b[3]-b[1] for b in header)*.5
    grouped = []
    for b in header:
        if grouped and b[0]-grouped[-1][2] < gap:
            a = grouped[-1]
            grouped[-1] = [a[0], min(a[1],b[1]), b[2], max(a[3],b[3])]
        else:
            grouped.append(b)
    if not 2 <= len(grouped) <= 8:
        raise UnsupportedMath("TABLE_BOUNDARY_COUNT_UNSUPPORTED")
    observations = [{"bbox_pixel": bounds(c), "pixel_symbol": symbol(c)} for c in body]
    # Verify the shape classification at two thresholds too: thin strokes may vanish.
    for observation, component in zip(observations, body):
        if observation["pixel_symbol"] != "OTHER":
            box = observation["bbox_pixel"]
            for threshold in (140, 210):
                pixels = [(a,b) for a,b in component if image.getpixel((a,b)) < threshold]
                if not pixels or symbol(pixels) != observation["pixel_symbol"]:
                    raise UnsupportedMath("TABLE_SIGN_RASTER_THRESHOLD_UNSTABLE")
    return {"header_boxes": grouped, "body": observations,
            "axis_label_box": bounds(axis_ink),
            "row_label_box": bounds(label_ink), "width":w,"height":h}


def unstyle(latex):
    text = re.sub(r"\\(?:mathbf|mathrm|mathit|pmb|boldsymbol)\b", "", latex).strip(" $\n")
    while text.startswith('{') and text.endswith('}'):
        depth = 0
        for index,char in enumerate(text):
            depth += (char=='{')-(char=='}')
            if depth==0:
                break
        if index!=len(text)-1:
            break
        text = text[1:-1].strip()
    return text


def scalar(latex):
    text = unstyle(latex)
    if len(text) > 20 or not re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", text):
        raise UnsupportedMath("TABLE_BOUNDARY_NOT_A_SCALAR")
    value = sp.Rational(text.replace(",", "."))
    if abs(value) > 10**9:
        raise UnsupportedMath("TABLE_BOUNDARY_VALUE_LIMIT")
    return str(value)


def structure(image, recognize):
    """recognize(crop) returns raw OCR; signs come from source pixels only."""
    geometry = analyze(image)
    def read(box):
        w,h = image.size
        padded = [max(0,box[0]-3), max(0,box[1]-3), min(w,box[2]+3), min(h,box[3]+3)]
        return recognize(image.crop(tuple(padded)))
    points = [{"value": scalar(read(box)), "bbox_pixel":box,
               "x_pixel": (box[0]+box[2])/2} for box in geometry["header_boxes"]]
    if any(sp.Rational(a["value"]) >= sp.Rational(b["value"]) for a,b in zip(points,points[1:])):
        raise UnsupportedMath("TABLE_BOUNDARIES_NOT_STRICTLY_INCREASING")
    axis_raw = read(geometry["axis_label_box"])
    axis = unstyle(axis_raw)
    if not re.fullmatch(r"[A-Za-z]", axis):
        raise UnsupportedMath("TABLE_AXIS_LABEL_UNSUPPORTED")
    row_raw = read(geometry["row_label_box"])
    row_label = unstyle(row_raw)
    parsed = assignment(row_label+"=0")
    if parsed["derivative_order"] != 1 or parsed["variable"] not in {None,axis}:
        raise UnsupportedMath("TABLE_ROW_IS_NOT_AN_UNAMBIGUOUS_DERIVATIVE")
    intervals, point_values = {}, []
    for observation in geometry["body"]:
        box = observation["bbox_pixel"]
        center = (box[0]+box[2])/2
        near = next((i for i,p in enumerate(points) if abs(center-p["x_pixel"]) < max(5,(box[2]-box[0])*.7)), None)
        mark = observation["pixel_symbol"]
        if near is not None:
            if mark in {"+","-"} or scalar(read(box)) != "0":
                raise UnsupportedMath("TABLE_POINT_VALUE_UNSUPPORTED")
            point_values.append({"at":points[near]["value"],"value":"0",**observation})
        else:
            interval = next((i for i,(a,b) in enumerate(zip(points,points[1:])) if a["x_pixel"] < center < b["x_pixel"]),None)
            if interval is None or mark not in {"+","-"} or interval in intervals:
                raise UnsupportedMath("TABLE_INTERVAL_SIGN_AMBIGUOUS")
            intervals[interval] = {"left":points[interval]["value"],"right":points[interval+1]["value"],
                                   "source_sign":mark,**observation}
    if set(intervals) != set(range(len(points)-1)):
        raise UnsupportedMath("TABLE_MISSING_INTERVAL_SIGN")
    return {"schema_version":"sign-table-candidate/v1","algorithm":VERSION,"axis":axis,"axis_latex_raw":axis_raw,
            "function_label":parsed["label"],"row_label_latex":row_label,
            "row_label_latex_raw":row_raw,
            "boundaries":points,"intervals":[intervals[i] for i in sorted(intervals)],"point_values":point_values,
            "status":"RASTER_AND_OCR_CANDIDATE_NOT_VISUALLY_VERIFIED",
            "academic_review":"PENDING","grading_support":"NOT_ASSESSED","publishable":False}


def check(table, derivative):
    """Exact rational signs, conditional on source transcription; no sampling proof."""
    if (derivative["label"] != table["function_label"] or derivative["derivative_order"] != 1
            or derivative["variable"] not in {None,table["axis"]}):
        return {"status":"NOT_ASSESSED","reason":"TABLE_FUNCTION_MISMATCH"}
    var = sp.Symbol(table["axis"])
    expr = derivative["expression"]
    if expr.free_symbols - {var} or not expr.is_rational_function(var):
        return {"status":"NOT_ASSESSED","reason":"ONLY_PARAMETER_FREE_RATIONAL_SIGN_CHECK_SUPPORTED"}
    numerator, denominator = sp.fraction(sp.cancel(expr))
    if max(sp.degree(numerator,var),sp.degree(denominator,var)) > 8:
        return {"status":"NOT_ASSESSED","reason":"SIGN_CHECK_DEGREE_LIMIT"}
    # Denominators before cancellation retain source excluded points.
    denominators = [denominator,*derivative["denominators"]]
    if any(d.free_symbols - {var} or not d.is_polynomial(var) or sp.degree(d,var)>8 for d in denominators):
        return {"status":"NOT_ASSESSED","reason":"SOURCE_DENOMINATOR_UNSUPPORTED"}
    zeros = sp.Poly(numerator,var).real_roots() if numerator != 0 else []
    poles = [r for d in denominators for r in sp.Poly(d,var).real_roots()]
    findings = []
    for interval in table["intervals"]:
        from .math_value import expression as endpoint,compare
        left,right = endpoint(interval["left"]),endpoint(interval["right"])
        if left.free_symbols or right.free_symbols or compare(interval['left'],interval['right'])!='LT':
            return {'status':'NOT_ASSESSED','reason':'SYMBOLIC_OR_UNORDERED_TABLE_INTERVAL'}
        try:
            relations=[(compare(interval['left'],sp.sstr(root)),compare(sp.sstr(root),interval['right'])) for root in zeros+poles]
        except UnsupportedMath:
            return {'status':'NOT_ASSESSED','reason':'ROOT_ORDER_NOT_SUPPORTED'}
        if any('UNKNOWN' in r for r in relations):
            return {'status':'NOT_ASSESSED','reason':'ROOT_ORDER_NOT_EXACTLY_ESTABLISHED'}
        if any(a=='LT' and b=='LT' for a,b in relations):
            return {"status":"NOT_ASSESSED","reason":"UNRECORDED_ROOT_OR_POLE_INSIDE_INTERVAL"}
        sample = 0 if left==-sp.oo and right==sp.oo else right-1 if left==-sp.oo else left+1 if right==sp.oo else (left+right)/2
        value = expr.subs(var,sample)
        if value.is_positive is not True and value.is_negative is not True and value.is_zero is not True:
            return {'status':'NOT_ASSESSED','reason':'INTERVAL_SIGN_NOT_EXACTLY_ESTABLISHED'}
        sign = "+" if value.is_positive else "-" if value.is_negative else "0"
        findings.append({"left":interval['left'],"right":interval['right'],"source_sign":interval["source_sign"],
                         "expected_sign":sign,"status":"PASS" if sign==interval["source_sign"] else "FAIL"})
    for point in table["point_values"]:
        from .math_value import expression as endpoint
        at = endpoint(point["at"])
        if at.free_symbols:
            return {'status':'NOT_ASSESSED','reason':'SYMBOLIC_POINT_REQUIRES_ASSUMPTIONS'}
        domain_ok = all(d.subs(var,at) != 0 for d in denominators)
        findings.append({"at":str(at),"source_value":point["value"],
                         "status":"PASS" if domain_ok and expr.subs(var,at)==0 else "FAIL"})
    return {"status":"FAIL" if any(f["status"]=="FAIL" for f in findings) else "PASS",
            "findings":findings,"scope":"CONDITIONAL_ON_TRANSCRIPTION_NOT_SOURCE_OR_ANSWER_APPROVAL"}
