"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.validateLoginFields = validateLoginFields;
exports.hasLoginFieldErrors = hasLoginFieldErrors;
const SIMPLE_EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/u;
function validateLoginFields(email, password) {
    const errors = {};
    const normalizedEmail = email.trim();
    if (!normalizedEmail)
        errors.email = "Vui lòng nhập email.";
    else if (normalizedEmail.length > 254 || !SIMPLE_EMAIL_PATTERN.test(normalizedEmail))
        errors.email = "Email chưa đúng định dạng.";
    if (!password)
        errors.password = "Vui lòng nhập mật khẩu.";
    else if (password.length > 128)
        errors.password = "Mật khẩu không được vượt quá 128 ký tự.";
    return errors;
}
function hasLoginFieldErrors(errors) {
    return Boolean(errors.email || errors.password);
}
