"use client";

import { LogOut } from "lucide-react";
import { useState } from "react";

import { authenticatedMutation, BrowserAuthError } from "@/lib/auth/browser";
import styles from "./auth.module.css";

export function LogoutButton({ compact = false }: { compact?: boolean }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function logout() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await authenticatedMutation("/auth/logout");
      window.location.replace("/login");
    } catch (caught) {
      setError(caught instanceof BrowserAuthError
        ? "Không thể đăng xuất an toàn. Vui lòng thử lại."
        : "Mất kết nối khi đăng xuất. Vui lòng thử lại.");
      setPending(false);
    }
  }

  return (
    <div className={styles.logoutArea}>
      <button className={`${styles.logout} ${compact ? styles.logoutCompact : ""}`} type="button" onClick={logout} disabled={pending} aria-label={pending ? "Đang đăng xuất" : "Đăng xuất"}>
        <LogOut size={17} aria-hidden="true" />
        <span>{pending ? "Đang đăng xuất…" : "Đăng xuất"}</span>
      </button>
      {error ? <p className={styles.logoutError} role="alert">{error}</p> : null}
    </div>
  );
}
