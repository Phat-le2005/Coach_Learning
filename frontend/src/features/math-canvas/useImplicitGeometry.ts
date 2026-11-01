"use client";

import { useEffect, useRef, useState } from "react";
import type { GraphSettings, MathExpression } from "./expression";
import { GraphSamplingQueue, type SamplingData, type SamplingResponse } from "./sampling-protocol";

export function useImplicitGeometry(model: MathExpression, settings: GraphSettings, sample = true) {
  const enabled = model.kind === "implicit" && sample;
  const queue = useRef<GraphSamplingQueue | null>(null);
  const [generation, setGeneration] = useState(0);
  const [data, setData] = useState<SamplingData | null>(null);
  const [pending, setPending] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let worker: Worker;
    try { worker = new Worker(new URL("./implicit.worker.ts", import.meta.url), { type: "module" }); }
    catch { setPending(false); setError("Chưa mở được bộ dựng hình. Bấm thử lại để tiếp tục."); return; }
    let live = true, timeout: ReturnType<typeof setTimeout> | undefined;
    const fail = (message: string) => {
      if (!live) return;
      clearTimeout(timeout); queue.current?.dispose(); queue.current = null; worker.terminate();
      setPending(false); setError(message);
    };
    const current = new GraphSamplingQueue((request) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => fail("Hình đang mất quá lâu để dựng. Thử lại với miền nhỏ hơn."), 10000);
      try { worker.postMessage(request); }
      catch { fail("Chưa gửi được công thức để dựng hình. Bấm thử lại."); }
    }, (result) => {
      if (live) { setData(result); setPending(false); setError(null); }
    }, (message) => { if (live) { setPending(false); setError(message); } });
    queue.current = current;
    worker.onmessage = (event: MessageEvent<SamplingResponse>) => { clearTimeout(timeout); current.accept(event.data); };
    worker.onerror = (event) => { event.preventDefault(); fail("Bộ dựng hình tạm thời không phản hồi. Bấm thử lại."); };
    worker.onmessageerror = () => fail("Chưa đọc được dữ liệu hình. Bấm thử lại.");
    setData(null); setError(null);
    return () => { live = false; clearTimeout(timeout); current.dispose(); worker.terminate(); if (queue.current === current) queue.current = null; };
  }, [enabled, generation]);

  useEffect(() => {
    if (!enabled || !queue.current) return;
    setPending(true); setError(null);
    queue.current.request({ model, settings, slice: settings.view_mode === "2D" && model.dimension === "3D",
      resolution: model.dimension === "3D" && settings.view_mode !== "2D" ? 28 : 56 });
  }, [enabled, model, settings, generation]);

  return { data, pending: enabled && pending, error: enabled ? error : null, retry: () => setGeneration((value) => value + 1) };
}
