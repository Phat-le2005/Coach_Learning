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
            const db = request.result;
            db.onclose = () => {
              this.dbPromise = null;
            };
            db.onversionchange = () => {
              try {
                db.close();
              } catch {}
              this.dbPromise = null;
            };
            resolve(db);
          };

          request.onerror = () => {
            this.dbPromise = null;
            resolve(null);
          };

          request.onblocked = () => {
            this.dbPromise = null;
            resolve(null);
          };
        } catch {
          this.dbPromise = null;
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
    for (let attempt = 0; attempt < 2; attempt++) {
      const db = await this.getDb();
      if (!db) return;

      try {
        await new Promise<void>((resolve, reject) => {
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
        });
        return;
      } catch {
        this.dbPromise = null;
      }
    }
  }

  async getPageDraft(
    attemptId: string,
    pageIndex: number,
  ): Promise<StoredPageDraft | null> {
    for (let attempt = 0; attempt < 2; attempt++) {
      const db = await this.getDb();
      if (!db) return null;

      try {
        return await new Promise<StoredPageDraft | null>((resolve, reject) => {
          const tx = db.transaction(STORE_PAGES, "readonly");
          const store = tx.objectStore(STORE_PAGES);
          const req = store.get([attemptId, pageIndex]);
          req.onsuccess = () => resolve((req.result as StoredPageDraft) || null);
          req.onerror = () => reject(req.error);
        });
      } catch {
        this.dbPromise = null;
      }
    }
    return null;
  }

  async listDirtyPages(attemptId: string): Promise<StoredPageDraft[]> {
    for (let attempt = 0; attempt < 2; attempt++) {
      const db = await this.getDb();
      if (!db) return [];

      try {
        return await new Promise<StoredPageDraft[]>((resolve, reject) => {
          const tx = db.transaction(STORE_PAGES, "readonly");
          const store = tx.objectStore(STORE_PAGES);
          const index = store.index("by_attempt");
          const req = index.getAll(attemptId);
          req.onsuccess = () => {
            const results = (req.result as StoredPageDraft[]) || [];
            resolve(results.filter((item) => item.isDirty));
          };
          req.onerror = () => reject(req.error);
        });
      } catch {
        this.dbPromise = null;
      }
    }
    return [];
  }

  async markPageClean(
    attemptId: string,
    pageIndex: number,
    documentRevision: number,
    expectedActionId: string,
  ): Promise<boolean> {
    for (let attempt = 0; attempt < 2; attempt++) {
      const db = await this.getDb();
      if (!db) return true; // Authoritative save succeeded

      try {
        return await new Promise<boolean>((resolve, reject) => {
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
        });
      } catch {
        this.dbPromise = null;
      }
    }
    return true;
  }

  async clearAttemptDrafts(attemptId: string): Promise<void> {
    for (let attempt = 0; attempt < 2; attempt++) {
      const db = await this.getDb();
      if (!db) return;

      try {
        await new Promise<void>((resolve, reject) => {
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
        });
        return;
      } catch {
        this.dbPromise = null;
      }
    }
  }
}

export const mathInkStorage = new MathInkIndexedDb();
