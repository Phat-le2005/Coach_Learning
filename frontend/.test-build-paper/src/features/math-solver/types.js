"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.STEP_KIND_DISPLAY_NAMES = exports.STEP_KINDS = void 0;
const contracts_1 = require("@/lib/api/contracts");
Object.defineProperty(exports, "STEP_KINDS", { enumerable: true, get: function () { return contracts_1.STEP_KINDS; } });
exports.STEP_KIND_DISPLAY_NAMES = {
    ASSUMPTION: "1. Giả thiết & TXĐ (Assumption)",
    DERIVATIVE_CALCULATION: "2. Tính đạo hàm (Derivative Calculation)",
    ROOT_FINDING: "3. Tìm nghiệm đạo hàm (Root Finding)",
    SIGN_TABLE: "4. Bảng xét dấu (Sign Table)",
    VARIATION_TABLE: "5. Bảng biến thiên (Variation Table)",
    CONCLUSION: "6. Kết luận khoảng đơn điệu (Conclusion)",
    EXPLANATION: "Diễn giải / Lập luận (Explanation)",
    CUSTOM: "Bước giải tự do (Custom Step)",
};
