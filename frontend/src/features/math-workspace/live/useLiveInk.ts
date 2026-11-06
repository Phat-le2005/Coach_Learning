"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getCsrfToken, refreshBrowserSession } from "@/lib/auth/browser";
import type { InkStroke } from "../types";
import { inkDiff, replayIntents, type InkIntent, type LiveSnapshot } from "./protocol";
import { liveOutbox } from "./outbox";
import { generateUuid } from "../utils/ink-math";

async function request<T>(url: string, body?: unknown): Promise<T> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const response = await fetch(url, { method: body === undefined ? "GET" : "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-EduMS-BFF": "1", ...(body === undefined ? {} : { "X-CSRF-Token": await getCsrfToken() }) },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(22000) });
    if (response.status === 401 && attempt === 0 && !url.startsWith("/api/ink-device/")) { await refreshBrowserSession(); continue; }
    const value = await response.json();
    if (!response.ok) throw Object.assign(new Error(value.error?.message ?? "Đồng bộ thất bại"), { code: value.error?.code, status: response.status });
    return value as T;
  }
  throw new Error("Phiên đăng nhập đã hết hạn.");
}

export function useLiveInk(options: { attemptId: string; pageIndex: number; enabled: boolean;
  apiBase?: string;
  onSnapshot: (snapshot: LiveSnapshot, pending: boolean) => void;
  onPageAvailable?: (pageIndex: number) => void }) {
  const { attemptId, pageIndex, enabled } = options;
  const [status, setStatus] = useState("disconnected");
  const [error, setError] = useState("");
  const [devices, setDevices] = useState(0);
  const [peers, setPeers] = useState<{ id: string; label: string }[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [drafts, setDrafts] = useState<InkStroke[]>([]);
  const [historyVersion, setHistoryVersion] = useState(0);
  const callback = useRef(options.onSnapshot); callback.current = options.onSnapshot;
  const pageAvailable = useRef(options.onPageAvailable); pageAvailable.current = options.onPageAvailable;
  const state = useRef<{ canonical: LiveSnapshot; pending: InkIntent[]; undo: InkIntent[]; redo: InkIntent[];
    ready: boolean; pumping: boolean; socket?: WebSocket; alive: boolean; generation: number; seq: number;
    remote: Map<string, { stroke: InkStroke; time: number }>; durable: Promise<void> }>({
    canonical: { document_revision: -1, page_index: pageIndex, strokes: [] }, pending: [], undo: [], redo: [],
    ready: false, pumping: false, alive: false, generation: 0, seq: 0, remote: new Map(), durable: Promise.resolve(),
  });
  const base = options.apiBase ?? `/api/v2/math-solutions/attempts/${attemptId}/ink`;
  const emit = useCallback(() => {
    const s = state.current;
    setPendingCount(s.pending.length);
    callback.current({ ...s.canonical, strokes: replayIntents(s.canonical.strokes, s.pending) }, s.pending.length > 0);
  }, []);
  const accept = useCallback((snapshot: LiveSnapshot) => {
    const s = state.current;
    if (snapshot.page_index !== pageIndex || snapshot.document_revision < s.canonical.document_revision) return;
    s.canonical = snapshot;
    const ids = new Set(snapshot.strokes.map(x => x.id));
    for (const [key, item] of s.remote) if (ids.has(item.stroke.id)) s.remote.delete(key);
    setDrafts([...s.remote.values()].map(x => x.stroke));
    emit();
  }, [emit, pageIndex]);

  const pump = useCallback(async () => {
    const s = state.current;
    if (s.pumping || !s.ready || !s.alive) return;
    s.pumping = true;
    const generation = s.generation;
    try {
      await s.durable;
      let conflicts = 0;
      while (s.pending.length && s.alive && generation === s.generation) {
        await s.durable;
        const intent = s.pending[0];
        // Journal retention is seven days. Never silently replay expired intent.
        if (Date.now() - intent.createdAt > 24 * 3600000) throw new Error("Bản nháp trực tiếp quá 24 giờ cần đối soát. Hãy xuất bản nháp trước khi tiếp tục.");
        setStatus("saving");
        try {
          const snapshot = await request<LiveSnapshot>(`${base}/pages/${pageIndex}/operations`, {
            client_action_id: intent.client_action_id, expected_document_revision: s.canonical.document_revision,
            add: intent.add, remove: intent.remove,
          });
          if (generation !== s.generation) return;
          await liveOutbox.remove(attemptId, intent.client_action_id);
          s.pending = s.pending.filter(x => x.client_action_id !== intent.client_action_id);
          accept(snapshot);
          emit(); // A newer WS revision may already have superseded this HTTP ACK.
          conflicts = 0;
        } catch (err) {
          const failure = err as Error & { code?: string };
          if (failure.code === "INK_REVISION_CONFLICT" && conflicts++ < 8) {
            accept(await request<LiveSnapshot>(`${base}/pages/${pageIndex}`));
            continue; // Fixed add/remove intent is unchanged by rebasing.
          }
          throw err;
        }
      }
      if (s.alive) { setError(""); setStatus(s.socket?.readyState === WebSocket.OPEN ? "connected" : "reconnecting"); }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể lưu nét. Bản nháp được giữ lại.");
      setStatus(navigator.onLine ? "error" : "offline");
    } finally { s.pumping = false; }
  }, [accept, attemptId, base, pageIndex, emit]);

  useEffect(() => {
    if (!enabled) return;
    const s = state.current;
    s.alive = true; s.ready = false; s.generation++;
    setStatus("reconnecting");
    s.canonical = { document_revision: -1, page_index: pageIndex, strokes: [] };
    s.pending = []; s.undo = []; s.redo = []; s.remote.clear(); setDrafts([]);
    setDevices(0); setPeers([]);
    setHistoryVersion(v => v + 1);
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout>;
    let heartbeat: ReturnType<typeof setInterval>;
    let retries = 0;
    const connect = async () => {
      if (cancelled) return;
      setStatus(navigator.onLine ? "reconnecting" : "offline");
      try {
        const ticket = await request<{ ticket: string; websocket_url: string }>(`${base}/live-ticket`, { page_index: pageIndex });
        if (cancelled) return;
        const socket = new WebSocket(ticket.websocket_url);
        s.socket = socket;
        socket.onopen = () => socket.send(JSON.stringify({ type: "AUTH", ticket: ticket.ticket,
          label: navigator.maxTouchPoints > 0 ? "Thiết bị cảm ứng" : "Máy tính" }));
        socket.onmessage = event => {
          if (cancelled) return;
          const message = JSON.parse(event.data);
          if (message.type === "PAGE_SNAPSHOT" || message.type === "STROKE_COMMITTED") {
            accept(message);
            if (!s.ready) { s.ready = true; void pump(); }
            retries = 0; setStatus(s.pending.length ? "saving" : "connected");
          } else if (message.type === "PAGE_AVAILABLE") {
            pageAvailable.current?.(message.page_index);
          } else if (message.type === "PRESENCE") {
            setDevices(message.devices);
            setPeers(message.peers ?? []);
            if (message.departed) s.remote.delete(message.departed);
            setDrafts([...s.remote.values()].map(x => x.stroke));
          } else if (["STROKE_BEGIN", "STROKE_POINTS", "STROKE_END"].includes(message.type)) {
            if (!s.canonical.strokes.some(x => x.id === message.stroke.id)) s.remote.set(message.peer_id, { stroke: message.stroke, time: Date.now() });
            setDrafts([...s.remote.values()].map(x => x.stroke));
          }
        };
        socket.onerror = () => setError("Kết nối trực tiếp bị gián đoạn; nét chưa xác nhận vẫn ở hàng đợi.");
        socket.onclose = () => {
          clearInterval(heartbeat);
          s.ready = false; s.remote.clear(); setDrafts([]);
          if (!cancelled) {
            setStatus(navigator.onLine ? "reconnecting" : "offline");
            retry = setTimeout(() => void connect(), Math.min(10000, 1000 * 2 ** retries++));
          }
        };
        heartbeat = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "RESYNC" }));
          for (const [key, draft] of s.remote) if (Date.now() - draft.time > 10000) s.remote.delete(key);
          setDrafts([...s.remote.values()].map(x => x.stroke));
          void pump();
        }, 5000);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Không kết nối được.");
        setStatus(navigator.onLine ? "error" : "offline");
        retry = setTimeout(() => void connect(), 5000);
      }
    };
    void liveOutbox.list(attemptId, pageIndex).then(pending => {
      if (cancelled) return;
      s.pending = pending; setPendingCount(pending.length); void connect();
    }).catch(() => { setStatus("error"); setError("Không mở được bộ nhớ bản nháp. Chưa bật viết trực tiếp."); });
    const online = () => { s.socket?.close(); };
    window.addEventListener("online", online);
    const beforeUnload = (event: BeforeUnloadEvent) => { if (s.pending.length) event.preventDefault(); };
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      cancelled = true; s.alive = false; s.ready = false; s.generation++;
      clearTimeout(retry); clearInterval(heartbeat); s.socket?.close();
      window.removeEventListener("online", online); window.removeEventListener("beforeunload", beforeUnload);
    };
  }, [enabled, attemptId, pageIndex, base, accept, pump]);

  const enqueue = useCallback((change: Pick<InkIntent, "add" | "remove">, history = true) => {
    const s = state.current;
    if (!change.add.length && !change.remove.length) return;
    const intent: InkIntent = { ...change, client_action_id: generateUuid(), createdAt: Math.max(Date.now(), (s.pending.at(-1)?.createdAt ?? 0) + 1) };
    s.pending.push(intent);
    if (history) { s.undo.push(intent); if (s.undo.length > 30) s.undo.shift(); s.redo = []; setHistoryVersion(v => v + 1); }
    s.durable = s.durable.then(async () => { await liveOutbox.put(attemptId, pageIndex, intent); });
    emit(); void pump();
  }, [attemptId, pageIndex, emit, pump]);
  const change = useCallback((next: InkStroke[], observedStrokes: InkStroke[]) => {
    // Never infer deletion of remote strokes which arrived after the user's
    // drawing/erasing event. Diff only against the strokes actually observed.
    enqueue(inkDiff(observedStrokes, next));
  }, [enqueue]);
  const undo = () => {
    const intent = state.current.undo.pop(); if (!intent) return;
    state.current.redo.push(intent); enqueue({ add: intent.remove, remove: intent.add }, false); setHistoryVersion(v => v + 1);
  };
  const redo = () => {
    const intent = state.current.redo.pop(); if (!intent) return;
    state.current.undo.push(intent); enqueue(intent, false); setHistoryVersion(v => v + 1);
  };
  const lastStream = useRef(0);
  const stream = useCallback((type: "STROKE_BEGIN" | "STROKE_POINTS" | "STROKE_END", stroke: InkStroke) => {
    const s = state.current;
    if (type === "STROKE_POINTS" && performance.now() - lastStream.current < 50) return;
    lastStream.current = performance.now();
    if (s.socket?.readyState === WebSocket.OPEN) s.socket.send(JSON.stringify({ type, stroke, seq: ++s.seq }));
  }, []);
  const flush = useCallback(async () => {
    await pump();
    const deadline = Date.now() + 25000;
    while (state.current.pumping && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 50));
    return state.current.pending.length === 0 && state.current.ready;
  }, [pump]);
  return { status, error, devices, peers, drafts, pendingCount, change, stream, flush, undo, redo,
    canUndo: historyVersion >= 0 && state.current.undo.length > 0, canRedo: state.current.redo.length > 0,
    ready: state.current.ready && state.current.canonical.page_index === pageIndex,
    initialized: state.current.canonical.page_index === pageIndex && state.current.canonical.document_revision >= 0, retry: pump };
}
