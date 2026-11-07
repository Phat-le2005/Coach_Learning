import type { InkIntent } from "./protocol";

interface Record extends InkIntent { key: string; attempt: string; page: number }
function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open("edums-live-ink", 1);
    open.onupgradeneeded = () => open.result.createObjectStore("outbox", { keyPath: "key" });
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error);
  });
}
async function transaction<T>(mode: IDBTransactionMode, operation: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await database();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction("outbox", mode);
      const request = operation(tx.objectStore("outbox"));
      tx.oncomplete = () => resolve(request.result);
      tx.onabort = tx.onerror = () => reject(tx.error ?? new Error("IndexedDB outbox failed"));
    });
  } finally { db.close(); }
}
export const liveOutbox = {
  put: (attempt: string, page: number, intent: InkIntent) => transaction("readwrite", store => store.put({ ...intent, key: `${attempt}:${intent.client_action_id}`, attempt, page })),
  remove: (attempt: string, id: string) => transaction("readwrite", store => store.delete(`${attempt}:${id}`)),
  list: async (attempt: string, page: number): Promise<InkIntent[]> => {
    const all = await transaction("readonly", store => store.getAll()) as Record[];
    return all.filter(r => r.attempt === attempt && r.page === page).sort((a,b) => a.createdAt - b.createdAt);
  },
};
