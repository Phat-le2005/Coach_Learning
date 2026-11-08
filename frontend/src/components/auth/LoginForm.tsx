"use client";

import {
  AlertCircle,
  ArrowRight,
  Eye,
  EyeOff,
  Info,
  LoaderCircle,
  Lock,
  LockKeyhole,
  Mail,
  ShieldCheck,
  User,
  UserPlus,
} from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import { GradientButton } from "@/components/ui/GradientButton";
import { authenticatedMutation, BrowserAuthError } from "@/lib/auth/browser";
import {
  hasLoginFieldErrors,
  validateLoginFields,
  validateRegisterFields,
  type LoginFieldErrors,
} from "@/lib/auth/login-validation";

import styles from "./auth.module.css";

export interface LoginFormProps {
  returnTo?: string;
  expired?: boolean;
  initialMode?: "login" | "register";
}

function friendlyError(error: unknown, mode: "login" | "register"): string {
  if (error instanceof BrowserAuthError) {
    if (error.status === 401) return "Email hoặc mật khẩu chưa đúng.";
    if (error.status === 403) return "Tài khoản không có quyền truy cập hoặc đã bị vô hiệu hóa.";
    if (error.status === 409) return "Email này đã được đăng ký. Vui lòng đăng nhập hoặc dùng email khác.";
    if (error.status === 422) {
      return mode === "register"
        ? "Thông tin đăng ký chưa hợp lệ (mật khẩu cần tối thiểu 12 ký tự)."
        : "Vui lòng kiểm tra lại email và mật khẩu.";
    }
    if (error.status === 503) return "Dịch vụ EduMS hiện chưa kết nối được. Vui lòng thử lại sau.";
    return error.message;
  }
  return "Không thể kết nối tới EduMS. Vui lòng kiểm tra kết nối mạng và thử lại.";
}

