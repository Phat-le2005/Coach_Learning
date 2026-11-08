import type { StudentCurrentActionRead } from "../../lib/api/contracts";
import type { StudentHomeActionType } from "./types";

export interface ResolvedStudentAction {
  type: StudentHomeActionType;
  title: string;
  description: string;
  primaryLabel: string;
  targetName?: string;
  targetCode?: string;
  targetType?: string;
  reasonCode?: string;
  resourceId?: string;
  resourceType?: string;
  phase?: string;
  repairCycleIndex?: number;
  hasAvailableRoute: boolean;
  route?: string;
  badgeLabel: string;
  guidanceText: string;
}

/**
 * Registry of client-implemented routes mapped directly to real student workspace pages.
 */
const AVAILABLE_ROUTES: Partial<
  Record<StudentHomeActionType, (action: StudentCurrentActionRead) => string | null>
> = {
  CONTINUE_REPAIR: (action) =>
    action.problem_type_id
      ? `/student/practice?problem_type_id=${encodeURIComponent(action.problem_type_id)}`
      : action.concept_id
      ? `/student/practice?concept_id=${encodeURIComponent(action.concept_id)}`
      : "/student/practice",
  CONTINUE_VERIFICATION: (action) =>
    action.concept_id
      ? `/student/practice?concept_id=${encodeURIComponent(action.concept_id)}`
      : action.problem_type_id
      ? `/student/practice?problem_type_id=${encodeURIComponent(action.problem_type_id)}`
      : "/student/practice",
  CONTINUE_ASSIGNMENT: (action) =>
    action.assignment_id
      ? `/student/assignments/${encodeURIComponent(action.assignment_id)}`
      : "/student/attempts?tab=classroom",
  COMPLETE_OVERDUE_ASSIGNMENT: (action) =>
    action.assignment_id
      ? `/student/assignments/${encodeURIComponent(action.assignment_id)}`
      : "/student/attempts?tab=classroom",
  CONTINUE_PRACTICE: (action) =>
    action.problem_type_id
      ? `/student/practice?problem_type_id=${encodeURIComponent(action.problem_type_id)}`
      : action.concept_id
      ? `/student/practice?concept_id=${encodeURIComponent(action.concept_id)}`
      : "/student/practice",
  REVIEW_DUE: (action) =>
    action.problem_type_id
      ? `/student/practice?problem_type_id=${encodeURIComponent(action.problem_type_id)}`
      : action.concept_id
      ? `/student/practice?concept_id=${encodeURIComponent(action.concept_id)}`
      : "/student/practice",
  TODAY_TASK: (action) =>
    action.problem_type_id
      ? `/student/practice?problem_type_id=${encodeURIComponent(action.problem_type_id)}`
      : action.concept_id
      ? `/student/practice?concept_id=${encodeURIComponent(action.concept_id)}`
      : "/student/practice",
  LEARNING_PRIORITY: (action) =>
    action.problem_type_id
      ? `/student/practice?problem_type_id=${encodeURIComponent(action.problem_type_id)}`
      : action.concept_id
      ? `/student/practice?concept_id=${encodeURIComponent(action.concept_id)}`
      : "/student/practice",
  IDLE: () => "/student/knowledge",
};

