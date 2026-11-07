import { validateSolutionTranscriptionIR } from "./structured-transcription-ir";
import type { CoreReview } from "./ocr-v2-core";
import { sha256Hex } from "./ocr-digest";
import { generateUuid } from "./ink-math";
const DB = "edums-ocr-transcription-v1";
async function open(): Promise<IDBDatabase> { return new Promise((resolve, reject) => {
  const r = indexedDB.open(DB, 1); r.onupgradeneeded = () => r.result.createObjectStore("reviews"); r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error);
}); }
export async function transcriptionKey(attemptId: string, identity: string) {
  // HTTP LAN origins lack SubtleCrypto. Keep the exact SHA-256 identity so
  // reopening a review preserves corrections in either browser environment.
  const hash = await sha256Hex(identity);
  return `${attemptId}:${hash}`;
}
export async function loadTranscription(key: string): Promise<CoreReview | undefined> {
  const db = await open(); try { return await new Promise((resolve, reject) => {
    const r = db.transaction("reviews").objectStore("reviews").get(key); r.onerror = () => reject(r.error); r.onsuccess = () => {
      try { if (r.result) { if (r.result.schemaVersion !== "ocr-core-review/1") throw Error("UNSUPPORTED_LOCAL_REVIEW"); validateSolutionTranscriptionIR(r.result.ir); } resolve(r.result); } catch (error) { reject(error); }
    };
  }); } finally { db.close(); }
}
export async function saveTranscription(key: string, review: CoreReview, expectedVersion?: string): Promise<string> {
  validateSolutionTranscriptionIR(review.ir); const db = await open();
  const version = generateUuid();
  try { await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("reviews", "readwrite"), store = tx.objectStore("reviews"), request = store.get(key); let conflict = false;
    request.onsuccess = () => { if (request.result?.localVersion !== expectedVersion) { conflict = true; tx.abort(); } else store.put({ ...review, localVersion: version }, key); };
    tx.oncomplete = () => resolve(); tx.onabort = () => reject(conflict ? Error("REVIEW_CHANGED_IN_ANOTHER_TAB; export before reload; stored corrections preserved") : tx.error); tx.onerror = () => reject(tx.error);
  }); return version; } finally { db.close(); }
}
