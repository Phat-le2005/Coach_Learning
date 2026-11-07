import type { InkStroke } from "@/lib/api/contracts";
import { computeBounds } from "./structured-transcription-ir";
import { mapLayoutToScopes, scopeIntegrity, validateOcrSource, type ScopeSource, type PerceptionResult, type RenderTransform, type ScopeProposal } from "./ocr-v2-geometry";

// Experimental, scale-relative geometric evidence. None of these cues recognizes a symbol
// or establishes that a transcript/content kind is correct. Never uses OCR text to group ink.
type Box = { l: number; r: number; t: number; b: number };
type Item = Box & { ids: string[]; x: number; y: number; w: number; h: number; cue: string[] };
export type RoutingDecision = { action: "COMER_PROBE" | "MANUAL"; reasons: string[]; status: string };
export type ScopeCandidate = { id: string; source: "INK_GEOMETRY" | "LEARNED_LAYOUT" | "CLUSTER_COMPLETION"; strokeIds: string[]; bounds: ReturnType<typeof computeBounds>; evidence: string[]; disposition: string; competingIds: string[] };
export interface ScopeConstruction {
  version: "multi-hypothesis/1"; mode: "HYBRID" | "GEOMETRY"; bodyHeightPx: number;
  scopes: ScopeProposal[]; candidates: ScopeCandidate[]; routing: Record<string, RoutingDecision>;
  relations: { kind: "UNKNOWN"; strokeIds: string[]; childScopeIds: string[]; reason: string }[];
  readingOrder: "PROPOSED" | "AMBIGUOUS"; trace: unknown[]; durationMs: number;
}
const median = (v: number[]) => [...v].sort((a, b) => a - b)[Math.floor(v.length / 2)] ?? 20;
const gapX = (a: Box, b: Box) => Math.max(0, a.l - b.r, b.l - a.r);
const gapY = (a: Box, b: Box) => Math.max(0, a.t - b.b, b.t - a.b);
const overlapX = (a: Box, b: Box) => Math.max(0, Math.min(a.r, b.r) - Math.max(a.l, b.l));
function combined(items: Item[], cue: string[] = []): Item {
  const l = Math.min(...items.map(a => a.l)), r = Math.max(...items.map(a => a.r)), t = Math.min(...items.map(a => a.t)), b = Math.max(...items.map(a => a.b));
  return { l, r, t, b, x: (l + r) / 2, y: (t + b) / 2, w: r - l, h: b - t, ids: [...new Set(items.flatMap(a => a.ids))], cue: [...new Set([...items.flatMap(a => a.cue), ...cue])] };
}
export interface LayoutRelationDecision {
  layoutCandidateId: string; geometryCandidateIds: string[]; strokeIds: string[];
  positive: string[]; negative: string[]; decision: "MERGE" | "KEEP_GEOMETRY";
  metrics?: { gapBody: number; prefixHeightBody: number; prefixWidthBody: number };
}
/** A narrow relation pass, not box ownership: complete a compact left prefix of an
 * already supported fraction only when an exact formula proposal supports both.
 * Independent equations, prose and multi-row delimiters remain separate.
 * Exported at the mapped-proposal seam so archived detector evidence can be replayed.
 */
