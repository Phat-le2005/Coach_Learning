"use client";

import { useEffect, useState } from "react";
import { refreshBrowserSession } from "@/lib/auth/browser";
import styles from "./TheoryMaps.module.css";

export function TheorySourceViewer({ url, title, pageCount, page }: {
  url: string; title: string; pageCount: number; page: number;
}) {
  const [blobUrl, setBlobUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = "";
    async function load() {
      setLoading(true); setError(""); setBlobUrl("");
      try {
        let response = await fetch(url, { credentials: "same-origin", cache: "no-store", signal: controller.signal });
        if (response.status === 401) {
          await refreshBrowserSession();
          response = await fetch(url, { credentials: "same-origin", cache: "no-store", signal: controller.signal });
        }
        if (!response.ok || !response.headers.get("content-type")?.includes("application/pdf")) {
          throw new Error(`Không thể mở PDF (${response.status}). Hãy kiểm tra phiên đăng nhập và thử lại.`);
        }
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Không thể tải PDF.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url]);

  const validPage = Math.max(1, Math.min(pageCount, page));
  return <div className={styles.pdfViewer}>
    {loading && <p role="status">Đang mở tài liệu gốc…</p>}
    {error && <p className={styles.error} role="alert">{error}</p>}
    {blobUrl && <>
      <div className={styles.pdfBar}><strong>Trang {validPage}/{pageCount}</strong>
        <a className={styles.link} href={`${blobUrl}#page=${validPage}`} target="_blank" rel="noopener noreferrer">Mở PDF toàn màn hình ↗</a>
      </div>
      <iframe key={`${blobUrl}:${validPage}`} className={styles.pdfFrame} src={`${blobUrl}#page=${validPage}`}
        title={`${title} — trang ${validPage}`} />
    </>}
  </div>;
}
