import type { InkStroke } from "../types";

export interface StoredPageDraft {
  attemptId: string;
  pageIndex: number;
  strokes: InkStroke[];
  documentRevision: number;
  clientActionId: string;
  isDirty: boolean;
  updatedAt: number;
}

const DB_NAME = "edums_math_ink_v1";
const DB_VERSION = 1;
const STORE_PAGES = "page_drafts";

class MathInkIndexedDb {
  private dbPromise: Promise<IDBDatabase | null> | null = null;

  private getDb(): Promise<IDBDatabase | null> {
    if (typeof window === "undefined" || typeof indexedDB === "undefined") {
      return Promise.resolve(null);
    }

    if (!this.dbPromise) {
      this.dbPromise = new Promise((resolve) => {
        try {
          const request = indexedDB.open(DB_NAME, DB_VERSION);

          request.onupgradeneeded = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains(STORE_PAGES)) {
              const store = db.createObjectStore(STORE_PAGES, {
                keyPath: ["attemptId", "pageIndex"],
              });
              store.createIndex("by_attempt", "attemptId", { unique: false });
              store.createIndex("by_dirty", "isDirty", { unique: false });
            }
          };

          request.onsuccess = () => {
            resolve(request.result);
          };

          request.onerror = () => {
            resolve(null);
          };
        } catch {
          resolve(null);
        }
      });
    }

    return this.dbPromise;
  }

  async savePageDraft(
    attemptId: string,
    pageIndex: number,
    strokes: InkStroke[],
    documentRevision: number,
    clientActionId: string,
    isDirty: boolean,
  ): Promise<void> {
    const db = await this.getDb();
    if (!db) return;

    return new Promise((resolve, reject) => {
      try {
        const tx = db.transaction(STORE_PAGES, "readwrite");
        const store = tx.objectStore(STORE_PAGES);
        const record: StoredPageDraft = {
          attemptId,
          pageIndex,
          strokes,
          documentRevision,
          clientActionId,
          isDirty,
          updatedAt: Date.now(),
        };
        store.put(record);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      } catch (err) {
        reject(err);
      }
    });
  }

  async getPageDraft(
    attemptId: string,
    pageIndex: number,
  ): Promise<StoredPageDraft | null> {
    const db = await this.getDb();
    if (!db) return null;

    return new Promise((resolve, reject) => {
      try {
        const tx = db.transaction(STORE_PAGES, "readonly");
        const store = tx.objectStore(STORE_PAGES);
        const req = store.get([attemptId, pageIndex]);
        req.onsuccess = () => resolve((req.result as StoredPageDraft) || null);
        req.onerror = () => reject(req.error);
      } catch (err) {
        reject(err);
      }
    });
  }

  async listDirtyPages(attemptId: string): Promise<StoredPageDraft[]> {
    const db = await this.getDb();
    if (!db) return [];

    return new Promise((resolve, reject) => {
      try {
        const tx = db.transaction(STORE_PAGES, "readonly");
        const store = tx.objectStore(STORE_PAGES);
        const index = store.index("by_attempt");
        const req = index.getAll(attemptId);
        req.onsuccess = () => {
          const results = (req.result as StoredPageDraft[]) || [];
          resolve(results.filter((item) => item.isDirty));
        };
        req.onerror = () => reject(req.error);
      } catch (err) {
        reject(err);
      }
    });
  }

  async markPageClean(
    attemptId: string,
    pageIndex: number,
    documentRevision: number,
    expectedActionId: string,
  ): Promise<boolean> {
    const db = await this.getDb();
    if (!db) return true; // The authoritative server save already succeeded.

    // Read and conditionally write in ONE readwrite transaction, so an older
    // in-flight save cannot mark a more recent ink draft as synchronized.
    return new Promise((resolve, reject) => {
      try {
        const tx = db.transaction(STORE_PAGES, "readwrite");
        const store = tx.objectStore(STORE_PAGES);
        const req = store.get([attemptId, pageIndex]);
        let matched = false;
        req.onsuccess = () => {
          const draft = req.result as StoredPageDraft | undefined;
          if (!draft || draft.clientActionId !== expectedActionId) return;
          matched = true;
          draft.isDirty = false;
          draft.documentRevision = documentRevision;
          draft.updatedAt = Date.now();
          store.put(draft);
        };
        tx.oncomplete = () => resolve(matched);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      } catch (err) {
        reject(err);
      }
    });
  }

  async clearAttemptDrafts(attemptId: string): Promise<void> {
    const db = await this.getDb();
    if (!db) return;

    return new Promise((resolve, reject) => {
      try {
        const tx = db.transaction(STORE_PAGES, "readwrite");
        const store = tx.objectStore(STORE_PAGES);
        const index = store.index("by_attempt");
        const req = index.getAllKeys(attemptId);
        req.onsuccess = () => {
          const keys = req.result;
          for (const key of keys) {
            store.delete(key);
          }
          resolve();
        };
        req.onerror = () => reject(req.error);
      } catch (err) {
        reject(err);
      }
    });
  }
}

export const mathInkStorage = new MathInkIndexedDb();