export function reconcileLayoutScopeCandidates(source: ScopeSource, scopes: ScopeProposal[], learned: ScopeProposal[], body: number) {
  const pen = validateOcrSource(source), box = (s: ScopeProposal): Box => {
    const b = computeBounds(pen.filter(p => s.strokeIds.includes(p.id)));
    return { l: b.left * 794, r: b.right * 794, t: b.top * 1123, b: b.bottom * 1123 };
  };
  const decisions: LayoutRelationDecision[] = [];
  const proposals: { decision: LayoutRelationDecision; members: ScopeProposal[]; host: ScopeProposal }[] = [];
  for (const layout of learned.filter(l => l.candidateStrokeIds.length)) {
    const members = scopes.filter(s => s.strokeIds.some(id => layout.candidateStrokeIds.includes(id)));
    if (members.length < 2) continue;
    const ids = pen.filter(p => members.some(s => s.strokeIds.includes(p.id))).map(p => p.id);
    const d: LayoutRelationDecision = { layoutCandidateId: `candidate-${layout.id}`,
      geometryCandidateIds: members.map(s => `candidate-${s.id}`), strokeIds: ids,
      positive: [], negative: [], decision: "KEEP_GEOMETRY" };
    decisions.push(d);
    if (layout.kind !== "MATH") d.negative.push("NO_FORMULA_LAYOUT_SUPPORT");
    else d.positive.push("FORMULA_LAYOUT_PROPOSAL");
    if (members.length !== 2) d.negative.push("NOT_A_LOCAL_PREFIX_PAIR; box may cover independent content");
    if (ids.length !== layout.candidateStrokeIds.length || ids.some(id => !layout.candidateStrokeIds.includes(id))
      || ids.length !== layout.strokeIds.length || ids.some(id => !layout.strokeIds.includes(id))) d.negative.push("PARTIAL_GROUP_OR_COMPETING_LAYOUT_OWNERSHIP");
    if (members.some(s => s.kind === "TEXT" || s.kind === "MIXED") || learned.some(l => (l.kind === "TEXT" || l.kind === "MIXED") && l.candidateStrokeIds.some(id => ids.includes(id)))) d.negative.push("TEXT_OR_MIXED_EVIDENCE");
    if (members.some(s => s.flags.includes("MULTI_ROW_DELIMITER_UNRESOLVED"))) d.negative.push("UNRESOLVED_MULTI_ROW_DELIMITER");
    if (members.filter(s => s.flags.includes("PARALLEL_EQUALITY_STROKES")).length > 1) d.negative.push("INDEPENDENT_EQUALITY_ANCHORS");
    const hosts = members.filter(s => s.flags.includes("FRACTION_BAR_WITH_ABOVE_BELOW_SUPPORT"));
    if (hosts.length !== 1) d.negative.push("NO_UNIQUE_SUPPORTED_FRACTION");
    if (members.length === 2 && hosts.length === 1) {
      const host = hosts[0], prefix = members.find(s => s !== host)!, h = box(host), p = box(prefix);
      if (host.kind !== "MATH") d.negative.push("FRACTION_HOST_NOT_ROUTED_MATH");
      const height = p.b - p.t, width = p.r - p.l, cy = (p.t + p.b) / 2;
      d.metrics = { gapBody: gapX(h, p) / body, prefixHeightBody: height / body, prefixWidthBody: width / body };
      if (p.r <= h.l && gapX(h, p) <= body * 1.2 && height <= body * 1.5 && width <= body * 2
        && cy >= h.t + (h.b - h.t) * .15 && cy <= h.b - (h.b - h.t) * .15) d.positive.push("COMPACT_LEFT_PREFIX_WITHIN_FRACTION_BODY_SUPPORT");
      else d.negative.push("NO_BOUNDED_PREFIX_RELATION");
      if (!d.negative.length) proposals.push({ decision: d, members, host });
    }
  }
  // Do not choose a host by detector order when two incompatible merges compete.
  const compatible = proposals.filter(p => {
    const conflict = proposals.some(other => other !== p && other.members.some(s => p.members.includes(s))
      && (other.members.length !== p.members.length || other.members.some(s => !p.members.includes(s))));
    if (conflict) p.decision.negative.push("COMPETING_RELATION_HYPOTHESES");
    return !conflict;
  });
  const replaced = new Set<string>(), merged: ScopeProposal[] = [];
  for (const p of compatible) {
    p.decision.decision = "MERGE";
    if (p.members.some(s => replaced.has(s.id))) continue; // identical supporting proposals
    p.members.forEach(s => replaced.add(s.id));
    const ids = pen.filter(s => p.members.some(g => g.strokeIds.includes(s.id))).map(s => s.id);
    merged.push({ ...p.host, strokeIds: ids, candidateStrokeIds: ids,
      regionIds: [...new Set(p.members.flatMap(s => s.regionIds))],
      flags: [...new Set([...p.members.flatMap(s => s.flags), "LAYOUT_SUPPORTED_FRACTION_PREFIX", "RECONCILED_SCOPE_REQUIRES_REVIEW"])],
      method: "EXACT_LAYOUT_FORMULA_SUPPORT + BOUNDED_FRACTION_PREFIX_RELATION; no OCR/GT used" });
  }
  const active = [...scopes.filter(s => !replaced.has(s.id)), ...merged].sort((a, b) => {
    const aa = box(a), bb = box(b); return aa.t - bb.t || aa.l - bb.l;
  });
  const integrity = scopeIntegrity(source, active);
  if (integrity.missing.length || integrity.duplicateOwnership.length || integrity.unknown.length) throw Error("RELATION_RECONCILIATION_SOURCE_INTEGRITY_FAILED");
  return { scopes: active, decisions };
}
/** Non-transitive row anchors, fraction support and bounded satellite attachment.
 * Layout labels support bounded relations, never directly own or join independent rows. */
