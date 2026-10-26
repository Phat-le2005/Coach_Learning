"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.CORRECTION_KEYS = void 0;
exports.insertCorrectionKey = insertCorrectionKey;
exports.toConfirmedLatex = toConfirmedLatex;
exports.CORRECTION_KEYS = [
    { label: "7", insert: "7", description: "Chèn số 7" },
    { label: "8", insert: "8", description: "Chèn số 8" },
    { label: "9", insert: "9", description: "Chèn số 9" },
    { label: "+", insert: "+", description: "Chèn dấu cộng" },
    { label: "−", insert: "-", description: "Chèn dấu trừ" },
    { label: "=", insert: "=", description: "Chèn dấu bằng" },
    { label: "4", insert: "4", description: "Chèn số 4" },
    { label: "5", insert: "5", description: "Chèn số 5" },
    { label: "6", insert: "6", description: "Chèn số 6" },
    { label: "×", insert: "×", description: "Chèn dấu nhân" },
    { label: "÷", insert: "÷", description: "Chèn dấu chia" },
    { label: "(", insert: "(", description: "Mở ngoặc" },
    { label: "1", insert: "1", description: "Chèn số 1" },
    { label: "2", insert: "2", description: "Chèn số 2" },
    { label: "3", insert: "3", description: "Chèn số 3" },
    { label: ")", insert: ")", description: "Đóng ngoặc" },
    { label: "x", insert: "x", description: "Chèn biến x" },
    { label: "y", insert: "y", description: "Chèn biến y" },
    { label: "0", insert: "0", description: "Chèn số 0" },
    { label: "π", insert: "π", description: "Chèn số pi" },
    { label: "x²", insert: "^2", description: "Bình phương biểu thức trước con trỏ" },
    { label: "xⁿ", insert: "^(□)", description: "Thêm số mũ, điền vào ô vuông" },
    { label: "√", insert: "√(□)", description: "Thêm căn bậc hai, điền vào ô vuông" },
    { label: "a/b", insert: "(□)/(□)", description: "Thêm phân số, điền tử và mẫu" },
];
function insertCorrectionKey(current, selectionStart, selectionEnd, template) {
    const start = Math.max(0, Math.min(current.length, selectionStart));
    const end = Math.max(start, Math.min(current.length, selectionEnd));
    const selected = current.slice(start, end);
    const insertion = selected && template.includes("□")
        ? template.replace("□", selected)
        : selected && template.startsWith("^")
            ? selected + template
            : template;
    const value = current.slice(0, start) + insertion + current.slice(end);
    const placeholder = insertion.indexOf("□");
    const cursor = start + insertion.length;
    return {
        value,
        selectionStart: placeholder >= 0 ? start + placeholder : cursor,
        selectionEnd: placeholder >= 0 ? start + placeholder + 1 : cursor,
    };
}
const SYMBOLS = {
    "×": String.raw `\times `,
    "÷": String.raw `\div `,
    "π": String.raw `\pi `,
    "≤": String.raw `\le `,
    "≥": String.raw `\ge `,
    "≠": String.raw `\ne `,
    "·": String.raw `\cdot `,
    "−": "-",
};
function closingParenthesis(input, start) {
    let depth = 0;
    for (let index = start; index < input.length; index += 1) {
        if (input[index] === "(")
            depth += 1;
        if (input[index] === ")") {
            depth -= 1;
            if (depth === 0)
                return index;
        }
    }
    return -1;
}
function convertSegment(input) {
    var _a;
    let converted = "";
    for (let index = 0; index < input.length; index += 1) {
        const isRoot = input.startsWith("√(", index);
        const isPower = input.startsWith("^(", index);
        if (isRoot || isPower) {
            const opening = index + 1;
            const closing = closingParenthesis(input, opening);
            if (closing < 0)
                return null;
            const inner = convertSegment(input.slice(opening + 1, closing));
            if (!(inner === null || inner === void 0 ? void 0 : inner.trim()))
                return null;
            converted += isRoot ? `\\sqrt{${inner}}` : `^{${inner}}`;
            index = closing;
        }
        else if (input[index] === "√") {
            return null;
        }
        else {
            converted += (_a = SYMBOLS[input[index]]) !== null && _a !== void 0 ? _a : input[index];
        }
    }
    return converted;
}
/** Accept familiar math entry while preserving already reviewed LaTeX. */
function toConfirmedLatex(input) {
    const trimmed = input.trim();
    if (!trimmed || trimmed.length > 1000 || trimmed.includes("□"))
        return null;
    const converted = convertSegment(trimmed);
    if (converted === null)
        return null;
    // Explicit (numerator)/(denominator) from the keypad becomes a displayed fraction.
    return converted.replace(/\(([^()]+)\)\/\(([^()]+)\)/g, String.raw `\frac{$1}{$2}`);
}
