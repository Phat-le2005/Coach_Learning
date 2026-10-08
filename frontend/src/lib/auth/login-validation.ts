export interface LoginFieldErrors {
  email?: string;
  password?: string;
}

const SIMPLE_EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/u;

export function validateLoginFields(email: string, password: string): LoginFieldErrors {
  const errors: LoginFieldErrors = {};
  const normalizedEmail = email.trim();

  if (!normalizedEmail) errors.email = "Vui lòng nhập email.";
  else if (normalizedEmail.length > 254 || !SIMPLE_EMAIL_PATTERN.test(normalizedEmail)) errors.email = "Email chưa đúng định dạng.";

  if (!password) errors.password = "Vui lòng nhập mật khẩu.";
  else if (password.length > 128) errors.password = "Mật khẩu không được vượt quá 128 ký tự.";

  return errors;
}

export function hasLoginFieldErrors(errors: LoginFieldErrors): boolean {
  return Boolean(errors.email || errors.password);
}