export function constructScopeCandidates(source: ScopeSource, perception: PerceptionResult, transform: RenderTransform, mode: "HYBRID" | "GEOMETRY" = "HYBRID"): ScopeConstruction {
  const start = performance.now(), pen = validateOcrSource(source);
  const items: Item[] = pen.map(s => { const b = computeBounds([s]), l = b.left * 794, r = b.right * 794, t = b.top * 1123, bottom = b.bottom * 1123;
    return { l, r, t, b: bottom, x: (l + r) / 2, y: (t + bottom) / 2, w: r - l, h: bottom - t, ids: [s.id], cue: [] }; });
  const body = Math.max(8, median(items.filter(a => a.h >= 8).map(a => a.h)));
  const trace: unknown[] = [{ stage: "SOURCE", strokeIds: pen.map(s => s.id), bodyHeightPx: body, decision: "PEN only; original IDs/order/coordinates retained" }];
  const horizontal = items.filter(a => a.w >= 6 && a.w / Math.max(1, a.h) >= 2.4 && a.h <= body * .42);
  // A long fraction rule can be slightly sloped while its axis-aligned box is
  // taller than a small glyph. Keep this evidence separate from equality/cross
  // detection: relaxing their horizontal threshold would change routing too.
  const slopedFractionRules = items.filter(a => !horizontal.includes(a) && a.w >= body * 2.2).filter(a => {
    const stroke = pen.find(s => s.id === a.ids[0])!;
    const points = stroke.points.map(p => ({ x: p.x * 794, y: p.y * 1123 }));
    const first = points[0], last = points[points.length - 1];
    const dx = last.x - first.x, dy = last.y - first.y, chord = Math.hypot(dx, dy);
    if (Math.abs(dx) < a.w * .85 || Math.abs(dy) > Math.abs(dx) * .15 || !chord) return false;
    const length = points.slice(1).reduce((sum, p, i) => sum + Math.hypot(p.x - points[i].x, p.y - points[i].y), 0);
    const deviation = Math.max(...points.map(p => Math.abs(dx * (p.y - first.y) - dy * (p.x - first.x)) / chord));
    if (length > chord * 1.15 || deviation > Math.max(body * .35, a.w * .035)) return false;
    trace.push({ stage: "SLOPED_FRACTION_RULE", ids: a.ids, widthPx: a.w, heightPx: a.h,
      strictHorizontalHeightLimitPx: body * .42, slope: Math.abs(dy / dx), pathToChordRatio: length / chord,
      maxDeviationPx: deviation, reason: "NEAR_LINEAR_LONG_STROKE; fraction support still required; not equality evidence" });
    return true;
  });
  const equals: Item[][] = [];
  for (let i = 0; i < horizontal.length; i++) for (let j = i + 1; j < horizontal.length; j++) {
    const a = horizontal[i], b = horizontal[j];
    if (Math.abs(a.y - b.y) >= 3 && Math.abs(a.y - b.y) <= body * 1.05 && overlapX(a, b) / Math.max(1, Math.min(a.w, b.w)) >= .68 && Math.min(a.w, b.w) / Math.max(a.w, b.w) >= .5)
      equals.push([a, b]);
  }
  const equalIds = new Set(equals.flat().flatMap(a => a.ids));
  const crosses: Item[][] = [];
  for (const bar of horizontal.filter(a => !equalIds.has(a.ids[0]) && a.w >= body * .7)) for (const stem of items) {
    if (stem === bar || stem.h < body * .6 || stem.w > body * .45 || stem.h / Math.max(1, stem.w) < 2) continue;
    const crossing = (bar.y - stem.t) / stem.h;
    if (crossing >= .2 && crossing <= .8 && stem.x >= bar.l + bar.w * .18 && stem.x <= bar.r - bar.w * .18)
      crosses.push([bar, stem]);
  }
  const fractions: Item[] = [], used = new Set<string>();
  for (const bar of [...horizontal, ...slopedFractionRules].filter(a => !equalIds.has(a.ids[0]) && a.w >= body * 2.2).sort((a, b) => b.w - a.w)) {
    if (used.has(bar.ids[0])) continue;
    if (items.some(a => a !== bar && a.h > body * 1.3 && a.w / a.h <= 2.2 && a.w > bar.w * .55 && overlapX(a, bar) > bar.w * .65 && a.t >= bar.y - body * .12 && a.t - bar.y < body * .2)) {
      trace.push({ stage: "FRACTION_REJECTED", bar: bar.ids, reason: "BAR_ATTACHED_TO_COMPACT_GLYPH; long radical overline is not this cue" }); continue;
    }
    // A newly admitted long sloped rule can enclose nested fractions farther
    // than the glyph-height window. Keep the old horizontal path unchanged:
    // widening every bar can absorb independent rows on mixed-content pages.
    const supportLimit = slopedFractionRules.includes(bar)
      ? Math.max(body * 3.3, Math.min(bar.w * .5, body * 5)) : body * 3.3;
    const around = items.filter(a => !used.has(a.ids[0]) && a !== bar && a.x >= bar.l - body * .25 && a.x <= bar.r + body * .25 && Math.abs(a.y - bar.y) < supportLimit);
    const above = around.filter(a => a.b < bar.y && bar.y - a.b < body * 2.1), below = around.filter(a => a.t > bar.y && a.t - bar.y < body * 2.1);
    if (!above.some(a => a.h > body * .35) || !below.some(a => a.h > body * .35)) continue;
    // Two full-width aligned equations have independent equals anchors; a bar between
    // them cannot silently turn those rows into one fraction.
    const independentRows = equals.filter(pair => pair.some(a => around.includes(a)) && Math.abs(combined(pair).y - bar.y) > body * .7);
    if (independentRows.length >= 2) { trace.push({ stage: "FRACTION_REJECTED", bar: bar.ids, reason: "INDEPENDENT_EQUALITY_ROWS" }); continue; }
    const group = combined([bar, ...around], ["FRACTION_BAR_WITH_ABOVE_BELOW_SUPPORT"]); group.y = bar.y;
    fractions.push(group); group.ids.forEach(id => used.add(id));
    trace.push({ stage: "FRACTION_SUPPORT", bar: bar.ids, strokeIds: group.ids, anchorY: group.y, limitPx: supportLimit });
  }
  // Initial rows are made from body-size marks; dots, bounds and exponents do not
  // create row anchors. Tall left delimiters are withheld to avoid bridging rows.
  const remaining = items.filter(a => !used.has(a.ids[0]));
  const tall = remaining.filter(a => a.h > body * 2.15 && a.w < a.h * .7);
  const rawAnchors = [
    ...equals.filter(pair => pair.every(a => !used.has(a.ids[0])) && Math.min(...pair.map(a => a.w)) >= body * .6).map(pair => combined(pair, ["PARALLEL_EQUALITY_STROKES"])),
    ...crosses.filter(pair => pair.every(a => !used.has(a.ids[0]))).map(pair => combined(pair, ["BALANCED_CROSS_STROKES"])),
  ];
  const equationAnchors: Item[] = [], anchored = new Set<string>();
  for (const anchor of rawAnchors) if (!anchor.ids.some(id => anchored.has(id))) { equationAnchors.push(anchor); anchor.ids.forEach(id => anchored.add(id)); }
  const anchorIds = new Set(equationAnchors.flatMap(a => a.ids));
  const seeds = [...equationAnchors, ...fractions, ...remaining.filter(a => !anchorIds.has(a.ids[0]) && !tall.includes(a) && (a.h >= body * .68 || horizontal.includes(a)))];
  const rows: { anchor: number; items: Item[] }[] = [];
  // Prioritize spatial math anchors over top-most ink: a raised exponent must not
  // establish the baseline of a whole equation. Anchors remain fixed thereafter.
  for (const item of seeds) {
    const match = rows.map(row => ({ row, d: Math.abs(row.anchor - item.y) })).filter(a => a.d <= body * .72).sort((a, b) => a.d - b.d)[0];
    if (match) match.row.items.push(item); else rows.push({ anchor: item.y, items: [item] });
  }
  const groups: Item[][] = [];
  const crossAtBoundary = (left: Item[], right: Item[]) => {
    const a = combined(left), b = combined(right);
    return left.some(i => i.cue.includes("BALANCED_CROSS_STROKES") && a.r - i.r < body * .5)
      || right.some(i => i.cue.includes("BALANCED_CROSS_STROKES") && i.l - b.l < body * .5);
  };
  // Explicit horizontal whitespace separates columns / prose prefixes. This is
  // independent of row tolerance and does not chain vertically through tall ink.
  for (const row of rows) {
    let current: Item[] = [], right = -Infinity;
    for (const item of row.items.sort((a, b) => a.l - b.l)) {
      const operatorBridge = current.length && crossAtBoundary(current, [item]);
      if (current.length && item.l - right > body * (operatorBridge ? 2.2 : 1.6)) { groups.push(current); current = []; }
      current.push(item); right = Math.max(right, item.r);
    }
    if (current.length) groups.push(current);
  }
  const mainEquality = (group: Item[]) => equals.some(pair => pair.every(a => combined(group).ids.includes(a.ids[0])) && Math.min(...pair.map(a => a.w)) >= body * .6);
  // A sloped handwritten line can straddle two fixed row anchors. Reconcile by
  // actual vertical support, not centre chaining. Two independent equality rows
  // are never merged by this rule; fraction height is not a global row tolerance.
  const reconcileFragments = (stage: string) => {
    let joined = true;
    while (joined) {
      joined = false;
      outer: for (let i = 0; i < groups.length; i++) for (let j = i + 1; j < groups.length; j++) {
        const a = combined(groups[i]), b = combined(groups[j]), union = combined([...groups[i], ...groups[j]]);
        if (a.cue.includes("MULTI_ROW_DELIMITER_UNRESOLVED") || b.cue.includes("MULTI_ROW_DELIMITER_UNRESOLVED")
          || (mainEquality(groups[i]) && mainEquality(groups[j]))) continue;
        const overlap = Math.min(a.b, b.b) - Math.max(a.t, b.t);
        const heightLimit = Math.max(body * 2.6, Math.max(a.h, b.h) + body * .35);
        const operatorBridge = a.l <= b.l ? crossAtBoundary(groups[i], groups[j]) : crossAtBoundary(groups[j], groups[i]);
        if (gapX(a, b) <= body * (operatorBridge ? 2.7 : 1.6) && overlap >= Math.min(body * .25, Math.min(a.h, b.h) * .3) && union.h <= heightLimit) {
          trace.push({ stage, first: a.ids, second: b.ids, verticalOverlapPx: overlap, unionHeightPx: union.h, reason: "SUPPORTED_SLOPED_LINE; independent equality anchors protected" });
          groups[i].push(...groups[j]); groups.splice(j, 1); joined = true; break outer;
        }
      }
    }
  };
  reconcileFragments("FRAGMENT_RECONCILIATION");
  // Sparse elevated fragments can be initial row seeds (e.g. an exponent drawn
  // as large as a letter). Reconsider them using an independently substantial
  // neighbouring row. Never demote an ordinary equality-bearing line.
  for (let i = groups.length - 1; i >= 0; i--) {
    const group = groups[i], box = combined(group);
    const hasMainEquality = equals.some(pair => pair.every(a => box.ids.includes(a.ids[0])) && Math.min(...pair.map(a => a.w)) >= body * .7);
    if (hasMainEquality || box.cue.length || box.w > body * 2.1 || box.h >= body * .98) continue;
    const support = groups.some((other, j) => j !== i && combined(other).w > Math.max(box.w * 2, body * 2.5)
      && gapX(combined(other), box) < body * .8 && gapY(combined(other), box) < body * 1.65);
    if (support) { trace.push({ stage: "RECONSIDER_SPARSE_ROW", ids: box.ids, reason: "BOUNDED_SATELLITE_CANDIDATE; not yet assigned" }); groups.splice(i, 1); }
  }
  const assigned = new Set(groups.flat(2).flatMap(a => a.ids));
  const withheld: Item[] = [], ambiguous = new Set<string>();
  // Complete body rows before assessing tall delimiters. Otherwise short letters
  // missing from the seed band can make a second row look horizontally distant.
  for (const item of remaining.filter(a => !assigned.has(a.ids[0])).sort((a, b) => Number(tall.includes(a)) - Number(tall.includes(b)) || b.h - a.h)) {
    if (assigned.has(item.ids[0])) continue;
    const near = groups.map(group => ({ group, box: combined(group), anchor: median(group.map(a => a.y)) }))
      .filter(a => gapX(a.box, item) <= body * (tall.includes(item) ? 1.8 : .95) && gapY(a.box, item) <= body * 1.65)
      .map(a => ({ ...a, cost: gapX(a.box, item) + Math.abs(a.anchor - item.y) * .45 })).sort((a, b) => a.cost - b.cost);
    const delimiterRows = tall.includes(item) ? near.filter(a => a.box.r >= item.r + body && item.t - body * .35 <= a.anchor && item.b + body * .35 >= a.anchor) : [];
    if (delimiterRows.length > 1) {
      const corners = remaining.filter(a => a !== item && a.w < item.w * 1.2 && a.h < body * .4 && overlapX(a, item) > a.w * .5 && Math.min(Math.abs(a.y - item.t), Math.abs(a.y - item.b)) < body * .3);
      for (const corner of corners) for (const group of groups) { const at = group.findIndex(a => a.ids.includes(corner.ids[0])); if (at >= 0) group.splice(at, 1); }
      for (let at = groups.length - 1; at >= 0; at--) if (!groups[at].length) groups.splice(at, 1);
      withheld.push(combined([item, ...corners], ["MULTI_ROW_DELIMITER_UNRESOLVED"]));
      [item, ...corners].flatMap(a => a.ids).forEach(id => assigned.add(id));
      trace.push({ stage: "DELIMITER", ids: [item, ...corners].flatMap(a => a.ids), reason: "MULTIPLE_ROWS; relation only, never atomic whole-page merge" }); continue;
    }
    // A substantial independent line is not an exponent. Ambiguous small marks
    // remain visible instead of assigning arbitrary nearest ownership.
    const isSatellite = item.h <= body * .98 || tall.includes(item);
    if (near.length && isSatellite && (near.length === 1 || near[1].cost - near[0].cost > body * .22)) {
      near[0].group.push({ ...item, cue: [...item.cue, "SATELLITE_ATTACHED"] }); item.ids.forEach(id => assigned.add(id));
      trace.push({ stage: "SATELLITE_ATTACHMENT", ids: item.ids, to: near[0].group.flatMap(a => a.ids), reason: "BOUNDED_NEAREST_SUPPORT", distancePx: near[0].cost });
    } else { withheld.push(item); if (near.length > 1) item.ids.forEach(id => ambiguous.add(id)); }
  }
  // Unattached ink is grouped only along a local line, not into a page-wide rescue.
  for (const item of withheld) {
    const bucket = groups.find(group => group.every(a => withheld.includes(a)) && Math.abs(combined(group).y - item.y) < body * .5 && gapX(combined(group), item) < body * .75);
    if (bucket) bucket.push(item); else groups.push([item]);
  }
  // Limits near a sizeable operator stay local to that operator's x-support.
  // They cannot connect two full-width rows or a delimiter spanning two rows.
  for (let i = groups.length - 1; i >= 0; i--) {
    const limit = combined(groups[i]);
    if (mainEquality(groups[i]) || limit.cue.includes("MULTI_ROW_DELIMITER_UNRESOLVED")) continue;
    for (let j = 0; j < groups.length; j++) {
      if (i === j) continue;
      const target = combined(groups[j]);
      const operator = groups[j].find(a => a.h >= body * 1.5 && a.w >= body && a.w / Math.max(1, a.h) <= 2 && !a.cue.includes("FRACTION_BAR_WITH_ABOVE_BELOW_SUPPORT"));
      if (!operator || target.w <= operator.w * 1.5 || limit.l < operator.l - body * .35 || limit.r > operator.r + body * .35 || limit.h > body * 1.8 || gapY(operator, limit) > body * 1.6) continue;
      trace.push({ stage: "OPERATOR_LIMIT_SUPPORT", operator: operator.ids, attached: limit.ids, reason: "LOCAL_X_SUPPORT; no independent full-width equality row" });
      groups[j].push(...groups[i].map(a => ({ ...a, cue: [...a.cue, "LOCAL_OPERATOR_LIMITS"] }))); groups.splice(i, 1); break;
    }
  }
  for (let i = groups.length - 1; i >= 0; i--) {
    const fragment = combined(groups[i]);
    if (fragment.w > body * 1.2 || fragment.h > body * 1.3 || fragment.cue.length || mainEquality(groups[i])) continue;
    const support = groups.filter((other, j) => { const b = combined(other); return i !== j && b.w > body * 4 && fragment.x >= b.l && fragment.x <= b.r && gapY(fragment, b) < body * 1.1; });
    if (support.length === 1) { support[0].push(...groups[i].map(a => ({ ...a, cue: [...a.cue, "RAISED_MARK_WITHIN_LINE_SUPPORT"] }))); groups.splice(i, 1); trace.push({ stage: "RAISED_MARK_COMPLETION", ids: fragment.ids, reason: "UNIQUE_LONG_LINE_X_SUPPORT; bounded vertical distance" }); }
  }
  // Satellites/diacritics can complete line support after the initial check.
  // Reuse identical gates; do not widen the body/height tolerance to rescue a case.
  reconcileFragments("POST_COMPLETION_FRAGMENT_RECONCILIATION");
  const learned = mapLayoutToScopes(source, perception, transform);
  const candidates: ScopeCandidate[] = [], routing: Record<string, RoutingDecision> = {};
  let scopes = groups.map(group => {
    const merged = combined(group), ids = pen.filter(s => merged.ids.includes(s.id)).map(s => s.id), id = `ink-${items.findIndex(a => a.ids[0] === ids[0])}`;
    const matched = learned.filter(s => s.candidateStrokeIds.some(st => ids.includes(st)));
    const exactFormula = mode === "HYBRID" && matched.some(s => s.kind === "MATH" && s.candidateStrokeIds.length === ids.length && ids.every(st => s.coverage[st] >= .8));
    const localEquals = equals.some(pair => pair.every(a => a.ids.every(st => ids.includes(st))));
    const localCrosses = crosses.filter(pair => pair.every(a => ids.includes(a.ids[0]))).length;
    const cues = [...merged.cue, ...(localEquals ? ["PARALLEL_EQUALITY_STROKES"] : []), ...(exactFormula ? ["FORMULA_LABEL_MATCHES_INDEPENDENT_GEOMETRY"] : [])];
    const textSignal = matched.some(s => s.kind === "TEXT"), uncertain = ids.some(st => ambiguous.has(st)) || cues.includes("MULTI_ROW_DELIMITER_UNRESOLVED");
    const math = !uncertain && (localEquals || cues.includes("FRACTION_BAR_WITH_ABOVE_BELOW_SUPPORT") || exactFormula
      || (localCrosses > 0 && (localCrosses >= 2 || cues.includes("LOCAL_OPERATOR_LIMITS") || cues.includes("SATELLITE_ATTACHED"))));
    const kind = math ? "MATH" : textSignal ? "TEXT" : "UNKNOWN";
    const reason = math ? "GEOMETRY_SUPPORTED_MATH_HYPOTHESIS; output remains unconfirmed" : uncertain ? "GEOMETRY_AMBIGUOUS" : textSignal ? "TEXT_SIGNAL_WITHOUT_MATH_SUPPORT; HTR unavailable" : "NO_POSITIVE_MATH_EVIDENCE";
    routing[id] = { action: math ? "COMER_PROBE" : "MANUAL", reasons: [...cues, reason], status: math ? "QUEUED_UNCONFIRMED" : reason };
    candidates.push({ id: `candidate-${id}`, source: "INK_GEOMETRY", strokeIds: ids, bounds: computeBounds(pen.filter(s => ids.includes(s.id))), evidence: cues, disposition: "ACTIVE_UNCONFIRMED", competingIds: matched.map(s => `candidate-${s.id}`) });
    return { id, regionIds: [...new Set(matched.flatMap(s => s.regionIds))], rawLabel: matched.map(s => s.rawLabel).join(" | ") || "ink_geometry", rawScore: null, kind,
      strokeIds: ids, candidateStrokeIds: ids, coverage: {}, flags: ["MULTI_HYPOTHESIS", "UNCONFIRMED_CONTENT_KIND", ...cues, reason], method: "INK_ROWS_FIXED_ANCHORS + FRACTION_SUPPORT + BOUNDED_SATELLITES; detector is evidence only" } as ScopeProposal;
  }).sort((a, b) => { const aa = computeBounds(pen.filter(s => a.strokeIds.includes(s.id))), bb = computeBounds(pen.filter(s => b.strokeIds.includes(s.id))); return aa.top - bb.top || aa.left - bb.left; });
  const relationPass = mode === "HYBRID" ? reconcileLayoutScopeCandidates(source, scopes, learned, body) : null;
  if (relationPass) {
    scopes = relationPass.scopes;
    trace.push({ stage: "LAYOUT_RELATION_RECONCILIATION", decisions: relationPass.decisions });
    for (const d of relationPass.decisions.filter(d => d.decision === "MERGE")) {
      for (const c of candidates.filter(c => d.geometryCandidateIds.includes(c.id))) c.disposition = "SUPERSEDED_BY_LAYOUT_SUPPORTED_RELATION";
      const scope = scopes.find(s => s.strokeIds.length === d.strokeIds.length && d.strokeIds.every(id => s.strokeIds.includes(id)))!;
      candidates.push({ id: `relation-${d.layoutCandidateId}`, source: "CLUSTER_COMPLETION", strokeIds: d.strokeIds,
        bounds: computeBounds(pen.filter(s => d.strokeIds.includes(s.id))), evidence: d.positive,
        disposition: `ACTIVE_UNCONFIRMED; ${scope.id}`, competingIds: [...d.geometryCandidateIds, d.layoutCandidateId] });
      routing[scope.id] = { action: "COMER_PROBE", status: "QUEUED_UNCONFIRMED", reasons: [...d.positive, "LAYOUT_SUPPORTED_FRACTION_PREFIX; review required"] };
    }
    for (const id of Object.keys(routing)) if (!scopes.some(s => s.id === id)) delete routing[id];
  }
  for (const item of learned.filter(s => s.candidateStrokeIds.length)) {
    const intersecting = scopes.filter(s => s.strokeIds.some(id => item.candidateStrokeIds.includes(id)));
    candidates.push({ id: `candidate-${item.id}`, source: "LEARNED_LAYOUT", strokeIds: item.candidateStrokeIds,
      bounds: computeBounds(pen.filter(s => item.candidateStrokeIds.includes(s.id))), evidence: [item.rawLabel, ...item.flags],
      disposition: relationPass?.decisions.some(d => d.layoutCandidateId === `candidate-${item.id}` && d.decision === "MERGE") ? "ACCEPTED_WITH_BOUNDED_FRACTION_PREFIX_RELATION"
        : intersecting.length > 1 ? "KEPT_AS_ALTERNATIVE; relation evidence insufficient (see trace)" : "ALTERNATIVE_NOT_OWNER; geometry completes box-boundary fragments", competingIds: intersecting.map(s => `candidate-${s.id}`) });
  }
  for (const scope of scopes.filter(s => s.kind === "MATH" && learned.some(l => l.strokeIds.some(id => s.strokeIds.includes(id)) && l.strokeIds.length < s.strokeIds.length)))
    candidates.push({ id: `completion-${scope.id}`, source: "CLUSTER_COMPLETION", strokeIds: scope.strokeIds, bounds: computeBounds(pen.filter(s => scope.strokeIds.includes(s.id))), evidence: ["Complete bounded geometry cluster instead of partial detector membership"], disposition: "SAME_AS_ACTIVE_SCOPE; no duplicate inference", competingIds: [`candidate-${scope.id}`] });
  const relations = scopes.filter(s => s.flags.includes("MULTI_ROW_DELIMITER_UNRESOLVED")).map(s => { const box = computeBounds(pen.filter(p => s.strokeIds.includes(p.id))); return { kind: "UNKNOWN" as const, strokeIds: s.strokeIds, childScopeIds: scopes.filter(other => { const b = computeBounds(pen.filter(p => other.strokeIds.includes(p.id))); return other !== s && b.left > box.right && b.top <= box.bottom + body / 1123 * .35 && b.bottom >= box.top - body / 1123 * .35; }).map(other => other.id), reason: "Tall left delimiter spans independent rows; SYSTEM vs ALTERNATIVES requires human review" }; });
  const integrity = scopeIntegrity(source, scopes);
  if (integrity.missing.length || integrity.duplicateOwnership.length || integrity.unknown.length) throw Error("CANDIDATE_SOURCE_INTEGRITY_FAILED");
  trace.push({ stage: "RECONCILIATION", integrity, scopes: scopes.map(s => ({ id: s.id, strokeIds: s.strokeIds, routing: routing[s.id] })), detectorStatus: perception.status });
  return { version: "multi-hypothesis/1", mode, bodyHeightPx: body, scopes, candidates, routing, relations,
    readingOrder: scopes.length <= 1 ? "PROPOSED" : "AMBIGUOUS", trace, durationMs: performance.now() - start };
}