export function LoginForm({ returnTo, expired = false, initialMode = "login" }: LoginFormProps) {
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<LoginFieldErrors>({});
  const submittingRef = useRef(false);
  const fullNameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmPasswordRef = useRef<HTMLInputElement>(null);

  function switchMode(nextMode: "login" | "register") {
    if (pending || nextMode === mode) return;
    setMode(nextMode);
    setError(null);
    setFieldErrors({});
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submittingRef.current) return;
    setError(null);
    const form = new FormData(event.currentTarget);
    const fullName = String(form.get("full_name") ?? "").trim();
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    const confirmPassword = String(form.get("confirm_password") ?? "");

    const validationErrors =
      mode === "register"
        ? validateRegisterFields(fullName, email, password, confirmPassword)
        : validateLoginFields(email, password);
    setFieldErrors(validationErrors);
    if (hasLoginFieldErrors(validationErrors)) {
      if (validationErrors.fullName) fullNameRef.current?.focus();
      else if (validationErrors.email) emailRef.current?.focus();
      else if (validationErrors.password) passwordRef.current?.focus();
      else if (validationErrors.confirmPassword) confirmPasswordRef.current?.focus();
      return;
    }

    submittingRef.current = true;
    setPending(true);
    try {
      const endpoint = mode === "register" ? "/auth/register" : "/auth/login";
      const payload =
        mode === "register"
          ? {
              full_name: fullName,
              email,
              password,
              ...(returnTo ? { return_to: returnTo } : {}),
            }
          : {
              email,
              password,
              ...(returnTo ? { return_to: returnTo } : {}),
            };
      const result = await authenticatedMutation(endpoint, payload);
      const destination = typeof result.redirect_to === "string" ? result.redirect_to : "/";
      window.location.assign(destination);
    } catch (caught) {
      setError(friendlyError(caught, mode));
      submittingRef.current = false;
      setPending(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <div className={styles.cardHeaderBlock}>
        <div className={styles.cardBadge}>
          {mode === "register" ? (
            <UserPlus size={12} aria-hidden="true" />
          ) : (
            <Lock size={12} aria-hidden="true" />
          )}
          <span>{mode === "register" ? "Khởi tạo mầm tri thức" : "Cổng truy cập an toàn"}</span>
        </div>
        <h2 className={styles.cardTitle}>
          {mode === "register" ? "Đăng ký tài khoản" : "Đăng nhập"}
        </h2>
        <p className={styles.cardSubtitle}>
          {mode === "register"
            ? "Tạo tài khoản Học sinh mới để bắt đầu hành trình học tập cá nhân hóa."
            : "Sử dụng tài khoản của bạn để tiếp tục hành trình học tập."}
        </p>
      </div>

      <div className={styles.modeTabs} role="tablist" aria-label="Chọn chế độ xác thực">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "login"}
          className={`${styles.modeTabBtn} ${mode === "login" ? styles.modeTabBtnActive : ""}`}
          onClick={() => switchMode("login")}
          disabled={pending}
        >
          Đăng nhập
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "register"}
          className={`${styles.modeTabBtn} ${mode === "register" ? styles.modeTabBtnActive : ""}`}
          onClick={() => switchMode("register")}
          disabled={pending}
        >
          Đăng ký mới
        </button>
      </div>

      {expired ? (
        <div className={styles.notice} role="status">
          <Info className={styles.bannerIcon} size={18} aria-hidden="true" />
          <span>Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để tiếp tục.</span>
        </div>
      ) : null}

      {mode === "register" ? (
        <div className={styles.fieldGroup}>
          <label className={styles.field} htmlFor="register-full-name">
            <span className={styles.fieldLabel}>Họ và tên</span>
            <span
              className={`${styles.inputWrap} ${fieldErrors.fullName ? styles.inputWrapInvalid : ""}`}
            >
              <User className={styles.inputIcon} size={18} aria-hidden="true" />
              <input
                id="register-full-name"
                ref={fullNameRef}
                name="full_name"
                type="text"
                autoComplete="name"
                required
                maxLength={200}
                placeholder="Nguyễn Văn An"
                disabled={pending}
                aria-invalid={Boolean(fieldErrors.fullName)}
                aria-describedby={fieldErrors.fullName ? "register-fullname-error" : undefined}
                onChange={() => {
                  if (fieldErrors.fullName) {
                    setFieldErrors((current) => ({ ...current, fullName: undefined }));
                  }
                }}
              />
            </span>
            {fieldErrors.fullName ? (
              <span id="register-fullname-error" className={styles.fieldError}>
                {fieldErrors.fullName}
              </span>
            ) : null}
          </label>
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
          <span className={styles.fieldLabel}>
            {mode === "register" ? "Mật khẩu (tối thiểu 12 ký tự)" : "Mật khẩu"}
          </span>
          <span className={`${styles.inputWrap} ${fieldErrors.password ? styles.inputWrapInvalid : ""}`}>
            <LockKeyhole className={styles.inputIcon} size={18} aria-hidden="true" />
            <input
              id="login-password"
              ref={passwordRef}
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              required
              maxLength={128}
              placeholder={mode === "register" ? "Tối thiểu 12 ký tự" : "Nhập mật khẩu"}
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

      {mode === "register" ? (
        <div className={styles.fieldGroup}>
          <label className={styles.field} htmlFor="register-confirm-password">
            <span className={styles.fieldLabel}>Xác nhận mật khẩu</span>
            <span
              className={`${styles.inputWrap} ${
                fieldErrors.confirmPassword ? styles.inputWrapInvalid : ""
              }`}
            >
              <LockKeyhole className={styles.inputIcon} size={18} aria-hidden="true" />
              <input
                id="register-confirm-password"
                ref={confirmPasswordRef}
                name="confirm_password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                required
                maxLength={128}
                placeholder="Nhập lại mật khẩu"
                disabled={pending}
                aria-invalid={Boolean(fieldErrors.confirmPassword)}
                aria-describedby={
                  fieldErrors.confirmPassword ? "register-confirm-error" : undefined
                }
                onChange={() => {
                  if (fieldErrors.confirmPassword) {
                    setFieldErrors((current) => ({ ...current, confirmPassword: undefined }));
                  }
                }}
              />
            </span>
            {fieldErrors.confirmPassword ? (
              <span id="register-confirm-error" className={styles.fieldError}>
                {fieldErrors.confirmPassword}
              </span>
            ) : null}
          </label>
        </div>
      ) : null}

      {error ? (
        <div className={styles.error} role="alert" aria-live="assertive">
          <AlertCircle className={styles.bannerIcon} size={18} aria-hidden="true" />
          <span>{error}</span>
        </div>
      ) : null}

      <GradientButton className={styles.submit} type="submit" disabled={pending}>
        {pending ? <LoaderCircle className={styles.spinner} size={19} aria-hidden="true" /> : null}
        <span>
          {pending
            ? mode === "register"
              ? "Đang khởi tạo tài khoản..."
              : "Đang xác thực thông tin..."
            : mode === "register"
              ? "Đăng ký và vào học ngay"
              : "Vào không gian học tập"}
        </span>
        {!pending ? <ArrowRight size={18} aria-hidden="true" /> : null}
      </GradientButton>

      <div className={styles.switchModeRow}>
        {mode === "login" ? (
          <span>
            Chưa có tài khoản học sinh?{" "}
            <button
              type="button"
              className={styles.switchModeLink}
              onClick={() => switchMode("register")}
              disabled={pending}
            >
              Đăng ký ngay
            </button>
          </span>
        ) : (
          <span>
            Đã có tài khoản trên hệ thống?{" "}
            <button
              type="button"
              className={styles.switchModeLink}
              onClick={() => switchMode("login")}
              disabled={pending}
            >
              Đăng nhập
            </button>
          </span>
        )}
      </div>

      <div className={styles.securityBadge}>
        <ShieldCheck className={styles.securityIcon} size={16} aria-hidden="true" />
        <p className={styles.privacy}>
          Bảo mật đa tầng bằng cookie HttpOnly và chữ ký số. EduMS không lưu trữ mã thông báo trong trình duyệt.
        </p>
      </div>
    </form>
  );
}
