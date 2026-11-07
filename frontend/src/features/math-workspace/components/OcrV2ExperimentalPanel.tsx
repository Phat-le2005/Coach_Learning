"use client";
import { sha256Hex } from "../utils/ocr-digest";
import { generateUuid } from "../utils/ink-math";
import { useEffect, useMemo, useRef, useState } from "react";
import type { InkStroke } from "@/lib/api/contracts";
import { diagnoseMathScope } from "../utils/ocr-model-diagnostics";
import { mathProbeOffer, runLabMathProbe, type MathProbeEvidence } from "../utils/ocr-v2-math-probe";
import { applyAutomaticTextProposal, planAutomaticRouting, recognizeAutomaticText, type AutomaticRoute } from "../utils/ocr-automatic-routing";
import type { HtrEvidence } from "../utils/vietnamese-htr";
import { recognizeUniMumer, uniMumerHealth, type MathRecognizer, type UniMumerEvidence, type UniMumerHealth } from "../utils/unimumer-recognizer";
import { constructScopeCandidates, type ScopeConstruction } from "../utils/ocr-v2-scope-candidates";
import { detectStructuralCandidates } from "../utils/structural-candidate-engine";
import { approveContentUnit, applyOcrToContentUnit, editContentUnit, editContainerRelation,
  confirmTranscriptionReadingOrder, getOrderedReviewUnits, getRootContentUnits, setSiblingReadingOrder,
  projectTranscriptionToLegacySteps, validateSolutionTranscriptionIR, type SolutionTranscriptionIR } from "../utils/structured-transcription-ir";
import { renderOcrLatexHtml } from "../utils/ocr-math-preview";
import { OcrMathPreview } from "./OcrMathPreview";
import { createOcrEvalCapture } from "../utils/ocr-eval-capture";
import { segmentPageInk } from "../utils/page-ocr";
import { buildScopeIR, cropLabScope, csvRows, editLabScopeKind, fromPixel, geometryPerception, groupIrUnits, INFERENCE_LIMIT,
  lassoIds, mapLayoutToScopes, PAGE, reassignScope, renderLabPage, renderTransform, scopeIntegrity, sourceKey, validateLabSource,
  type LabProfile, type LabSource, type PerceptionResult, type RouteKind, type ScopeProposal } from "../utils/ocr-v2-experimental";
import styles from "./OcrV2ExperimentalPanel.module.css";

type Health = { status: string; models?: Record<string, { status: string; modelId: string }>; htr?: { status: string }; error?: string };
type Recognition = { scopeId: string; strokeIds: string[]; pageIndex: number; sourceRevision: number; sourceStrokeSha256: string; timestamp: string; wrapperInvocations: number; diagnosticInvocations: number; inferenceCalls: number | null; verifiedInferenceCalls?: number; wrapperLatex: string | null; error?: string; ms: number; diagnostic?: Awaited<ReturnType<typeof diagnoseMathScope>>; recognizer?: MathRecognizer; unimumerInvocations?: number; unimumer?: UniMumerEvidence; unimumerError?: string; inputCrop?: string; transcriptModel?: string; htrInvocations?: number; htr?: HtrEvidence };
type RoutingOutcome = { scopeId: string; kind: RouteKind; status: string; reason: string; inferenceCalls: number | null; verifiedInferenceCalls?: number; rawOutput?: string | null; selectedOutput?: string | null; durationMs?: number };
type AutoRow = AutomaticRoute & { crop: string; status: string; rawOutput?: string | null; selectedOutput?: string | null; durationMs?: number; inferenceCalls: number | null };
const download = (name: string, data: unknown, mime = "application/json") => {
  const blob = new Blob([typeof data === "string" ? data : JSON.stringify(data, null, 2)], { type: mime });
  const url = URL.createObjectURL(blob), a = document.createElement("a"); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};
async function digest(data: string) { return sha256Hex(data); }

