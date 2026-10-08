"use client";

import { LogOut } from "lucide-react";
import { useState } from "react";

import { authenticatedMutation } from "@/lib/auth/browser";

import styles from "./auth.module.css";

export function LogoutButton({ compact = false }: { compact?: boolean }) {
  const [pending, setPending] = useState(false);
  async function logout() {
    setPending(true);
    try { await authenticatedMutation("/auth/logout"); }
    finally { window.location.assign("/login"); }
  }
  return <button className={`${styles.logout} ${compact ? styles.logoutCompact : ""}`} type="button" onClick={logout} disabled={pending} aria-label={pending ? "Đang đăng xuất" : "Đăng xuất"}><LogOut size={17} /><span>{pending ? "Đang thoát" : "Đăng xuất"}</span></button>;
}
