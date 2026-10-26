"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getActionCopy = getActionCopy;
exports.getPriorityReasonCopy = getPriorityReasonCopy;
exports.getRegionStateCopy = getRegionStateCopy;
const actionCopy = {
    CONTINUE_REPAIR: {
        title: "Khôi phục phần nền tảng đang cản bước tiến của bạn.",
        description: "Một mắt xích vững hơn sẽ giúp những phần tiếp theo trở nên nhẹ nhàng hơn.",
        primaryLabel: "Tiếp tục phục hồi",
    },
    CONTINUE_VERIFICATION: {
        title: "Kiểm tra lại một mắt xích quan trọng trước khi tiếp tục.",
        description: "Một lượt kiểm tra ngắn sẽ giúp lộ trình tiếp theo chính xác hơn.",
        primaryLabel: "Tiếp tục kiểm tra",
    },
    CONTINUE_ASSIGNMENT: {
        title: "Bạn đang có một bài tập chưa hoàn thành.",
        description: "Quay lại đúng vị trí đã dừng để giữ mạch suy nghĩ liền mạch.",
        primaryLabel: "Tiếp tục bài tập",
    },
    COMPLETE_OVERDUE_ASSIGNMENT: {
        title: "Hoàn thành phần còn lại để giữ nhịp học ổn định.",
        description: "Ưu tiên phần đang trễ trước khi mở thêm một mục tiêu mới.",
        primaryLabel: "Hoàn thành bài tập",
    },
    CONTINUE_PRACTICE: {
        title: "Tiếp tục phiên luyện tập đang dang dở.",
        description: "Mạch luyện tập hiện tại đang phù hợp với tiến độ của bạn.",
        primaryLabel: "Tiếp tục luyện tập",
    },
    REVIEW_DUE: {
        title: "Một vài kiến thức đã đến lúc cần được củng cố lại.",
        description: "Ôn đúng thời điểm giúp kiến thức được giữ lại lâu hơn.",
        primaryLabel: "Ôn ngay",
    },
    TODAY_TASK: {
        title: "Nhiệm vụ tiếp theo trong lộ trình hôm nay đã sẵn sàng.",
        description: "Một bước tập trung lúc này sẽ tạo đà cho phần còn lại của ngày.",
        primaryLabel: "Bắt đầu nhiệm vụ",
    },
    LEARNING_PRIORITY: {
        title: "Đây là mục tiêu quan trọng nhất để bạn tiến lên lúc này.",
        description: "Lộ trình đang ưu tiên phần có tác động lớn nhất đến tiến bộ tiếp theo.",
        primaryLabel: "Tiếp tục học",
    },
    IDLE: {
        title: "Hôm nay là một điểm khởi đầu mới.",
        description: "Chọn một mục tiêu vừa sức và bắt đầu bằng một bước rõ ràng.",
        primaryLabel: "Khám phá hôm nay",
    },
};
const priorityReasonCopy = {
    VERIFIED_ROOT_CAUSE: "Nền tảng cần củng cố",
    PREREQUISITE_REPAIR: "Kiến thức tiên quyết",
    CURRENT_LESSON: "Bài đang học",
    REVIEW_DUE: "Đến hạn ôn",
    WEAK_PROBLEM_TYPE: "Dạng bài cần luyện",
    WEAK_CONCEPT: "Khái niệm cần củng cố",
};
const regionStateCopy = {
    mastered: "Đã vững",
    developing: "Đang phát triển",
    weak: "Cần chăm sóc",
    review: "Đến hạn ôn",
    not_started: "Chưa bắt đầu",
};
function getActionCopy(type) {
    return actionCopy[type];
}
function getPriorityReasonCopy(code) {
    var _a;
    return (_a = priorityReasonCopy[code]) !== null && _a !== void 0 ? _a : "Ưu tiên học tập";
}
function getRegionStateCopy(state) {
    return regionStateCopy[state];
}