/** Isolated experiment: no API client for ink, steps, batches or grading is imported. */
export function OcrV2ExperimentalPanel({ source, onClose }: { source: LabSource; onClose?: () => void }) {
  const [snapshot, setSnapshot] = useState(() => structuredClone(source));
  const [profile, setProfile] = useState<LabProfile>("HYBRID"), [health, setHealth] = useState<Health>({ status: "CHECKING" });
  const [recognizer,setRecognizer]=useState<MathRecognizer>("COMER"),[uniHealth,setUniHealth]=useState<UniMumerHealth>({status:"CHECKING"}),[promptId,setPromptId]=useState<"reference"|"strict">("reference");
  const uniAbort=useRef<AbortController|null>(null);
  const [construction, setConstruction] = useState<ScopeConstruction | null>(null), [routingOutcomes, setRoutingOutcomes] = useState<RoutingOutcome[]>([]);
  const [automaticRows, setAutomaticRows] = useState<AutoRow[]>([]);
  const [showScopeBoxes, setShowScopeBoxes] = useState(true);
  const [perception, setPerception] = useState<PerceptionResult | null>(null), [scopes, setScopes] = useState<ScopeProposal[]>([]);
  const [ir, setIr] = useState<SolutionTranscriptionIR | null>(null), [selected, setSelected] = useState("");
  const [records, setRecords] = useState<Recognition[]>([]), [runs, setRuns] = useState<unknown[]>([]), [archives, setArchives] = useState<unknown[]>([]);
  const [mathProbes, setMathProbes] = useState<MathProbeEvidence[]>([]);
  const [busy, setBusy] = useState(false), [progress, setProgress] = useState("Chưa chạy"), [error, setError] = useState("");
  const [picked, setPicked] = useState<string[]>([]), [multi, setMulti] = useState<string[]>([]), [lasso, setLasso] = useState(false);
  const [polygon, setPolygon] = useState<{ x: number; y: number; pressure: number }[]>([]), [manualKind, setManualKind] = useState<RouteKind>("MATH");
  const [cut, setCut] = useState(50), [relation, setRelation] = useState<"SYSTEM" | "ALTERNATIVES" | "FRACTION" | "INDEPENDENT" | "UNKNOWN">("UNKNOWN");
  const [consent, setConsent] = useState(false), [padding, setPadding] = useState(16);
  const [mounted, setMounted] = useState(false);
  const [annotations, setAnnotations] = useState<{ id: string; strokeIds: string[]; kind: RouteKind; transcript: string }[]>([]);
  const [annotationText, setAnnotationText] = useState(""), [humanVerified, setHumanVerified] = useState(false);
  const [lassoEvidence, setLassoEvidence] = useState<unknown[]>([]);
  const sourceRef = useRef(source); sourceRef.current = source;
  const irRef = useRef(ir); irRef.current = ir;
  const lock = useRef(false), calls = useRef(0), alive = useRef(true), pathRef = useRef<typeof polygon>([]);
  useEffect(() => { alive.current = true; setMounted(true); return () => { alive.current = false;uniAbort.current?.abort(); }; }, []);
  useEffect(() => { if (!irRef.current) setSnapshot(structuredClone(source)); }, [source]);
  const stale = sourceKey(source) !== sourceKey(snapshot);
  useEffect(()=>{if(stale)uniAbort.current?.abort();},[stale]);
  useEffect(() => {
    const old = irRef.current;
    if (!stale || !old || (!old.approvedUnitCount && old.readingOrderStatus !== "CONFIRMED")) return;
    setArchives(a => [...a, { reason: "SOURCE_CHANGED_APPROVAL_INVALIDATED", ir: old, source: snapshot }]);
    const pending = validateSolutionTranscriptionIR({ ...old, reviewStatus: "NEEDS_REVIEW", readingOrderStatus: "AMBIGUOUS", approvedUnitCount: 0,
      contentUnits: old.contentUnits.map(u => ({ ...u, reviewStatus: "NEEDS_REVIEW" })), provenance: { ...old.provenance, updatedAt: new Date().toISOString() } });
    irRef.current = pending; setIr(pending);
  }, [stale, snapshot]);
  const rendered = useMemo(() => { if (!mounted) return { value: null, error: "" }; try { return { value: renderLabPage(snapshot, renderTransform(padding)), error: "" }; } catch (e) { return { value: null, error: String(e) }; } }, [snapshot, padding, mounted]);
  const rows = ir ? getOrderedReviewUnits(ir.contentUnits) : [], unit = ir?.contentUnits.find(u => u.id === selected);
  const scope = scopes.find(s => `unit-${s.id}` === selected), highlighted = picked.length ? picked : unit?.sourceStrokeIds ?? [];
  const record = records.filter(r => r.scopeId === scope?.id).at(-1);
  const probeOffer = mathProbeOffer(scope);
  const snapshotProbes = mathProbes.filter(p => p.sourceKey === sourceKey(snapshot));
  const selectedProbe = snapshotProbes.filter(p => p.scopeId === scope?.id
    && JSON.stringify(p.sourceStrokeIds) === JSON.stringify(snapshot.strokes.filter(s => s.tool === "PEN" && scope.strokeIds.includes(s.id)).map(s => s.id))).at(-1);
  const integrity = scopeIntegritySafe();
  function scopeIntegritySafe() { try { return scopeIntegrity(snapshot, scopes); } catch (e) { return { error: String(e) }; } }
  const refreshHealth = async () => { try { const response = await fetch("/api/ocr-v2-lab", { cache: "no-store" }); const value = await response.json(); setHealth({ ...value, status: response.ok ? value.status : "UNAVAILABLE" }); } catch { setHealth({ status: "UNAVAILABLE", error: "Sidecar chưa chạy/cấu hình. Có thể dùng V1/V2 hoặc scope thủ công." }); } };
  useEffect(() => { void refreshHealth(); }, []);
  const refreshUni=async()=>setUniHealth(await uniMumerHealth());
  useEffect(()=>{void refreshUni();},[]);
  function change(action: (previous: SolutionTranscriptionIR) => SolutionTranscriptionIR) {
    if (stale || !irRef.current) return;
    try { const next = action(irRef.current); irRef.current = next; setIr(next); setError(""); } catch (e) { setError(String(e)); }
  }
  async function recognize(list: ScopeProposal[], input: LabSource, explicitScope = false, engine: MathRecognizer = recognizer) {
    const key = sourceKey(input);
    const outcomes: RoutingOutcome[] = list.filter(s => s.strokeIds.length).map(s => ({ scopeId: s.id, kind: s.kind,
      status: s.kind === "MATH" ? "QUEUED_UNCONFIRMED" : "UNRESOLVED",
      reason: s.kind === "MATH" ? s.flags.join("; ") : s.kind === "TEXT" ? "TEXT_RECOGNIZER_MISSING; manual transcription" : s.flags.join("; ") || "UNRESOLVED_KIND", inferenceCalls: 0 }));
    setRoutingOutcomes(outcomes);
    const update = (id: string, patch: Partial<RoutingOutcome>) => { const row = outcomes.find(o => o.scopeId === id)!; Object.assign(row, patch); setRoutingOutcomes(outcomes.map(o => ({ ...o }))); };
    for (const s of list.filter(s => s.kind === "MATH" && s.strokeIds.length)) {
      if (!explicitScope && s.flags.some(f => f.startsWith("BOUNDARY_CROSSING") || f.startsWith("OVERLAPPING_CANDIDATES"))) {
        update(s.id, { status: "BLOCKED_GEOMETRY_AMBIGUOUS", reason: "OLD_BASELINE_BOUNDARY_OR_OVERLAP_GATE" }); continue;
      }
      if (!alive.current || sourceKey(sourceRef.current) !== key) { update(s.id, { status: "CANCELLED_SOURCE_CHANGED" }); continue; }
      if (calls.current >= INFERENCE_LIMIT) { update(s.id, { status: "BLOCKED_INFERENCE_BUDGET", reason: `Limit ${INFERENCE_LIMIT} attempts per action; retry selected scope` }); continue; }
      const ink = input.strokes.filter(st => st.tool === "PEN" && s.strokeIds.includes(st.id));
      const started = performance.now(); const evidence: Recognition = { scopeId: s.id, strokeIds: ink.map(st => st.id), pageIndex: input.pageIndex, sourceRevision: input.sourceRevision, sourceStrokeSha256: await digest(JSON.stringify(input.strokes)), timestamp: new Date().toISOString(), wrapperInvocations: 0, diagnosticInvocations: 0, inferenceCalls: 0, wrapperLatex: null, ms: 0 };
      evidence.recognizer=engine;evidence.unimumerInvocations=0;evidence.inferenceCalls=0;
      let verifiedCalls=0,uncertainInference=false;
      const controller=new AbortController();uniAbort.current=controller;
      setProgress(`${engine} ${s.id} / ${ink.length} strokes / ${calls.current + 1}/${INFERENCE_LIMIT}`);
      if(engine!=="UNIMUMER"){
        try {
          calls.current++; evidence.diagnosticInvocations++;
          evidence.diagnostic = await diagnoseMathScope(ink);
          if(evidence.diagnostic.status==="COMPLETED"){
            verifiedCalls++;evidence.wrapperLatex=evidence.diagnostic.frontendAcceptedLatex;evidence.transcriptModel="CoMER";
          }else evidence.error=evidence.diagnostic.status;
        }catch(e){evidence.error=String(e);uncertainInference=true;}
      }
      if(engine!=="COMER"){
        if(calls.current>=INFERENCE_LIMIT)evidence.unimumerError="INFERENCE_BUDGET_EXHAUSTED";
        else try{
          // Render selected ink only: a page crop could include unrelated strokes
          // inside the same box, unlike CoMER's exact vector membership input.
          const page=renderLabPage({...input,strokes:ink},renderTransform(padding));
          evidence.inputCrop=cropLabScope(page.canvas,ink,page.transform);
          calls.current++;evidence.unimumerInvocations++;
          evidence.unimumer=await recognizeUniMumer(evidence.inputCrop,evidence.strokeIds,promptId,controller.signal);
          if(evidence.unimumer.status==="COMPLETED"){
            verifiedCalls++;
            if(engine==="UNIMUMER"){
              evidence.wrapperLatex=renderOcrLatexHtml(evidence.unimumer.normalizedLatex)?evidence.unimumer.normalizedLatex:null;evidence.transcriptModel="Uni-MuMER";
            }
          }
        }catch(e){evidence.unimumerError=String(e);uncertainInference=true;}
      }
      // Compare keeps CoMER as the transcript proposal; the second output is separate evidence.
      // Uni-MuMER failure is never relabeled as a successful fallback prediction.
      if(evidence.wrapperLatex&&alive.current&&sourceKey(sourceRef.current)===key&&irRef.current){
        const next=applyOcrToContentUnit(irRef.current,`unit-${s.id}`,evidence.wrapperLatex);irRef.current=next;setIr(next);
      }
      evidence.verifiedInferenceCalls=verifiedCalls;evidence.inferenceCalls=uncertainInference?null:verifiedCalls;
      update(s.id,{status:evidence.wrapperLatex?"MODEL_OUTPUT_UNCONFIRMED":verifiedCalls?"RAW_OUTPUT_SYNTAX_UNSUPPORTED":"RUNTIME_OR_MODEL_ERROR",reason:[evidence.error,evidence.unimumerError,...s.flags].filter(Boolean).join("; "),inferenceCalls:evidence.inferenceCalls,verifiedInferenceCalls:verifiedCalls,
        rawOutput:evidence.diagnostic?.status==="COMPLETED"?evidence.diagnostic.rawLatex:evidence.unimumer?.rawOutput,selectedOutput:evidence.wrapperLatex,durationMs:performance.now()-started});
      evidence.ms = performance.now() - started;
      if (alive.current) setRecords(previous => [...previous, evidence]);
    }
    return outcomes;
  }
  async function recognizeAutomatic(input: LabSource, active: ScopeProposal[], proposal: PerceptionResult) {
    const key=sourceKey(input), plan=planAutomaticRouting(input,active,proposal);
    const rows:AutoRow[]=plan.map(route=>{
      const ink=input.strokes.filter(s=>route.sourceStrokeIds.includes(s.id)),page=renderLabPage({...input,strokes:ink},renderTransform(padding));
      return {...route,crop:cropLabScope(page.canvas,ink,page.transform),status:route.action==="DEFER"?"DEFERRED_UNRESOLVED":"QUEUED_UNCONFIRMED",inferenceCalls:0};
    });
    setAutomaticRows(rows.map(r=>({...r})));
    const math=await recognize(active.filter(s=>plan.some(r=>r.scopeId===s.id&&r.action==="COMER")),input,false,"COMER");
    for(const r of rows){const result=math.find(m=>m.scopeId===r.scopeId);if(result)Object.assign(r,{status:result.status,rawOutput:result.rawOutput,selectedOutput:result.selectedOutput,durationMs:result.durationMs,inferenceCalls:result.inferenceCalls});}
    for(const row of rows.filter(r=>r.action==="VIETOCR")){
      if(!alive.current||sourceKey(sourceRef.current)!==key){row.status="CANCELLED_SOURCE_CHANGED";continue;}
      if(calls.current>=INFERENCE_LIMIT){row.status="BLOCKED_INFERENCE_BUDGET";continue;}
      const scope=active.find(s=>s.id===row.scopeId)!,controller=new AbortController();uniAbort.current=controller;
      setProgress(`VietOCR ${scope.id} · ${scope.strokeIds.length} nét · output chưa xác nhận`);
      const attempt:Recognition={scopeId:scope.id,strokeIds:row.sourceStrokeIds,pageIndex:input.pageIndex,sourceRevision:input.sourceRevision,sourceStrokeSha256:await digest(JSON.stringify(input.strokes)),timestamp:new Date().toISOString(),wrapperInvocations:0,diagnosticInvocations:0,htrInvocations:1,inferenceCalls:null,wrapperLatex:null,ms:0,transcriptModel:"VietOCR",inputCrop:row.crop};
      const start=performance.now();calls.current++;
      try{
        const evidence=await recognizeAutomaticText(input,scope,proposal,row.crop,controller.signal);
        attempt.htr=evidence;attempt.wrapperLatex=evidence.rawTranscript;attempt.inferenceCalls=1;attempt.verifiedInferenceCalls=1;
        row.rawOutput=evidence.rawTranscript;row.selectedOutput=evidence.normalizedTranscript;row.inferenceCalls=1;row.status="MODEL_OUTPUT_UNCONFIRMED";
        if(sourceKey(sourceRef.current)===key&&irRef.current&&alive.current){
          const unit=irRef.current.contentUnits.find(u=>u.id===`unit-${scope.id}`);
          if(unit?.kind==="TEXT"&&evidence.rawTranscript.trim()){const next=applyAutomaticTextProposal(irRef.current,unit.id,evidence.rawTranscript);irRef.current=next;setIr(next);}
        }else row.status="STALE_SOURCE_CHANGED; evidence not applied";
      }catch(e){attempt.error=String(e);row.status=`RUNTIME_OR_MODEL_ERROR: ${String(e)}`;row.inferenceCalls=null;}
      attempt.ms=performance.now()-start;row.durationMs=attempt.ms;if(alive.current)setRecords(old=>[...old,attempt]);
    }
    const order=getOrderedReviewUnits(irRef.current?.contentUnits??[]).map(r=>r.unit.id);
    rows.sort((a,b)=>order.indexOf(`unit-${a.scopeId}`)-order.indexOf(`unit-${b.scopeId}`));
    if(alive.current)setAutomaticRows(rows.map(r=>({...r})));
    const outcomes:RoutingOutcome[]=rows.map(r=>({scopeId:r.scopeId,kind:r.proposedKind,status:r.status,reason:r.reasons.join('; '),inferenceCalls:r.inferenceCalls,rawOutput:r.rawOutput,selectedOutput:r.selectedOutput,durationMs:r.durationMs}));
    setRoutingOutcomes(outcomes);return outcomes;
  }
  async function run(automatic=false) {
    if (lock.current) return; lock.current = true; setBusy(true); setError(""); calls.current = 0;
    try {
      const input = structuredClone(sourceRef.current), pen = validateLabSource(input), render = renderLabPage(input, renderTransform(padding)),mode=automatic?"HYBRID":profile;
      if(!automatic)setAutomaticRows([]);
      setSnapshot(input); const started = performance.now(); let proposal: PerceptionResult;
      setProgress("Render A4 → detector local…");
      if (mode === "GEOMETRY") proposal = { status: "GEOMETRY_EVIDENCE_ONLY", model: "INK_GEOMETRY", regions: [] };
      else if (mode === "V1" || mode === "V2") proposal = geometryPerception(pen, mode, render.transform);
      else {
        try {
          const response = await fetch("/api/ocr-v2-lab", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: mode === "HYBRID" ? "LAYOUT_M" : mode, png: render.png }), signal: AbortSignal.timeout(90000) });
          const result = await response.json();
          proposal = { ...result, model: result.model ?? mode, status: result.status ?? "ERROR", regions: Array.isArray(result.regions) ? result.regions : [], error: result.error ?? (!response.ok ? `HTTP_${response.status}` : undefined) };
        } catch (e) { proposal = { status: "SIDECAR_UNAVAILABLE", model: mode, regions: [], error: String(e) }; }
      }
      const mapping = proposal.regions.length ? proposal : geometryPerception(pen, "V2", render.transform, true);
      const built = mode === "HYBRID" || mode === "GEOMETRY" ? constructScopeCandidates(input, proposal, render.transform, mode) : null;
      const nextScopes = built ? built.scopes : mapLayoutToScopes(input, mapping, render.transform);
      setConstruction(built);
      setPerception(proposal); const old = irRef.current;
      const sameSource = old && JSON.stringify(old.sourceSnapshot.strokes) === JSON.stringify(pen) && old.pageIndex === input.pageIndex && old.sourceRevision === Math.max(1, input.sourceRevision);
      // Rerunning perception cannot overwrite a reviewed scope/correction. New proposals remain in raw run history.
      const preserve = sameSource && (old.contentUnits.some(u => u.reviewStatus === "APPROVED" || u.isManuallyCorrected)
        || scopes.some(s => s.flags.includes("MANUAL_SCOPE_NOT_AUTOMATIC") || s.flags.includes("USER_ROUTING_OVERRIDE")));
      const active = preserve ? scopes : nextScopes;
      if (old) setArchives(a => [...a, { reason: "BEFORE_RERUN", ir: old, scopes, source: snapshot, recognition: records, annotations }]);
      if (old && !sameSource) { setRecords([]); setAnnotations([]); setHumanVerified(false); }
      const nextIr = preserve ? old : buildScopeIR(input, active, sameSource ? old : undefined);
      irRef.current = nextIr; setIr(nextIr); setScopes(active); setSelected(getRootContentUnits(nextIr.contentUnits)[0]?.id ?? "");
      const inputHash = await digest(JSON.stringify(input));
      setRuns(previous => [...previous, { sourceSha256: inputHash, sourceKey: keyForExport(input), profile:mode, automatic, perception: proposal, mappingStatus: mapping.status, proposedScopes: nextScopes,
        construction: built, preservedReviewedScopes: Boolean(preserve), elapsedMs: performance.now() - started, transform: render.transform, timestamp: new Date().toISOString() }]);
      const outcomes = automatic?await recognizeAutomatic(input,active,proposal):await recognize(active, input);
      const completed = outcomes.reduce((n, o) => n + (o.verifiedInferenceCalls ?? o.inferenceCalls ?? 0), 0), unresolved = outcomes.filter(o => o.status !== "MODEL_OUTPUT_UNCONFIRMED").length;
      setProgress(pen.length ? `Bản nháp · ${completed} inference (${automatic?"CoMER/VietOCR":recognizer}) đã xác minh / ${calls.current} lần gọi · ${unresolved} scope chưa nhận diện; mọi output cần review.` : "Trang trống · không inference CoMER");
      await refreshHealth();
    } catch (e) { setError(String(e)); setProgress("Không chạy được; nét gốc được giữ nguyên."); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  function keyForExport(input: LabSource) { return { pageIndex: input.pageIndex, sourceRevision: input.sourceRevision, sourceKind: input.sourceKind, datasetSplit: input.datasetSplit }; }
  async function retry() {
    if (!scope || scope.kind !== "MATH" || lock.current || stale) return;
    lock.current = true; setBusy(true); calls.current = 0;
    try { await recognize([scope], snapshot, true); setProgress("Đã lưu thêm raw evidence; correction thủ công giữ nguyên."); }
    finally { lock.current = false; setBusy(false); }
  }
  async function probeUnknown() {
    if (!scope || !probeOffer.eligible || lock.current || stale) return;
    lock.current = true; setBusy(true); setError("");
    setProgress("Math Probe do bạn yêu cầu · CoMER · giữ nguyên UNKNOWN và bản chép.");
    try {
      const evidence = await runLabMathProbe(snapshot, scope, () => sourceKey(sourceRef.current));
      if (alive.current) {
        setMathProbes(previous => [...previous, evidence]);
        setProgress(`Math Probe: ${evidence.status} · chỉ thêm evidence, không đổi loại hoặc xác nhận nội dung.`);
      }
    } catch (e) { setError(String(e)); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  function applyScope(ids: string[]) {
    if (!ir || busy || stale || !ids.length) return;
    try {
      const ordered = snapshot.strokes.filter(s => s.tool === "PEN" && ids.includes(s.id)).map(s => s.id);
      const id = `manual-${generateUuid()}`, next = reassignScope(scopes, ordered, id, manualKind);
      setArchives(previous => [...previous, { reason: "MANUAL_SCOPE_CHANGE; prior corrections retained", ir, scopes, source: snapshot }]);
      const nextIr = buildScopeIR(snapshot, next, ir); irRef.current = nextIr; setIr(nextIr); setScopes(next); setSelected(`unit-${id}`); setPicked([]); setMulti([]);
      setProgress("Phạm vi đã đổi; bản review trước giữ trong Lịch sử. Hãy đọc lại scope mới.");
    } catch (e) { setError(String(e)); }
  }
  function changeKind(kind: RouteKind) {
    if (!scope || busy || stale) return;
    setScopes(previous => previous.map(s => s.id === scope.id ? { ...s, kind, flags: [...s.flags, "USER_ROUTING_OVERRIDE"] } : s));
    change(previous => editLabScopeKind(previous, { ...scope, kind }));
  }
  function move(direction: number) {
    if (!ir || !unit) return; const row = rows.find(r => r.unit.id === selected)!;
    const ids = rows.filter(r => r.parentId === row.parentId).map(r => r.unit.id), index = ids.indexOf(selected), to = index + direction;
    if (to < 0 || to >= ids.length) return; [ids[index], ids[to]] = [ids[to], ids[index]];
    change(previous => setSiblingReadingOrder(previous, row.parentId, ids));
  }
  async function exportPackage() {
    if (!ir || !rendered.value || !consent) return;
    const exportSource = { ...snapshot, consent };
    const sourceSha256 = await digest(JSON.stringify(exportSource)), projection = projectTranscriptionToLegacySteps(ir);
    const packageData = { schemaVersion: "ocr-v2-experimental/1", createdAt: new Date().toISOString(), source: exportSource, sourceSha256,
      stale, effectiveReviewStatus: stale ? "STALE_REVIEW_REQUIRED" : ir.reviewStatus, perception, scopes, integrity,
      recognizer, uniMumerHealth: uniHealth, recognition: records, automaticRecognition:automaticRows,
      automaticConfig:automaticRows.length?{mathRecognizer:"COMER",textRecognizer:"VIETOCR",kindDecisions:"UNCALIBRATED_EVIDENCE_PROPOSALS",autoApprove:false}:null,
      mathProbes: mathProbes.map(({ sourceKey: _transientInkKey, ...evidence }) => evidence),
      routingRecovery: scopes.map(s => ({ scopeId: s.id, originalKind: s.kind, ...mathProbeOffer(s), trigger: "USER_ONLY; never auto probe" })),
      recognizerInvocationCount: records.reduce((n, r) => n + r.wrapperInvocations + r.diagnosticInvocations + (r.unimumerInvocations ?? 0)+(r.htrInvocations??0), 0) + mathProbes.reduce((n, p) => n + p.invocationCount, 0),
      modelInferenceCalls: [...records, ...mathProbes].every(r => r.inferenceCalls !== null) ? [...records, ...mathProbes].reduce((n, r) => n + r.inferenceCalls!, 0) : "NOT_AVAILABLE; runtime error may occur after inference",
      construction, routingOutcomes, runs, archives, lassoEvidence,
      ir, projection, structuralProposals: detectStructuralCandidates(snapshot.strokes),
      render: { transform: rendered.value.transform, supportIndex: rendered.value.supportIndex, png: rendered.value.png,
        crops: scopes.filter(s => s.strokeIds.length).map(s => ({ scopeId: s.id, png: cropLabScope(rendered.value!.canvas, snapshot.strokes.filter(st => s.strokeIds.includes(st.id)), rendered.value!.transform) })) },
      annotation: { status: humanVerified && annotations.length ? "HUMAN_VERIFIED" : "DRAFT", sourceSha256, consent, datasetSplit: snapshot.datasetSplit, writerId: snapshot.writerId ?? "NOT_AVAILABLE", groups: annotations, labelSource: "USER_DECLARED_INDEPENDENT_OF_OCR" },
      metrics: { accuracy: "NOT_MEASURED", regionRecall: "NOT_MEASURED", typeConfusion: "NOT_MEASURED", scopePrecisionRecall: "NOT_MEASURED", falseSplitMerge: "NOT_MEASURED", readingOrderErrors: "NOT_MEASURED", mathExactCER: "NOT_MEASURED", vietnameseCERWER: "NOT_MEASURED", correctionBurden: "NOT_MEASURED", reviewArchiveCount: archives.length },
      privacy: "Current local ink only; no credentials/cookies/env/problem answer; no grading payload" };
    download("ocr-v2-package.json", packageData);
    download("ocr-v2-comparison.csv", csvRows(records.map(r => ({ scope: r.scopeId, strokeIds: r.strokeIds.join(" "), recognizer: r.recognizer ?? "COMER", unimumerRaw: r.unimumer?.rawOutput, unimumerMs: r.unimumer?.durationMs, unimumerError: r.unimumerError, output: r.wrapperLatex, rawPreRepair: r.diagnostic?.status === "COMPLETED" ? r.diagnostic.rawLatex : "NOT_AVAILABLE", ms: r.ms, error: r.error, labelStatus: "NOT_MEASURED" }))), "text/csv;charset=utf-8");
  }
  async function exportLabels() {
    const capture = createOcrEvalCapture(snapshot.pageIndex, snapshot.strokes, segmentPageInk(snapshot.strokes));
    const bytes = JSON.stringify(capture, null, 2), captureSha256 = await digest(bytes);
    download("ocr-v2-source-capture.json", bytes);
    download("ocr-v2-human-annotation.json", { schemaVersion: 1, sampleId: `page-${snapshot.pageIndex + 1}`, captureFile: "ocr-v2-source-capture.json", captureSha256,
      annotationStatus: humanVerified && annotations.length ? "HUMAN_VERIFIED" : "DRAFT", annotator: { kind: "HUMAN", id: snapshot.writerId }, labelSource: "HUMAN_INDEPENDENT_OF_OCR",
      writerId: snapshot.writerId, datasetSplit: snapshot.datasetSplit, consent,
      expectedGroups: annotations.map(a => ({ groupId: a.id, strokeIds: a.strokeIds, contentKind: a.kind === "MIXED" ? "UNKNOWN" : a.kind,
        ...(a.kind === "MATH" ? { latex: a.transcript } : { text: a.transcript }), notes: a.kind === "MIXED" ? "Mixed line, subscopes unresolved" : "User-declared independent source transcription" })) });
  }
  function pointer(e: React.PointerEvent<SVGSVGElement>) {
    const point = e.currentTarget.createSVGPoint(); point.x = e.clientX; point.y = e.clientY;
    const matrix = e.currentTarget.getScreenCTM(); if (!matrix) throw new Error("SVG_TRANSFORM_UNAVAILABLE");
    const local = point.matrixTransform(matrix.inverse());
    return { x: Math.max(0, Math.min(1, local.x / PAGE.width)), y: Math.max(0, Math.min(1, local.y / PAGE.height)), pressure: .5 };
  }
  return <section className={styles.panel} aria-label="OCR V2 Experimental" data-testid="ocr-v2-panel" aria-busy={busy} data-stale={stale}>
    <header><h2>OCR V2 Experimental · Trang {source.pageIndex + 1}</h2>{onClose && <button onClick={onClose}>Đóng thử nghiệm</button>}</header>
    <p>Local · bản chép thử nghiệm · không lưu bước/chấm bài. Detector score và beam score chưa calibrated.</p>
    <p role="status" data-testid="v2-progress">{progress}</p>
    {stale && <p role="alert">Nét hoặc revision đã đổi. Approval cũ đã stale; chạy lại trên nguồn mới trước khi xác nhận.</p>}
    {(error || rendered.error) && <p role="alert">{error || rendered.error}</p>}
    <div className={styles.controls}>
      <label>Recognizer <select aria-label="Math recognizer" value={recognizer} disabled={busy} onChange={e=>setRecognizer(e.target.value as MathRecognizer)}><option value="COMER">CoMER — Baseline</option><option value="UNIMUMER">Uni-MuMER Qwen3.5-2B — Local Q4_K_M</option><option value="COMPARE">Compare — cùng stroke IDs</option></select></label>
      {recognizer!=="COMER"&&<label>Prompt <select aria-label="Uni-MuMER prompt" value={promptId} disabled={busy} onChange={e=>setPromptId(e.target.value as typeof promptId)}><option value="reference">Reference transcription</option><option value="strict">Strict / preserve mistakes</option></select></label>}
      <label>Chế độ <select aria-label="Chế độ OCR V2" value={profile} disabled={busy} onChange={e => setProfile(e.target.value as LabProfile)}>
        <option value="HYBRID">Hybrid: geometry + Layout-M (thử nghiệm)</option><option value="GEOMETRY">Geometry candidates (không detector)</option><option value="LAYOUT_M">Layout-M cũ (baseline box/label)</option><option value="LAYOUT_V3" disabled={!health.models || ["MISSING", "UNSUPPORTED_RUNTIME"].includes(health.models.LAYOUT_V3?.status ?? "MISSING")}>PP-DocLayoutV3 ({health.models?.LAYOUT_V3?.status ?? "cần weights"})</option><option value="V1">V1 baseline (giả định toán)</option><option value="V2">V2 baseline (giả định toán)</option></select></label>
      <label>Padding <input aria-label="Padding renderer" type="number" min={0} max={64} value={padding} disabled={busy || !!ir} onChange={e => setPadding(Number(e.target.value))} /></label>
      <button onClick={() => void run()} disabled={busy} data-testid="v2-run">{busy ? "Đang chạy…" : "Thử OCR V2 toàn trang"}</button>
      <button onClick={() => void run(true)} disabled={busy} data-testid="v2-auto-run">Thử OCR tự động toàn trang</button>
      <button onClick={() => void refreshHealth()}>Kiểm tra detector/HTR</button>
      <button onClick={()=>void refreshUni()}>Kiểm tra Uni-MuMER local</button>
    </div>
    <p data-testid="unimumer-health">Uni-MuMER: {uniHealth.status} · {uniHealth.profile??"chưa chạy"} · GPU layers {uniHealth.gpuLayers??"NOT_AVAILABLE"} · projector {uniHealth.projectorDevice??"NOT_AVAILABLE"}. {uniHealth.error}</p>
    {recognizer==="COMPARE"&&<p>Hai model nhận cùng stroke IDs. Bản chép IR dùng đề xuất CoMER; Uni-MuMER hiển thị riêng để đối chiếu, không tự chọn model theo output hoặc GT.</p>}
    <p data-testid="v2-detector-status">Detector: {perception?.status ?? health.status} · {perception?.model ?? profile} · {perception?.regions.length ?? 0} raw boxes. HTR: {health.htr?.status ?? "UNRESOLVED_MANUAL"}.</p>
    {perception && !perception.regions.length && <p role="note">{construction ? "Không dùng được box detector; geometry vẫn tạo ứng viên độc lập, loại chưa chắc chắn được giữ unresolved." : "FALLBACK geometry V2, type UNKNOWN; cần review."} Raw detector: {perception.error ?? perception.status}.</p>}
    <details><summary>Health / model provenance</summary><pre>{JSON.stringify({ health, manifest: perception?.manifest, timings: perception?.timings }, null, 2)}</pre></details>
    {automaticRows.length>0&&<section data-testid="v2-automatic-preview"><h3>Bản chép tự động · {ir?.readingOrderStatus??"AMBIGUOUS"} · chưa xác nhận</h3>
      <p>CoMER cho MATH có evidence; VietOCR cho dòng TEXT đủ evidence. Điểm hình học không phải xác suất đúng; UNKNOWN/MIXED được giữ lại.</p>
      {automaticRows.map((r,i)=><article key={r.scopeId} data-testid={`auto-scope-${r.scopeId}`} style={{borderBottom:'1px solid #aaa',padding:8}}>
        <strong>{i+1}. {r.scopeId} · {r.sourceStrokeIds.length} nét · {r.originalKind} → {r.proposedKind} · {r.action}</strong>
        <p>{r.reasons.join('; ')} · {r.status} {r.durationMs!=null?`· ${Math.round(r.durationMs)}ms`:''}</p>
        <img src={r.crop} alt={`Crop tự động ${r.scopeId}`} style={{maxWidth:'100%',maxHeight:160}}/>
        <p>Raw: <code>{r.rawOutput??"UNRESOLVED"}</code></p>
        {r.action==='COMER'&&r.selectedOutput&&<OcrMathPreview latex={r.selectedOutput}/>}
        <details><summary>Stroke IDs / routing evidence</summary><pre>{JSON.stringify({sourceStrokeIds:r.sourceStrokeIds,features:r.features},null,2)}</pre></details>
      </article>)}
    </section>}
    <div className={styles.columns}>
      <div>
        <button aria-pressed={lasso} disabled={busy || stale} onClick={() => setLasso(!lasso)}>Khoanh nét trong preview</button>
        <label><input type="checkbox" checked={showScopeBoxes} onChange={e => setShowScopeBoxes(e.target.checked)} />Overlay scope geometry (xanh); box model (tím)</label>
        <svg data-testid="v2-source-overlay" aria-label="Trang gốc và scope overlay" viewBox={`0 0 ${PAGE.width} ${PAGE.height}`} className={styles.ink}
          onPointerDown={e => { if (!lasso) return; e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); pathRef.current = [pointer(e)]; setPolygon(pathRef.current); }}
          onPointerMove={e => { if (lasso && e.currentTarget.hasPointerCapture(e.pointerId)) { e.preventDefault(); pathRef.current = [...pathRef.current, pointer(e)].slice(-1000); setPolygon(pathRef.current); } }}
          onPointerUp={e => { if (!lasso || !e.currentTarget.hasPointerCapture(e.pointerId)) return; const path = [...pathRef.current]; e.currentTarget.releasePointerCapture(e.pointerId); const ids = lassoIds(snapshot, path); setPicked(ids); setLassoEvidence(p => [...p, { polygon: path, strokeIds: ids, pageIndex: snapshot.pageIndex, sourceRevision: snapshot.sourceRevision }]); pathRef.current = []; setPolygon([]); }}>
          <rect width={794} height={1123} fill="white" />
          {snapshot.strokes.filter(s => s.tool === "PEN" && s.points.length).map((s, i) => <g key={s.id} data-stroke-id={s.id} role="button" tabIndex={0} aria-label={`Chọn nét V2 ${i + 1}`} aria-pressed={picked.includes(s.id)}
            onClick={() => { if (!lasso) setPicked(p => p.includes(s.id) ? p.filter(id => id !== s.id) : [...p, s.id]); }}>
            {s.points.length === 1 ? <circle cx={s.points[0].x * 794} cy={s.points[0].y * 1123} r={3} fill={picked.includes(s.id) ? "#d64c13" : "#123"} /> : <polyline points={s.points.map(p => `${p.x * 794},${p.y * 1123}`).join(" ")} fill="none" stroke={picked.includes(s.id) ? "#d64c13" : highlighted.includes(s.id) ? "#176dca" : "#17202a"} strokeWidth={Math.max(2, s.width)} strokeLinecap="round" strokeLinejoin="round" />}
          </g>)}
          {perception?.regions.map((r, index) => { if (!rendered.value || r.box.length !== 4) return null; const a = fromPixel({ x: r.box[0], y: r.box[1] }, rendered.value.transform), b = fromPixel({ x: r.box[2], y: r.box[3] }, rendered.value.transform); return <g key={r.id} onClick={() => { const s = scopes.find(s => s.regionIds.includes(r.id) && s.strokeIds.length); if (s) setSelected(`unit-${s.id}`); }} style={{ cursor: "pointer" }}><rect x={a.x * 794} y={a.y * 1123} width={Math.max(0, (b.x - a.x) * 794)} height={Math.max(0, (b.y - a.y) * 1123)} fill="transparent" stroke="#9b1485" strokeWidth={2} /><text x={a.x * 794} y={a.y * 1123 - 4} fontSize={13} fill="#9b1485">{index + 1}: {r.label} {r.score?.toFixed(3)}</text></g>; })}
          {showScopeBoxes && construction?.candidates.filter(c => c.source === "INK_GEOMETRY").map((c, index) => <g key={c.id} pointerEvents="none"><rect x={c.bounds.left * 794} y={c.bounds.top * 1123} width={Math.max(1, (c.bounds.right - c.bounds.left) * 794)} height={Math.max(1, (c.bounds.bottom - c.bounds.top) * 1123)} fill="none" stroke="#087b65" strokeDasharray="5 3" /><text x={c.bounds.left * 794} y={c.bounds.bottom * 1123 + 12} fontSize={12} fill="#087b65">G{index + 1}: {c.strokeIds.length} nét</text></g>)}
          {polygon.length > 1 && <polygon points={polygon.map(p => `${p.x * 794},${p.y * 1123}`).join(" ")} fill="#48a2e533" stroke="#2278ba" />}
        </svg>
        <p>Đã chọn {picked.length} nét. Click nét hoặc khoanh; không sửa ink gốc.</p>
        <label>Loại scope thủ công <select value={manualKind} onChange={e => setManualKind(e.target.value as RouteKind)}>{["MATH", "TEXT", "MIXED", "UNKNOWN"].map(k => <option key={k}>{k}</option>)}</select></label>
        <button disabled={!picked.length || busy || stale} onClick={() => applyScope(picked)}>Tạo scope từ nét đã chọn</button>
        <button disabled={!scope || !picked.length || busy || stale} onClick={() => applyScope([...new Set([...(scope?.strokeIds ?? []), ...picked])])}>Gán nét vào scope đang xem</button>
        <details><summary>Stroke IDs / coverage / orphan</summary><pre>{JSON.stringify({ integrity, selected: scope, source: keyForExport(snapshot) }, null, 2)}</pre></details>
        {construction && <details open data-testid="v2-candidates"><summary>Ứng viên và đối chiếu geometry / learned layout</summary>
          <p>Ứng viên thay thế không sở hữu nét độc lập và không tự chạy thêm inference. Chọn để xem membership; dùng thao tác scope thủ công nếu muốn thay phạm vi.</p>
          {construction.candidates.map(c => <div key={c.id}><button disabled={busy} onClick={() => setPicked(c.strokeIds)}>{c.source} · {c.strokeIds.length} nét · {c.disposition}</button><small>{c.evidence.join("; ")}</small></div>)}
          <pre>{JSON.stringify({ relations: construction.relations, trace: construction.trace, durationMs: construction.durationMs }, null, 2)}</pre>
        </details>}
      </div>
      <div>
        <h3>Scopes và bản chép</h3>
        {ir && <p data-testid="v2-ir-status">{ir.reviewStatus} · reading order {ir.readingOrderStatus} · {ir.approvedUnitCount}/{ir.contentUnits.length} đã duyệt</p>}
        <nav aria-label="Đơn vị bản chép V2">{rows.map(r => <div key={r.unit.id} className={styles.unit} style={{ marginLeft: r.depth * 16 }}>
          <input type="checkbox" aria-label={`Chọn nhóm ${r.unit.id}`} checked={multi.includes(r.unit.id)} onChange={e => setMulti(p => e.target.checked ? [...p, r.unit.id] : p.filter(id => id !== r.unit.id))} />
          <button aria-current={selected === r.unit.id ? "true" : undefined} onClick={() => setSelected(r.unit.id)}>{r.unit.readingOrder + 1}. {r.unit.role === "CONTAINER" ? r.unit.structureKind : scopes.find(s => `unit-${s.id}` === r.unit.id)?.kind ?? r.unit.kind} · {r.unit.sourceStrokeIds.length} nét · {r.unit.reviewStatus}</button>
        </div>)}</nav>
        <button disabled={multi.length < 2 || busy || stale} onClick={() => applyScope(rows.filter(r => multi.includes(r.unit.id)).flatMap(r => r.unit.sourceStrokeIds))}>Gộp các scope đã chọn</button>
        <label>Quan hệ <select aria-label="Quan hệ cấu trúc V2" value={relation} onChange={e => setRelation(e.target.value as typeof relation)}>{["UNKNOWN", "SYSTEM", "ALTERNATIVES", "FRACTION", "INDEPENDENT"].map(k => <option key={k}>{k}</option>)}</select></label>
        <button disabled={multi.length < 2 || busy || stale} onClick={() => { change(p => groupIrUnits(p, multi, relation)); setMulti([]); }}>Tạo container cấu trúc</button>
        {unit && <section>
          <h4>{unit.id} · {unit.role}</h4>
          {scope && <p data-testid="v2-routing-reason">Routing: {routingOutcomes.find(o => o.scopeId === scope.id)?.status ?? "SCOPE_CHANGED_REVIEW_REQUIRED"} · {routingOutcomes.find(o => o.scopeId === scope.id)?.reason ?? scope.flags.join("; ")}</p>}
          {scope && <><label>Định tuyến <select aria-label="Định tuyến scope V2" value={scope.kind} disabled={busy || stale} onChange={e => changeKind(e.target.value as RouteKind)}>{["MATH", "TEXT", "MIXED", "UNKNOWN"].map(k => <option key={k}>{k}</option>)}</select></label>
            <button data-testid="v2-recognize-selected" disabled={scope.kind !== "MATH" || busy || stale} onClick={() => void retry()}>Đọc lại scope toán</button>
            <p data-testid="v2-probe-offer">Loại hiện tại: {scope.kind} · {probeOffer.action} · {scope.kind==="TEXT"?record?.htr?"VIETOCR_PROPOSAL_AVAILABLE":"AUTO_TEXT_EVIDENCE_REQUIRED":probeOffer.reason}</p>
            {scope.kind === "MIXED" && <p data-testid="v2-kind-projection">Scope MIXED → IR UNKNOWN (schema 1.1); provenance giữ loại MIXED. Các phần chữ/toán chưa được tách hoặc xác nhận.</p>}
            {probeOffer.eligible && <><button data-testid="v2-math-probe" disabled={busy || stale} onClick={() => void probeUnknown()}>Thử nhận dạng như toán (CoMER)</button><p>Chỉ bấm nếu bạn muốn kiểm tra vùng này như biểu thức toán. Probe không đổi UNKNOWN, không nhập đè bản chép và không xác nhận nội dung.</p></>}
            {scope.kind !== "MATH" && <p>{scope.kind === "TEXT" ? record?.htr?"Đã có đề xuất VietOCR chưa xác nhận; raw output và correction tách riêng.":"TEXT chưa có đề xuất; OCR tự động chỉ gọi VietOCR khi evidence đủ, không chỉ dựa vào nhãn detector." : probeOffer.eligible ? "UNRESOLVED: có thể thử Math Probe theo yêu cầu; chưa xác định loại nội dung." : "UNRESOLVED: cần review phạm vi hoặc cấu trúc; không tự gửi CoMER."}</p>}
            <label>Vạch tách % <input aria-label="Vạch tách scope V2" type="range" min={5} max={95} value={cut} onChange={e => setCut(Number(e.target.value))} /></label>
            <button disabled={busy || stale || scope.strokeIds.length < 2} onClick={() => { const cutY = unit.bounds.top + (unit.bounds.bottom - unit.bounds.top) * cut / 100; applyScope(snapshot.strokes.filter(s => scope.strokeIds.includes(s.id) && (Math.min(...s.points.map(p => p.y)) + Math.max(...s.points.map(p => p.y))) / 2 < cutY).map(s => s.id)); }}>Tách theo vạch (thủ công)</button></>}
          {unit.role === "CONTAINER" ? <label>Sửa quan hệ <select value={unit.structureKind ?? "UNKNOWN"} disabled={busy || stale} onChange={e => change(p => editContainerRelation(p, selected, e.target.value as typeof relation))}>{["UNKNOWN", "SYSTEM", "ALTERNATIVES", "FRACTION", "INDEPENDENT"].map(k => <option key={k}>{k}</option>)}</select></label> : <>
            <p>Đề xuất bản chép ({record?.transcriptModel??"CoMER"}): <code data-testid="v2-wrapper-output">{unit.rawRecognition ?? "UNRESOLVED"}</code></p>
            <label>Bản chép đã sửa <textarea data-testid="v2-transcript" disabled={stale} value={unit.approvedContent ?? unit.rawRecognition ?? ""} onChange={e => change(p => editContentUnit(p, selected, { content: e.target.value }))} /></label>
            {unit.kind === "MATH" && <OcrMathPreview latex={unit.approvedContent ?? unit.rawRecognition ?? ""} />}
          </>}
          <button disabled={stale || busy} onClick={() => change(p => approveContentUnit(p, selected))}>Xác nhận nội dung / cấu trúc</button>
          <button disabled={stale || busy} onClick={() => move(-1)}>Lên</button><button disabled={stale || busy} onClick={() => move(1)}>Xuống</button>
          {record && <details open><summary>Raw model evidence · {Math.round(record.ms)}ms</summary><p>Pre-repair: <code data-testid="v2-pre-repair">{record.diagnostic?.status === "COMPLETED" ? record.diagnostic.rawLatex : "NOT_AVAILABLE"}</code></p>
            <p>{record.error}</p><pre>{JSON.stringify(record.diagnostic?.status === "COMPLETED" ? { ...record.diagnostic, preprocessing: { ...record.diagnostic.preprocessing, previewPng: "export JSON" } } : record, null, 2)}</pre></details>}
          {(record?.unimumer||record?.unimumerError)&&<section aria-label="Uni-MuMER recognition evidence"><h3>Uni-MuMER Q4_K_M · {record.unimumer?.profile??"UNAVAILABLE"}</h3><p>Raw: <code data-testid="unimumer-raw">{record.unimumer?.rawOutput??"NOT_AVAILABLE"}</code></p><p data-testid="unimumer-error">{record.unimumerError}</p><p>{record.unimumer?.durationMs!=null?`${Math.round(record.unimumer.durationMs)} ms`:"NOT_MEASURED"} · {record.unimumer?.status??"ERROR"} · image SHA-256 {record.unimumer?.inputImageHash??"NOT_AVAILABLE"}</p>{record.unimumer&&<OcrMathPreview latex={record.unimumer.normalizedLatex}/>}<details><summary>Evidence / provenance</summary><pre>{JSON.stringify(record.unimumer??{error:record.unimumerError},null,2)}</pre></details>{record.inputCrop&&<img className={styles.crop} src={record.inputCrop} alt="Ảnh crop thực tế gửi Uni-MuMER"/>}</section>}
          {selectedProbe && <section aria-label="Math Probe evidence" data-testid="v2-math-probe-result">
            <h4>Math Probe · CoMER · đề xuất chưa xác nhận</h4>
            <p>Loại lúc probe: {selectedProbe.originalKind} · {selectedProbe.status} · {Math.round(selectedProbe.durationMs)} ms · cần review.</p>
            <p>Raw: <code data-testid="v2-math-probe-raw">{selectedProbe.rawOutput ?? "NOT_AVAILABLE"}</code></p>
            <p>Postprocessed: <code>{selectedProbe.normalizedOutput ?? "NOT_AVAILABLE"}</code></p>
            {selectedProbe.normalizedOutput && <OcrMathPreview latex={selectedProbe.normalizedOutput} />}
            <p>{selectedProbe.error} · Input tensor SHA-256: {selectedProbe.inputCropHash ?? "NOT_AVAILABLE"}</p>
            {selectedProbe.inputCropPreview && <img className={styles.crop} src={selectedProbe.inputCropPreview} alt="CoMER input tensor từ đúng nét của Math Probe" />}
            <p>Giữ UNKNOWN hoặc tự chọn MATH/TEXT rồi nhập bản chép vào ô sửa sau khi đối chiếu. Probe không tự chép vào ô này.</p>
          </section>}
          {scope && rendered.value && <img className={styles.crop} src={cropLabScope(rendered.value.canvas, snapshot.strokes.filter(s => scope.strokeIds.includes(s.id)), rendered.value.transform)} alt="Crop nét của scope đang xem" />}
        </section>}
        <button disabled={!ir || stale || busy} onClick={() => change(confirmTranscriptionReadingOrder)}>Xác nhận thứ tự đọc</button>
        <details><summary>Đề xuất cấu trúc (chưa áp dụng vào scope)</summary><pre>{JSON.stringify(detectStructuralCandidates(snapshot.strokes), null, 2)}</pre></details>
        <details><summary>Lịch sử correction / raw runs ({archives.length})</summary><pre>{JSON.stringify({ archives, runs }, null, 2)}</pre></details>
        <details><summary>Raw layout proposals</summary><pre>{JSON.stringify(perception, null, 2)}</pre></details>
        <details open><summary>Routing / scopes chưa nhận diện</summary><pre data-testid="v2-routing-outcomes">{JSON.stringify(routingOutcomes, null, 2)}</pre></details>
        <p>Projection: PREVIEW_ONLY · steps=[] · submitPayload=null · readyToSubmit=false.</p>
      </div>
    </div>
    <details><summary>Gán nhãn độc lập cho dữ liệu mới (DEV / HOLDOUT)</summary>
      <p>Chọn nét trước khi xem OCR, tự nhập nhãn từ nét gốc. Không sao chép prediction thành GT. Dùng 15–30 mẫu mới và giữ HOLDOUT độc lập.</p>
      <label>Nhãn độc lập <input aria-label="Nhãn độc lập V2" value={annotationText} onChange={e => setAnnotationText(e.target.value)} /></label>
      <button disabled={!picked.length || !annotationText.trim() || records.length > 0 || snapshotProbes.length > 0} onClick={() => { setAnnotations(a => [...a, { id: generateUuid(), strokeIds: [...picked], kind: manualKind, transcript: annotationText }]); setAnnotationText(""); }}>Thêm nhóm nhãn độc lập</button>
      <label><input type="checkbox" disabled={records.length > 0 || snapshotProbes.length > 0} checked={humanVerified} onChange={e => setHumanVerified(e.target.checked)} />Tôi đã đối chiếu nhãn độc lập với OCR</label>
      <pre>{JSON.stringify(annotations, null, 2)}</pre>
      <button disabled={!consent || busy || stale} onClick={() => void exportLabels()}>Xuất capture + nhãn tương thích 05.4</button>
    </details>
    <label><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />Tôi đồng ý lưu/xuất nét hiện tại trên máy để chẩn đoán</label>
    <button data-testid="v2-export" disabled={!ir || busy || !consent} onClick={() => void exportPackage()}>Xuất JSON + CSV + ảnh</button>
    {rendered.value && <button disabled={!consent} onClick={() => { const a = document.createElement("a"); a.href = rendered.value!.png; a.download = "ocr-v2-full-page.png"; a.click(); }}>Tải PNG toàn trang</button>}
    <p>Hướng dẫn: viết → chọn chế độ → chạy → chọn scope. UNKNOWN phù hợp có thể Thử nhận dạng như toán mà không đổi loại; tự đối chiếu rồi sửa/xác nhận. Nếu phạm vi thiếu nét hoặc gộp sai, khoanh lại trước. TEXT tiếng Việt nhập thủ công. Bản này không gửi chấm.</p>
  </section>;
}
