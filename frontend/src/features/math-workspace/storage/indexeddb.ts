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
        const req = store.put(record);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
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
  ): Promise<void> {
    const draft = await this.getPageDraft(attemptId, pageIndex);
    if (!draft) return;
    draft.isDirty = false;
    draft.documentRevision = documentRevision;
    draft.updatedAt = Date.now();

    const db = await this.getDb();
    if (!db) return;

    return new Promise((resolve, reject) => {
      try {
        const tx = db.transaction(STORE_PAGES, "readwrite");
        const store = tx.objectStore(STORE_PAGES);
        const req = store.put(draft);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
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
