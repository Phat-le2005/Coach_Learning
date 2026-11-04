import { sampleLab } from "./lab-geometry";
import type { LabDocument } from "./lab-spec";
self.onmessage = (event: MessageEvent<{ id: number; document: LabDocument; parameters: Record<string, number>; domain: number }>) => {
  const { id, document, parameters, domain } = event.data;
  try { self.postMessage({ id, drawing: sampleLab(document, parameters, domain) }); }
  catch (error) { self.postMessage({ id, error: error instanceof Error ? error.message : "Chưa dựng được hình." }); }
};
