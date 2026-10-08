"use client";

import { ChevronDown, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import type { Role } from "@/lib/api/contracts";
import { LogoutButton } from "./LogoutButton";
import styles from "./account-menu.module.css";

const roleNames: Record<Role, string> = {
  STUDENT: "Học sinh",
  TEACHER: "Giáo viên",
  PARENT: "Phụ huynh",
  ADMIN: "Quản trị",
};

interface AccountMenuProps {
  fullName: string;
  email?: string;
  role: Role;
  compact?: boolean;
}

export function AccountMenu({ fullName, email, role, compact = false }: AccountMenuProps) {
  const [open, setOpen] = useState(false);
  const popoverId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const avatar = fullName.trim().split(/\s+/u).filter(Boolean).slice(-2)
    .map((part) => part.charAt(0).toLocaleUpperCase("vi")).join("") || "—";

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !containerRef.current?.contains(event.target)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className={styles.wrapper}>
      <button
        ref={buttonRef}
        className={`${styles.trigger} ${compact ? styles.compact : ""}`}
        type="button"
        aria-label={`Tài khoản của ${fullName}. Mở tùy chọn tài khoản`}
        aria-controls={open ? popoverId : undefined}
        aria-expanded={open}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span className={styles.avatar} aria-hidden="true">{avatar}</span>
        {!compact ? <span className={styles.triggerName}>{fullName}</span> : null}
        <ChevronDown className={styles.chevron} size={16} aria-hidden="true" />
      </button>
      {open ? (
        <div id={popoverId} className={styles.popover} aria-label="Tùy chọn tài khoản">
          <p className={styles.eyebrow}>Tài khoản · {roleNames[role]}</p>
          <strong className={styles.fullName}>{fullName}</strong>
          {email ? <span className={styles.email}>{email}</span> : null}
          <div className={styles.separator} />
          <Link className={styles.profileLink} href="/account" onClick={() => setOpen(false)}>
            <UserRound size={18} aria-hidden="true" />
            Hồ sơ của tôi
          </Link>
          <div className={styles.separator} />
          <LogoutButton />
        </div>
      ) : null}
    </div>
  );
}
