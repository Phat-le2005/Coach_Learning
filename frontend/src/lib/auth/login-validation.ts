export interface LoginFieldErrors {
  fullName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
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

export function validateRegisterFields(
  fullName: string,
  email: string,
  password: string,
  confirmPassword: string
): LoginFieldErrors {
  const errors: LoginFieldErrors = {};
  const normalizedName = fullName.trim();
  const normalizedEmail = email.trim();

  if (!normalizedName) errors.fullName = "Vui lòng nhập họ và tên.";
  else if (normalizedName.length > 200) errors.fullName = "Họ và tên không được vượt quá 200 ký tự.";

  if (!normalizedEmail) errors.email = "Vui lòng nhập email.";
  else if (normalizedEmail.length > 254 || !SIMPLE_EMAIL_PATTERN.test(normalizedEmail)) errors.email = "Email chưa đúng định dạng.";

  if (!password) errors.password = "Vui lòng nhập mật khẩu.";
  else if (password.length < 12) errors.password = "Mật khẩu đăng ký cần ít nhất 12 ký tự.";
  else if (password.length > 128) errors.password = "Mật khẩu không được vượt quá 128 ký tự.";

  if (!confirmPassword) errors.confirmPassword = "Vui lòng xác nhận lại mật khẩu.";
  else if (confirmPassword !== password) errors.confirmPassword = "Mật khẩu xác nhận chưa khớp.";

  return errors;
}

export function hasLoginFieldErrors(errors: LoginFieldErrors): boolean {
  return Boolean(errors.fullName || errors.email || errors.password || errors.confirmPassword);
}
