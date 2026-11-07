"use client";
import { useEffect, useRef, useState } from "react";
import { assertHtrCandidate, htrMetrics, runSelectedHtrProbe, type HtrCandidate, type HtrEvidence } from "../utils/vietnamese-htr";

/** Frozen research samples are separate from live canvas/review state. Never auto-run. */
export function VietnameseHtrProbePanel() {
  const [candidates, setCandidates] = useState<HtrCandidate[]>([]), [selected, setSelected] = useState("HTR-1");
  const [health, setHealth] = useState("CHECKING"), [error, setError] = useState("");
  const [busy, setBusy] = useState(false), [evidence, setEvidence] = useState<Record<string, HtrEvidence>>({});
  const controller = useRef<AbortController | null>(null), lock = useRef(false), alive = useRef(true);
  const candidate = candidates.find(c => c.candidateId === selected), result = evidence[selected];
  useEffect(() => {
    alive.current = true;
    void fetch("/api/ocr-v2-lab/htr", { cache: "no-store" }).then(async r => {
      const body = await r.json(); if (!r.ok) throw Error(body.error ?? "HTR_CATALOG_UNAVAILABLE");
      body.candidates.forEach(assertHtrCandidate);
      if (alive.current) { setCandidates(body.candidates); setHealth(body.health.status); }
    }).catch(e => { if (alive.current) { setError(String(e)); setHealth("UNAVAILABLE"); } });
    return () => { alive.current = false; controller.current?.abort(); };
  }, []);
  async function run() {
    if (!candidate || lock.current) return;
    lock.current = true; setBusy(true); setError(""); controller.current = new AbortController();
    try { const value = await runSelectedHtrProbe(candidate, controller.current.signal); if (alive.current) { setEvidence(old => ({ ...old, [candidate.candidateId]: value })); setHealth("LOADED"); } }
    catch (e) { if (alive.current) setError(String(e)); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  return <section data-testid="vietnamese-htr-panel" aria-busy={busy} style={{ border: "1px solid #8099aa", padding: 12, marginBottom: 16 }}>
    <h2>Vietnamese HTR · Research probe</h2>
    <p>VietOCR handwritten fine-tune · local CPU · <span data-testid="htr-health">{health}</span>. Chỉ ba crop đã xác nhận; không tự nhận mọi TEXT/UNKNOWN trên canvas.</p>
    <label>HTR candidate đã xác nhận <select data-testid="htr-candidate" disabled={busy} value={selected} onChange={e => setSelected(e.target.value)}>{candidates.map(c => <option key={c.candidateId} value={c.candidateId}>{c.candidateId} · {c.sourceStrokeIds.length} nét · kind gốc {c.originalKind}</option>)}</select></label>
    <button data-testid="htr-run" disabled={!candidate || busy} onClick={() => void run()}>Thử nhận dạng chữ Việt</button>
    {error && <p role="alert" data-testid="htr-error">{error}</p>}
    {candidate && <div>
      <p>{candidate.pageId} · {candidate.scopeId} · revision {candidate.sourceRevision}. HTR-3 luôn là subset19, không phải scope33 hiện tại.</p>
      <img src={candidate.png} alt={`Crop đúng nét nguồn ${candidate.candidateId}`} style={{ maxWidth: "100%", border: "1px solid #bbb" }} />
      <p data-testid="htr-reference">Reference Research (human-confirmed assisted): {candidate.reference.text}</p>
      <details><summary>Source stroke IDs / provenance</summary><pre>{JSON.stringify({ sourceStrokeIds: candidate.sourceStrokeIds, inputImageHash: candidate.inputImageHash, sourceSnapshotSha256: candidate.sourceSnapshotSha256, originalKind: candidate.originalKind }, null, 2)}</pre></details>
    </div>}
    {result && <div><p>Raw model output chưa xác nhận: <strong data-testid="htr-raw">{result.rawTranscript || "(empty output)"}</strong></p>
      <p>{result.modelId} · {result.device} · <span data-testid="htr-latency">{Math.round(result.durationMs)} ms</span> · {result.status}</p>
      <details><summary>Evidence / NFC / metrics trên đúng mẫu này</summary><pre data-testid="htr-evidence">{JSON.stringify({ ...result, metrics: candidate ? htrMetrics(result.rawTranscript, candidate.reference.text) : null }, null, 2)}</pre></details>
    </div>}
    <p>Probe chỉ lưu evidence trong bộ nhớ và local logs. Không đổi kind, không nhập đè correction, không approve, không gửi chấm. Nhãn reference không được gửi cho model.</p>
  </section>;
}
