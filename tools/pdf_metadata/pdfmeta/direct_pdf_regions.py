"""Conservative raster ink grids and bounded crops; no model or reference inputs."""
from statistics import median

import numpy as np


def intersect(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def subtract(box, obstacle):
    """Disjoint rectangles covering box minus obstacle, preserving side text."""
    if not intersect(box, obstacle):
        return [box]
    left, top, right, bottom = box
    x0, y0, x1, y1 = max(left, obstacle[0]), max(top, obstacle[1]), min(right, obstacle[2]), min(bottom, obstacle[3])
    return [b for b in [(left, top, right, y0), (left, y0, x0, y1),
                        (x1, y0, right, y1), (left, y1, right, bottom)] if area(b)]


def reading_order(nodes):
    """XY-cut on physical blocks: spanning blocks, then columns left to right."""
    if len(nodes) < 2:
        return nodes
    for axis in (0, 1):
        intervals = sorted((n['bbox'][axis], n['bbox'][axis + 2]) for n in nodes)
        end = intervals[0][1]
        gaps = []
        for start, stop in intervals[1:]:
            if start - end >= 0:
                gaps.append((start - end, (start + end) / 2))
            end = max(end, stop)
        if gaps:
            cut = max(gaps)[1] if axis == 0 else min(gaps, key=lambda g: g[1])[1]
            first = [n for n in nodes if n['bbox'][axis + 2] <= cut]
            second = [n for n in nodes if n['bbox'][axis] >= cut]
            if first and second and len(first) + len(second) == len(nodes):
                return reading_order(first) + reading_order(second)
    return sorted(nodes, key=lambda n: (n['bbox'][1], n['bbox'][0]))


def visual_regions(image, detections, dpi):
    """Combine learned layout with visible grid rules; image containers are not figures."""
    width, height = image.size
    labels = {'table': 'TABLE', 'chart': 'GRAPH', 'image': 'FIGURE',
              'header_image': 'FIGURE', 'footer_image': 'FIGURE'}
    text_labels = {'text', 'paragraph_title', 'doc_title', 'content', 'header', 'footer',
                   'footnote', 'number', 'display_formula', 'inline_formula', 'formula_number'}
    text = [d for d in detections if d.get('label') in text_labels]
    candidates = []
    for d in detections:
        if d.get('label') not in labels or float(d.get('score', 0)) < .4:
            continue
        b = d['coordinate']
        box = [max(0, int(b[0])), max(0, int(b[1])), min(width, int(np.ceil(b[2]))), min(height, int(np.ceil(b[3])))]
        if area(box) < 16:
            continue
        inside = [t for t in text if intersect(t['coordinate'], box) > .85 * area(t['coordinate'])
                  and t['coordinate'][2] - t['coordinate'][0] > .35 * (box[2] - box[0])]
        children = [v for v in detections if v is not d and v.get('label') in labels
                    and .03 * area(box) < area(v['coordinate']) < .65 * area(box)
                    and intersect(box, v['coordinate']) > .9 * area(v['coordinate'])]
        if d['label'] == 'image' and area(box) > .6 * width * height and (
                children or (len(inside) >= 2 and sum(intersect(t['coordinate'], box) for t in inside) > .15 * area(box))):
            continue
        candidates.append({'bbox': box, 'visual_kind': labels[d['label']], 'score': float(d['score']),
                           'detector': 'PP-DocLayoutV3', 'review_required': float(d['score']) < .6})
    for table in detect_tables(image):
        candidates.append({'bbox': list(table['bbox']), 'visual_kind': 'TABLE', 'score': None,
                           'detector': 'RASTER_INK_GRID', 'review_required': False})
    # Nested/duplicate predictions describe one object; never retain its pixels twice.
    merged = []
    priority = {'TABLE': 3, 'GRAPH': 2, 'FIGURE': 1}
    for candidate in sorted(candidates, key=lambda c: priority[c['visual_kind']], reverse=True):
        box = candidate['bbox']
        duplicate = next((m for m in merged if intersect(m['bbox'], box) > .75 * min(area(m['bbox']), area(box))), None)
        if duplicate:
            if candidate['detector'] == 'RASTER_INK_GRID' and duplicate['visual_kind'] == 'TABLE':
                # The learned table can include the entire yellow solution panel.
                # Actual crossing rules give a tighter table boundary.
                duplicate.update(bbox=box, detector='RASTER_INK_GRID+PP-DocLayoutV3', review_required=False)
            else:
                duplicate['bbox'] = [min(duplicate['bbox'][0], box[0]), min(duplicate['bbox'][1], box[1]),
                                     max(duplicate['bbox'][2], box[2]), max(duplicate['bbox'][3], box[3])]
                duplicate['review_required'] |= candidate['review_required']
        else:
            merged.append(dict(candidate))
    padding = max(2, round(2 * dpi / 72))
    for candidate in merged:
        b = candidate['bbox']
        for title in (d['coordinate'] for d in detections if d.get('label') == 'figure_title'):
            horizontal_overlap = max(0, min(b[2], title[2]) - max(b[0], title[0]))
            gap = max(0, max(title[1] - b[3], b[1] - title[3]))
            # Titles above a figure are often printed question labels. Keep those
            # as text; only compact captions underneath are owned by the visual.
            if (title[1] >= b[3] - padding and gap < 12 * dpi / 72
                    and title[3] - title[1] < max(.3 * (b[3] - b[1]), 16 * dpi / 72)
                    and title[2] - title[0] < .9 * (b[2] - b[0])
                    and horizontal_overlap > .5 * min(b[2] - b[0], title[2] - title[0])):
                b = [min(b[0], title[0]), min(b[1], title[1]), max(b[2], title[2]), max(b[3], title[3])]
        margin = 2 if candidate['detector'].startswith('RASTER_INK_GRID') else padding
        candidate['bbox'] = [max(0, int(b[0]) - margin), max(0, int(b[1]) - margin),
                             min(width, int(np.ceil(b[2])) + margin), min(height, int(np.ceil(b[3])) + margin)]
    # Slightly touching padding is owned by one visual region; mark real overlap.
    for i, candidate in enumerate(merged):
        for other in merged[i + 1:]:
            if intersect(candidate['bbox'], other['bbox']):
                candidate['review_required'] = other['review_required'] = True
    return merged, text


def plan_visual_regions(image, detections, dpi):
    visuals, text = visual_regions(image, detections, dpi)
    free = [(0, 0, image.width, image.height)]
    for visual in visuals:
        free = [piece for box in free for piece in subtract(box, visual['bbox'])]
    nodes = [dict(v, kind='VISUAL') for v in visuals]
    maximum = max(100, int(180 * dpi / 72))

    def add_text(box, allow_columns=True):
        left, top, right, bottom = map(int, box)
        if right <= left or bottom <= top:
            return
        ink = np.asarray(image.crop((left, top, right, bottom)).convert('L')) < 175
        yy, xx = np.nonzero(ink)
        if not len(xx):
            return
        # Retain a small margin, within the free rectangle, around actual ink.
        box = (max(left, left + int(xx.min()) - 2), max(top, top + int(yy.min()) - 2),
               min(right, left + int(xx.max()) + 3), min(bottom, top + int(yy.max()) + 3))
        left, top, right, bottom = box
        if allow_columns:
            hints = [t['coordinate'] for t in text if t.get('label') in {'text', 'content', 'paragraph_title'}
                     and t['coordinate'][3] - t['coordinate'][1] > 12 * dpi / 72
                     and intersect(t['coordinate'], box) > .8 * area(t['coordinate'])]
            narrow = sorted((b[0], b[2]) for b in hints if .18 * (right - left) < b[2] - b[0] < .75 * (right - left))
            cuts = []
            if narrow:
                end = narrow[0][1]
                for start, stop in narrow[1:]:
                    if start - end > .025 * (right - left):
                        cuts.append((start - end, (start + end) / 2))
                    end = max(end, stop)
            if cuts:
                def flows_vertically(boxes):
                    # One short item beside a larger block is an inline choice,
                    # not evidence of a document column. Two separate lines or
                    # a genuine multiline paragraph can establish column flow.
                    if any(b[3] - b[1] >= 24 * dpi / 72 for b in boxes):
                        return True
                    return any(min(a[3], b[3]) <= max(a[1], b[1])
                               for i, a in enumerate(boxes) for b in boxes[i + 1:])

                column_cuts = [c for c in cuts
                               if flows_vertically([b for b in hints if b[2] <= c[1]])
                               and flows_vertically([b for b in hints if b[0] >= c[1]])]
                if not column_cuts:
                    # Read a row of short side-by-side items before the material
                    # underneath. Split only at an observed blank horizontal gap,
                    # so a right-hand item cannot follow the solution below it.
                    cut = max(cuts)[1]
                    sides = [[b for b in hints if b[2] <= cut],
                             [b for b in hints if b[0] >= cut]]
                    isolated = [b for side in sides if side and not flows_vertically(side) for b in side]
                    if isolated:
                        row_bottom = max(b[3] for b in isolated)
                        following = [b[1] for b in hints if b[1] > row_bottom]
                        if following:
                            boundary = round((row_bottom + min(following)) / 2)
                            stripe = np.asarray(image.crop((left, boundary - 1, right, boundary + 2)).convert('L'))
                            if top < boundary < bottom and not (stripe < 175).any():
                                add_text((left, top, right, boundary), False)
                                add_text((left, boundary, right, bottom), True)
                                return
                    cuts = []
                else:
                    cuts = column_cuts
            if cuts:
                cut = round(max(cuts)[1])
                spanning = sorted((max(top, int(b[1])), min(bottom, int(np.ceil(b[3])))) for b in hints if b[0] < cut < b[2])
                cursor = top
                for y0, y1 in spanning + [(bottom, bottom)]:
                    if y0 > cursor:
                        add_text((left, cursor, cut, y0), False)
                        add_text((cut, cursor, right, y0), False)
                    if y1 > max(cursor, y0):
                        add_text((left, max(cursor, y0), right, y1), False)
                    cursor = max(cursor, y1)
                return
        if bottom - top > maximum:
            halves = split_box(image, box)
            if halves:
                for half in halves:
                    add_text(half, allow_columns)
                return
        nodes.append({'kind': 'TEXT', 'bbox': list(box)})

    for box in free:
        add_text(box)
    return reading_order(nodes)


def runs(values):
    edges = np.diff(np.r_[False, values, False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def split_box(image, box, *, cell=False):
    """Prefer an empty gutter; never invent overlap or omit pixels at the cut."""
    left, top, right, bottom = box
    vertical = cell and right - left > 3 * (bottom - top)
    ink = np.asarray(image.crop(box).convert('L')) < 175
    density = ink.mean(axis=0 if vertical else 1)
    size = len(density)
    if size < 40:
        return []
    lo, hi = max(1, int(size * .3)), min(size - 1, int(size * .7))
    gaps = [(a, b) for a, b in runs(density[lo:hi] < .015) if b - a >= 3]
    cut = min(((a + b) // 2 + lo for a, b in gaps), key=lambda x: abs(x - size / 2), default=size // 2)
    if vertical:
        return [(left, top, left + cut, bottom), (left + cut, top, right, bottom)]
    return [(left, top, right, top + cut), (left, top + cut, right, bottom)]


def detect_tables(image):
    """Require repeated long rules plus a crossing vertical rule, like native ink grids.

    This also handles an open variation table (two horizontal rules, one long
    vertical rule). Only visible dividers define cells: no inferred math columns.
    Unknown/borderless tables stay in ordinary bounded image transcription.
    """
    ink = np.asarray(image.convert('L')) < 150
    height, width = ink.shape
    horizontal = []
    for y in range(height):
        for a, b in runs(ink[y]):
            if b - a >= max(80, int(width * .25)):
                if horizontal and y - horizontal[-1][0] <= 3 and abs(a - horizontal[-1][1]) < 5 and abs(b - horizontal[-1][2]) < 5:
                    continue
                horizontal.append((y, a, b))
    groups = []
    for line in horizontal:
        y, a, b = line
        group = next((g for g in groups if 8 < y - g[-1][0] < min(350, height * .4)
                      and min(b, g[-1][2]) - max(a, g[-1][1]) > .85 * min(b - a, g[-1][2] - g[-1][1])), None)
        if group is None:
            groups.append([line])
        else:
            group.append(line)
    tables = []
    for group in groups:
        if len(group) < 2:
            continue
        ys = [g[0] for g in group]
        gap = median(b - a for a, b in zip(ys, ys[1:]))
        left, right = min(g[1] for g in group), max(g[2] for g in group)
        low, high = max(0, int(ys[0] - gap * 1.5)), min(height, int(ys[-1] + gap * 4))
        vertical = []
        for x in range(left, right):
            for a, b in runs(ink[low:high, x]):
                a, b = a + low, b + low
                if a <= ys[0] + 3 and b >= ys[-1] - 3 and b - a > ys[-1] - ys[0] + 8:
                    if not vertical or x - vertical[-1][0] > 4:
                        vertical.append((x, a, b))
        if not vertical:
            continue
        top, bottom = min(v[1] for v in vertical), max(v[2] for v in vertical)
        xb = [left] + [v[0] for v in vertical if left + 6 < v[0] < right - 6] + [right]
        yb = [top] + [y for y in ys if top + 6 < y < bottom - 6] + [bottom]
        if len(xb) < 3 or len(yb) < 3 or (len(xb) - 1) * (len(yb) - 1) > 36:
            continue
        bbox = (left, top, right, bottom)
        if any(not (bottom <= t['bbox'][1] or top >= t['bbox'][3]) for t in tables):
            continue
        tables.append({'bbox': bbox, 'rows': len(yb) - 1, 'columns': len(xb) - 1,
                       'cells': [{'row': r, 'column': c, 'bbox': (x0, y0, x1, y1)}
                                 for r, (y0, y1) in enumerate(zip(yb, yb[1:]))
                                 for c, (x0, x1) in enumerate(zip(xb, xb[1:]))]})
    return sorted(tables, key=lambda t: t['bbox'][1])


def plan_regions(image, max_height):
    """Separate tables before prose, then bound each remaining horizontal band."""
    tables = detect_tables(image)
    nodes = []
    top = 0

    def bands(y0, y1):
        if y1 <= y0:
            return
        pending = [(0, y0, image.width, y1)]
        while pending:
            box = pending.pop(0)
            if box[3] - box[1] > max_height:
                halves = split_box(image, box)
                if halves:
                    pending[0:0] = halves
                    continue
            if (np.asarray(image.crop(box).convert('L')) < 175).any():
                nodes.append({'kind': 'TEXT', 'bbox': box})

    for number, table in enumerate(tables):
        bands(top, table['bbox'][1])
        # Preserve side text too. A detected grid never owns the entire strip.
        for box in [(0, table['bbox'][1], table['bbox'][0], table['bbox'][3]),
                    (table['bbox'][2], table['bbox'][1], image.width, table['bbox'][3])]:
            if box[2] > box[0] and (np.asarray(image.crop(box).convert('L')) < 175).any():
                nodes.append({'kind': 'TEXT', 'bbox': box})
        nodes.append({'kind': 'TABLE', 'bbox': table['bbox'], 'table': table, 'number': number})
        top = table['bbox'][3]
    bands(top, image.height)
    return nodes
