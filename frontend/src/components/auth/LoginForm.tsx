"use client";

import {
  AlertCircle,
  ArrowRight,
  Eye,
  EyeOff,
  Info,
  LoaderCircle,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import { GradientButton } from "@/components/ui/GradientButton";
import { authenticatedMutation, BrowserAuthError } from "@/lib/auth/browser";
import { hasLoginFieldErrors, validateLoginFields, type LoginFieldErrors } from "@/lib/auth/login-validation";

import styles from "./auth.module.css";

export interface LoginFormProps {
  returnTo?: string;
  expired?: boolean;
}

function friendlyError(error: unknown): string {
  if (error instanceof BrowserAuthError) {
    if (error.status === 401) return "Email hoặc mật khẩu chưa đúng.";
    if (error.status === 403) return "Tài khoản không có quyền truy cập hoặc đã bị vô hiệu hóa.";
    if (error.status === 422) return "Vui lòng kiểm tra lại email và mật khẩu.";
    if (error.status === 503) return "Dịch vụ EduMS hiện chưa kết nối được. Vui lòng thử lại sau.";
    return error.message;
  }
  return "Không thể kết nối tới EduMS. Vui lòng kiểm tra kết nối mạng và thử lại.";
}

export function LoginForm({ returnTo, expired = false }: LoginFormProps) {
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<LoginFieldErrors>({});
  const submittingRef = useRef(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submittingRef.current) return;
    setError(null);
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    const validationErrors = validateLoginFields(email, password);
    setFieldErrors(validationErrors);
    if (hasLoginFieldErrors(validationErrors)) {
      if (validationErrors.email) emailRef.current?.focus();
      else passwordRef.current?.focus();
      return;
    }
    submittingRef.current = true;
    setPending(true);
    try {
      const result = await authenticatedMutation("/auth/login", {
        email,
        password,
        ...(returnTo ? { return_to: returnTo } : {}),
      });
      const destination = typeof result.redirect_to === "string" ? result.redirect_to : "/";
      window.location.assign(destination);
    } catch (caught) {
      setError(friendlyError(caught));
      submittingRef.current = false;
      setPending(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      {expired ? (
        <div className={styles.notice} role="status">
          <Info className={styles.bannerIcon} size={18} aria-hidden="true" />
          <span>Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để tiếp tục.</span>
        </div>
      ) : null}

      <div className={styles.fieldGroup}>
        <label className={styles.field} htmlFor="login-email">
          <span className={styles.fieldLabel}>Email tài khoản</span>
          <span className={`${styles.inputWrap} ${fieldErrors.email ? styles.inputWrapInvalid : ""}`}>
            <Mail className={styles.inputIcon} size={18} aria-hidden="true" />
            <input
              id="login-email"
              ref={emailRef}
              name="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              required
              maxLength={254}
              placeholder="hocsinh@edums.vn"
              disabled={pending}
              aria-invalid={Boolean(fieldErrors.email)}
              aria-describedby={fieldErrors.email ? "login-email-error" : undefined}
              onChange={() => {
                if (fieldErrors.email) setFieldErrors((current) => ({ ...current, email: undefined }));
              }}
            />
          </span>
          {fieldErrors.email ? (
            <span id="login-email-error" className={styles.fieldError}>
              {fieldErrors.email}
            </span>
          ) : null}
        </label>
      </div>

      <div className={styles.fieldGroup}>
        <label className={styles.field} htmlFor="login-password">
          <span className={styles.fieldLabel}>Mật khẩu</span>
          <span className={`${styles.inputWrap} ${fieldErrors.password ? styles.inputWrapInvalid : ""}`}>
            <LockKeyhole className={styles.inputIcon} size={18} aria-hidden="true" />
            <input
              id="login-password"
              ref={passwordRef}
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              maxLength={128}
              placeholder="Nhập mật khẩu"
              disabled={pending}
              aria-invalid={Boolean(fieldErrors.password)}
              aria-describedby={fieldErrors.password ? "login-password-error" : undefined}
              onChange={() => {
                if (fieldErrors.password) setFieldErrors((current) => ({ ...current, password: undefined }));
              }}
            />
            <button
              className={styles.reveal}
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
              aria-pressed={showPassword}
              disabled={pending}
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </span>
          {fieldErrors.password ? (
            <span id="login-password-error" className={styles.fieldError}>
              {fieldErrors.password}
            </span>
          ) : null}
        </label>
      </div>

      {error ? (
        <div className={styles.error} role="alert" aria-live="assertive">
          <AlertCircle className={styles.bannerIcon} size={18} aria-hidden="true" />
          <span>{error}</span>
        </div>
      ) : null}

      <GradientButton className={styles.submit} type="submit" disabled={pending}>
        {pending ? <LoaderCircle className={styles.spinner} size={19} aria-hidden="true" /> : null}
        <span>{pending ? "Đang xác thực thông tin..." : "Vào không gian học tập"}</span>
        {!pending ? <ArrowRight size={18} aria-hidden="true" /> : null}
      </GradientButton>

      <div className={styles.securityBadge}>
        <ShieldCheck className={styles.securityIcon} size={16} aria-hidden="true" />
        <p className={styles.privacy}>
          Bảo mật đa tầng bằng cookie HttpOnly và chữ ký số. EduMS không lưu trữ mã thông báo trong trình duyệt.
        </p>
      </div>
    </form>
  );
}
