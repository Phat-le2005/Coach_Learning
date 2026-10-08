"use client";

import { ChevronDown, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useReducer, useRef } from "react";

import type { Role } from "@/lib/api/contracts";
import { accountMenuReducer, initialAccountMenuState } from "@/lib/auth/account-menu-state";
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
  const [state, dispatch] = useReducer(accountMenuReducer, initialAccountMenuState);
  const popoverId = useId();
  const titleId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const firstItemRef = useRef<HTMLAnchorElement>(null);
  const avatar = fullName.trim().split(/\s+/u).filter(Boolean).slice(-2)
    .map((part) => part.charAt(0).toLocaleUpperCase("vi")).join("") || "—";

  useEffect(() => {
    if (state.focus === "first-item" && state.open) {
      firstItemRef.current?.focus();
      dispatch({ type: "FOCUS_APPLIED" });
    } else if (state.focus === "trigger") {
      buttonRef.current?.focus();
      dispatch({ type: "FOCUS_APPLIED" });
    }
  }, [state.focus, state.open]);

  useEffect(() => {
    if (!state.open) return;
    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !containerRef.current?.contains(event.target)) {
        dispatch({ type: "CLOSE" });
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        dispatch({ type: "CLOSE_AND_RESTORE" });
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [state.open]);

  return (
    <div ref={containerRef} className={styles.wrapper}>
      <button
        ref={buttonRef}
        className={`${styles.trigger} ${compact ? styles.compact : ""}`}
        type="button"
        aria-label={`Tài khoản của ${fullName}. Mở tùy chọn tài khoản`}
        aria-controls={state.open ? popoverId : undefined}
        aria-expanded={state.open}
        aria-haspopup="dialog"
        onClick={(event) => dispatch({ type: "TOGGLE", focusFirst: event.detail === 0 })}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            dispatch({ type: "OPEN_WITH_FOCUS" });
          }
        }}
      >
        <span className={styles.avatar} aria-hidden="true">{avatar}</span>
        {!compact ? <span className={styles.triggerName}>{fullName}</span> : null}
        <ChevronDown className={styles.chevron} size={16} aria-hidden="true" />
      </button>
      {state.open ? (
        <div id={popoverId} className={styles.popover} role="dialog" aria-labelledby={titleId}>
          <p id={titleId} className={styles.eyebrow}>Tài khoản · {roleNames[role]}</p>
          <strong className={styles.fullName}>{fullName}</strong>
          {email ? <span className={styles.email}>{email}</span> : null}
          <div className={styles.separator} />
          <Link ref={firstItemRef} className={styles.profileLink} href="/account" onClick={() => dispatch({ type: "CLOSE" })}>
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
