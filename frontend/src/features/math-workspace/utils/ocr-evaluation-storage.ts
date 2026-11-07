import type { CachedRecognition } from "./ocr-evaluation-benchmark";
const DB = "coach-ocr-evaluation-local-v1";
async function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => { request.result.createObjectStore("workspace"); request.result.createObjectStore("recognition"); };
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
  });
}
async function read<T>(store: string, key: string): Promise<T | undefined> {
  const db = await database(); try { return await new Promise((resolve, reject) => { const request = db.transaction(store).objectStore(store).get(key); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); }); } finally { db.close(); }
}
async function write(store: string, key: string, value: unknown): Promise<void> {
  const db = await database(); try { await new Promise<void>((resolve, reject) => { const tx = db.transaction(store, "readwrite"); tx.objectStore(store).put(value, key); tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error); }); } finally { db.close(); }
}
export const readEvaluationWorkspace = <T>() => read<T>("workspace", "active");
/** Atomic optimistic lock: another tab cannot silently overwrite this tab's annotations. */
export async function saveEvaluationWorkspace(value: unknown, expectedSavedAt: string | undefined): Promise<void> {
  const db = await database();
  try { await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("workspace", "readwrite"), store = tx.objectStore("workspace"), request = store.get("active"); let conflict = false;
    request.onsuccess = () => { if (request.result?.savedAt !== expectedSavedAt) { conflict = true; tx.abort(); } else store.put(value, "active"); };
    tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error); tx.onabort = () => reject(conflict ? Error("WORKSPACE_CHANGED_IN_ANOTHER_TAB; export current edits before reload; stored annotations preserved") : tx.error);
  }); } finally { db.close(); }
}
export const getRecognitionCache = (key: string) => read<CachedRecognition>("recognition", key);
export const putRecognitionCache = (key: string, value: CachedRecognition) => write("recognition", key, value);
export const storeEvaluationTransfer = (id: string, value: unknown) => write("workspace", `transfer-${id}`, value);
export const readEvaluationTransfer = <T>(id: string) => read<T>("workspace", `transfer-${id}`);
