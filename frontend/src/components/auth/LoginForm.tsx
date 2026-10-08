"use client";

import { ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole, Mail } from "lucide-react";
import { useState, type FormEvent } from "react";

import { GradientButton } from "@/components/ui/GradientButton";
import { authenticatedMutation, BrowserAuthError } from "@/lib/auth/browser";

import styles from "./auth.module.css";

export interface LoginFormProps { returnTo?: string; expired?: boolean }

function friendlyError(error: unknown): string {
  if (error instanceof BrowserAuthError) {
    if (error.status === 401) return "Email hoặc mật khẩu chưa đúng.";
    if (error.status === 403) return "Tài khoản không có quyền truy cập hoặc đã bị vô hiệu hóa.";
    if (error.status === 422) return "Vui lòng kiểm tra lại email và mật khẩu.";
    if (error.status === 503) return "Dịch vụ EduMS hiện chưa kết nối được. Vui lòng thử lại sau.";
    return error.message;
  }
  return "Không thể kết nối tới EduMS. Vui lòng kiểm tra mạng và thử lại.";
}

export function LoginForm({ returnTo, expired = false }: LoginFormProps) {
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const result = await authenticatedMutation("/auth/login", {
        email: String(form.get("email") ?? ""),
        password: String(form.get("password") ?? ""),
        ...(returnTo ? { return_to: returnTo } : {}),
      });
      const destination = typeof result.redirect_to === "string" ? result.redirect_to : "/";
      window.location.assign(destination);
    } catch (caught) {
      setError(friendlyError(caught));
      setPending(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      {expired ? <div className={styles.notice}>Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại để tiếp tục.</div> : null}
      <label className={styles.field}>
        <span>Email</span>
        <span className={styles.inputWrap}>
          <Mail size={18} aria-hidden="true" />
          <input name="email" type="email" inputMode="email" autoComplete="email" required maxLength={254} placeholder="ban@edums.vn" disabled={pending} />
        </span>
      </label>
      <label className={styles.field}>
        <span>Mật khẩu</span>
        <span className={styles.inputWrap}>
          <LockKeyhole size={18} aria-hidden="true" />
          <input name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required maxLength={128} placeholder="Nhập mật khẩu" disabled={pending} />
          <button className={styles.reveal} type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}>
            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        </span>
      </label>
      {error ? <div className={styles.error} role="alert">{error}</div> : null}
      <GradientButton className={styles.submit} type="submit" disabled={pending}>
        {pending ? <LoaderCircle className={styles.spinner} size={19} aria-hidden="true" /> : null}
        {pending ? "Đang xác thực" : "Vào không gian học tập"}
        {!pending ? <ArrowRight size={18} aria-hidden="true" /> : null}
      </GradientButton>
      <p className={styles.privacy}>Phiên đăng nhập được bảo vệ bằng cookie HttpOnly. EduMS không lưu token trong trình duyệt.</p>
    </form>
  );
}