export function resolveStudentAction(action: StudentCurrentActionRead): ResolvedStudentAction {
  const type = action.action_type as StudentHomeActionType;
  const targetName = action.target_name ?? undefined;
  const targetCode = action.target_code ?? undefined;
  const targetType = action.target_type ?? undefined;
  const reasonCode = action.reason_code ?? undefined;
  const phase = action.phase ?? undefined;
  const repairCycleIndex = action.repair_cycle_index ?? undefined;

  let resourceId: string | undefined;
  let resourceType: string | undefined;
  let title = "Không gian học tập";
  let description = "Dữ liệu học tập cá nhân hóa đã kết nối.";
  let primaryLabel = "Xem chi tiết";
  let badgeLabel = "Học tập";
  let guidanceText = "Thông tin trạng thái được đọc trực tiếp từ hệ thống backend EduMS.";

  switch (type) {
    case "CONTINUE_REPAIR": {
      resourceId = action.adaptive_repair_session_id ?? action.resource_id ?? undefined;
      resourceType = "adaptive_repair_session";
      title = "Tiếp tục vá mắt xích hổng kiến thức";
      description = "Hệ thống đã xác minh nguyên nhân gốc rễ. Hãy hoàn thành 2-3 câu ngắn để củng cố vững chắc nền tảng.";
      primaryLabel = "Vá mắt xích ngay (~5p)";
      badgeLabel = phase ? `Vá sửa sai · Giai đoạn ${phase}` : "Vá sửa sai thích ứng";
      guidanceText = "Phiên sửa sai thích ứng tập trung khắc phục ngộ nhận cốt lõi. AI đối chiếu từng bước giải để phát hiện sai sót biến đổi ngay lập tức.";
      break;
    }
    case "CONTINUE_VERIFICATION": {
      resourceId = action.verification_id ?? action.resource_id ?? undefined;
      resourceType = "root_cause_verification";
      title = "Tiếp tục xác minh lỗ hổng kiến thức";
      description = "Hệ thống đang kiểm chứng giả thuyết về ngộ nhận kiến thức để đưa ra lộ trình sửa sai chính xác nhất.";
      primaryLabel = "Xác minh ngay (~5p)";
      badgeLabel = "Xác minh ngộ nhận";
      guidanceText = "Phiên xác minh kiểm tra xem bạn có thực sự gặp khó khăn ở mắt xích này không trước khi mở chu kỳ sửa sai.";
      break;
    }
    case "CONTINUE_ASSIGNMENT": {
      resourceId = action.assignment_id ?? action.resource_id ?? undefined;
      resourceType = "classroom_assignment";
      title = "Tiếp tục làm bài tập được giao";
      description = "Bạn có bài tập từ lớp học đang trong trạng thái làm dở dang cần hoàn thành.";
      primaryLabel = "Làm bài tập lớp";
      badgeLabel = "Bài tập đang làm";
      guidanceText = "Bài tập được giáo viên giao trong lớp học, chấm chữa từng bước chuẩn xác từ ngân hàng đề.";
      break;
    }
    case "COMPLETE_OVERDUE_ASSIGNMENT": {
      resourceId = action.assignment_id ?? action.resource_id ?? undefined;
      resourceType = "classroom_assignment";
      title = "Hoàn thành bài tập đã quá hạn";
      description = "Bài tập từ lớp học đã vượt quá thời hạn nộp bài. Hãy ưu tiên hoàn thành sớm để không gián đoạn tiến độ học.";
      primaryLabel = "Nộp bù bài tập";
      badgeLabel = "Quá hạn nộp bài";
      guidanceText = "Bài tập đã quá hạn chót. Bạn vẫn có thể hoàn thành lời giải và gửi hệ thống đối chiếu từng bước.";
      break;
    }
    case "CONTINUE_PRACTICE": {
      resourceId = action.practice_session_id ?? action.resource_id ?? undefined;
      resourceType = "practice_session";
      title = "Tiếp tục phiên luyện tập";
      description = "Bạn có một phiên luyện tập tự do chưa hoàn thành hoặc chưa nộp kết quả.";
      primaryLabel = "Luyện tiếp dạng này";
      badgeLabel = "Phiên luyện tập dở dang";
      guidanceText = "Không gian giải toán từng bước trên giấy kỹ thuật số đang chờ bạn giải quyết câu hỏi tiếp theo.";
      break;
    }
    case "REVIEW_DUE": {
      resourceId = action.problem_type_id ?? action.concept_id ?? action.resource_id ?? undefined;
      resourceType = action.target_type ?? "review_target";
      title = "Ôn tập kiến thức đến hạn";
      description = "Mục tiêu học tập đã đến chu kỳ lặp lại ngắt quãng để củng cố trí nhớ dài hạn và chống quên.";
      primaryLabel = "Ôn tập ngay (~5p)";
      badgeLabel = "Đến hạn ôn tập";
      guidanceText = "Thuật toán Spaced Repetition tính toán thời điểm vàng để ôn lại kiến thức trước khi rơi vào vùng quên lãng.";
      break;
    }
    case "TODAY_TASK": {
      resourceId = action.study_task_id ?? action.resource_id ?? undefined;
      resourceType = "study_task";
      title = "Nhiệm vụ kế hoạch hôm nay";
      description = "Kế hoạch ngày của bạn có một nhiệm vụ trọng tâm được ưu tiên cao nhất cần hoàn thành.";
      primaryLabel = "Thực hiện nhiệm vụ ngày";
      badgeLabel = "Kế hoạch ngày";
      guidanceText = "Nhiệm vụ thuộc Kế hoạch học tập cá nhân hóa được thuật toán phân bổ theo thời gian và mục tiêu học tập.";
      break;
    }
    case "LEARNING_PRIORITY": {
      resourceId = action.problem_type_id ?? action.concept_id ?? action.resource_id ?? undefined;
      resourceType = action.target_type ?? "learning_priority";
      title = "Luyện tập mục tiêu ưu tiên";
      description = "Mục tiêu quan trọng nhất được gợi ý dựa trên năng lực hiện tại và mục tiêu điểm số của bạn.";
      primaryLabel = "Luyện ngay dạng này (~5p)";
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
      primaryLabel = "Khám phá Cây Tri Thức 3D";
      badgeLabel = "Trạng thái sẵn sàng";
      guidanceText = "Tất cả bài tập lớp, phiên sửa sai và lịch ôn tập đều đang ở trạng thái tốt. Bạn có thể xem lộ trình ưu tiên bên dưới để tự học thêm.";
      break;
    }
  }

  const routeResolver = AVAILABLE_ROUTES[type];
  const route = routeResolver ? routeResolver(action) ?? undefined : undefined;
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
