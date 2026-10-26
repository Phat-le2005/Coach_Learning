"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.resolveStudentAction = resolveStudentAction;
/**
 * Registry of client-implemented routes.
 * Workspace routes (practice, repair, review) will be connected in FE-REAL-03.
 * Currently, no sub-workspace routes exist in app/student/.
 */
const AVAILABLE_ROUTES = {};
function resolveStudentAction(action) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p, _q, _r, _s, _t, _u, _v, _w, _x, _y, _z, _0, _1, _2;
    const type = action.action_type;
    const targetName = (_a = action.target_name) !== null && _a !== void 0 ? _a : undefined;
    const targetCode = (_b = action.target_code) !== null && _b !== void 0 ? _b : undefined;
    const targetType = (_c = action.target_type) !== null && _c !== void 0 ? _c : undefined;
    const reasonCode = (_d = action.reason_code) !== null && _d !== void 0 ? _d : undefined;
    const phase = (_e = action.phase) !== null && _e !== void 0 ? _e : undefined;
    const repairCycleIndex = (_f = action.repair_cycle_index) !== null && _f !== void 0 ? _f : undefined;
    let resourceId;
    let resourceType;
    let title = "Không gian học tập";
    let description = "Dữ liệu học tập cá nhân hóa đã kết nối.";
    let primaryLabel = "Xem chi tiết";
    let badgeLabel = "Học tập";
    let guidanceText = "Thông tin trạng thái được đọc trực tiếp từ hệ thống backend EduMS.";
    switch (type) {
        case "CONTINUE_REPAIR": {
            resourceId = (_h = (_g = action.adaptive_repair_session_id) !== null && _g !== void 0 ? _g : action.resource_id) !== null && _h !== void 0 ? _h : undefined;
            resourceType = "adaptive_repair_session";
            title = "Tiếp tục vá mắt xích hổng kiến thức";
            description = "Hệ thống đã xác minh nguyên nhân gốc rễ. Bạn đang trong phiên sửa sai thích ứng để củng cố vững chắc nền tảng kiến thức.";
            primaryLabel = "Xem chi tiết mắt xích";
            badgeLabel = phase ? `Vá sửa sai · Giai đoạn ${phase}` : "Vá sửa sai thích ứng";
            guidanceText = "Phiên sửa sai thích ứng tập trung khắc phục ngộ nhận cốt lõi. Giao diện làm bài trực tiếp (Repair Workspace) đang được chuẩn bị trong phân hệ FE-REAL-03.";
            break;
        }
        case "CONTINUE_VERIFICATION": {
            resourceId = (_k = (_j = action.verification_id) !== null && _j !== void 0 ? _j : action.resource_id) !== null && _k !== void 0 ? _k : undefined;
            resourceType = "root_cause_verification";
            title = "Tiếp tục xác minh lỗ hổng kiến thức";
            description = "Hệ thống đang kiểm chứng giả thuyết về ngộ nhận kiến thức để đưa ra lộ trình sửa sai chính xác nhất.";
            primaryLabel = "Xem mục tiêu xác minh";
            badgeLabel = "Xác minh ngộ nhận";
            guidanceText = "Phiên xác minh kiểm tra xem bạn có thực sự gặp khó khăn ở mắt xích này không trước khi mở chu kỳ sửa sai.";
            break;
        }
        case "CONTINUE_ASSIGNMENT": {
            resourceId = (_m = (_l = action.assignment_id) !== null && _l !== void 0 ? _l : action.resource_id) !== null && _m !== void 0 ? _m : undefined;
            resourceType = "classroom_assignment";
            title = "Tiếp tục làm bài tập được giao";
            description = "Bạn có bài tập từ lớp học đang trong trạng thái làm dở dang cần hoàn thành.";
            primaryLabel = "Xem thông tin bài tập";
            badgeLabel = "Bài tập đang làm";
            guidanceText = "Bài tập được giáo viên giao trong lớp học. Không gian nộp và làm bài trực tuyến sẽ được kết nối trong phân hệ bài tập.";
            break;
        }
        case "COMPLETE_OVERDUE_ASSIGNMENT": {
            resourceId = (_p = (_o = action.assignment_id) !== null && _o !== void 0 ? _o : action.resource_id) !== null && _p !== void 0 ? _p : undefined;
            resourceType = "classroom_assignment";
            title = "Hoàn thành bài tập đã quá hạn";
            description = "Bài tập từ lớp học đã vượt quá thời hạn nộp bài. Hãy ưu tiên hoàn thành sớm để không gián đoạn tiến độ học.";
            primaryLabel = "Xem bài quá hạn";
            badgeLabel = "Quá hạn nộp bài";
            guidanceText = "Bài tập đã quá hạn chót. Bạn vẫn có thể xem lại thông tin bài tập và nộp bổ sung theo quy định lớp học.";
            break;
        }
        case "CONTINUE_PRACTICE": {
            resourceId = (_r = (_q = action.practice_session_id) !== null && _q !== void 0 ? _q : action.resource_id) !== null && _r !== void 0 ? _r : undefined;
            resourceType = "practice_session";
            title = "Tiếp tục phiên luyện tập";
            description = "Bạn có một phiên luyện tập tự do chưa hoàn thành hoặc chưa nộp kết quả.";
            primaryLabel = "Xem phiên luyện tập";
            badgeLabel = "Phiên luyện tập dở dang";
            guidanceText = "Không gian làm bài luyện tập cá nhân (Practice Workspace) sẽ được ra mắt trong phân hệ FE-REAL-03.";
            break;
        }
        case "REVIEW_DUE": {
            resourceId = (_u = (_t = (_s = action.problem_type_id) !== null && _s !== void 0 ? _s : action.concept_id) !== null && _t !== void 0 ? _t : action.resource_id) !== null && _u !== void 0 ? _u : undefined;
            resourceType = (_v = action.target_type) !== null && _v !== void 0 ? _v : "review_target";
            title = "Ôn tập kiến thức đến hạn";
            description = "Mục tiêu học tập đã đến chu kỳ lặp lại ngắt quãng để củng cố trí nhớ dài hạn và chống quên.";
            primaryLabel = "Xem nội dung cần ôn";
            badgeLabel = "Đến hạn ôn tập";
            guidanceText = "Thuật toán Spaced Repetition tính toán thời điểm vàng để ôn lại kiến thức trước khi rơi vào vùng quên lãng.";
            break;
        }
        case "TODAY_TASK": {
            resourceId = (_x = (_w = action.study_task_id) !== null && _w !== void 0 ? _w : action.resource_id) !== null && _x !== void 0 ? _x : undefined;
            resourceType = "study_task";
            title = "Nhiệm vụ kế hoạch hôm nay";
            description = "Kế hoạch ngày của bạn có một nhiệm vụ trọng tâm được ưu tiên cao nhất cần hoàn thành.";
            primaryLabel = "Xem nhiệm vụ hôm nay";
            badgeLabel = "Kế hoạch ngày";
            guidanceText = "Nhiệm vụ thuộc Kế hoạch học tập cá nhân hóa được thuật toán phân bổ theo thời gian và mục tiêu học tập.";
            break;
        }
        case "LEARNING_PRIORITY": {
            resourceId = (_0 = (_z = (_y = action.problem_type_id) !== null && _y !== void 0 ? _y : action.concept_id) !== null && _z !== void 0 ? _z : action.resource_id) !== null && _0 !== void 0 ? _0 : undefined;
            resourceType = (_1 = action.target_type) !== null && _1 !== void 0 ? _1 : "learning_priority";
            title = "Luyện tập mục tiêu ưu tiên";
            description = "Mục tiêu quan trọng nhất được gợi ý dựa trên năng lực hiện tại và mục tiêu điểm số của bạn.";
            primaryLabel = "Xem mục tiêu gợi ý";
            badgeLabel = "Gợi ý ưu tiên";
            guidanceText = "Thuật toán đề xuất dạng bài này để tối ưu hóa hiệu quả học tập và tạo đà bứt phá điểm số.";
            break;
        }
        case "IDLE":
        default: {
            resourceId = undefined;
            resourceType = undefined;
            title = "Không gian học tập sẵn sàng";
            description = "Hiện tại bạn không có nhiệm vụ khẩn cấp nào. Mọi bài tập và lượt ôn đều đang ở trạng thái tốt.";
            primaryLabel = "Xem trạng thái học tập";
            badgeLabel = "Trạng thái sẵn sàng";
            guidanceText = "Tất cả bài tập lớp, phiên sửa sai và lịch ôn tập đều đang ở trạng thái tốt. Bạn có thể xem lộ trình ưu tiên bên dưới để tự học thêm.";
            break;
        }
    }
    const routeResolver = AVAILABLE_ROUTES[type];
    const route = routeResolver ? (_2 = routeResolver(action)) !== null && _2 !== void 0 ? _2 : undefined : undefined;
    const hasAvailableRoute = Boolean(route);
    return {
        type,
        title,
        description,
        primaryLabel,
        targetName,
        targetCode,
        targetType,
        reasonCode,
        resourceId,
        resourceType,
        phase,
        repairCycleIndex,
        hasAvailableRoute,
        route,
        badgeLabel,
        guidanceText,
    };
}
