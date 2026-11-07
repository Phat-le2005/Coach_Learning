import { ApiNetworkError, ApiResponseError } from "../../../lib/api/client";
import { ApiContractError } from "../../../lib/api/validation";

const MESSAGES: Readonly<Record<string, string>> = {
  PAPER_OCR_NOT_CONFIGURED: "Dịch vụ đọc bài chụp chưa sẵn sàng do cấu hình máy chủ. Ảnh đã tải lên vẫn được giữ lại; em có thể nhập bước ở dưới.",
  PAPER_OCR_RATE_LIMITED: "Dịch vụ đang hết lượt nhận diện. Ảnh vẫn được giữ lại; hãy thử sau hoặc nhập bước ở dưới.",
  PAPER_OCR_UNAVAILABLE: "Dịch vụ nhận diện đang tạm thời gián đoạn, kể cả sau khi thử kết nối lại. Ảnh và các bước đã lưu vẫn còn. Hãy bấm trích xuất OCR lại sau hoặc nhập bước ở dưới.",
  PAPER_OCR_TIMEOUT: "Nhận diện mất quá nhiều thời gian. Ảnh vẫn được giữ lại; hãy thử lại hoặc tải từng trang rõ nét hơn.",
  PAPER_OCR_INVALID: "Kết quả nhận diện chưa hợp lệ nên chưa được lưu thành bước giải. Hãy thử lại với ảnh rõ hơn hoặc nhập bước ở dưới.",
  PAPER_OCR_REQUEST_REJECTED: "Dịch vụ chưa xử lý được ảnh/PDF này. Ảnh gốc vẫn được giữ lại; hãy thử ảnh PNG/JPEG khác hoặc tải từng trang.",
};

export function paperOcrErrorMessage(cause: unknown): string {
  if (cause instanceof ApiResponseError) {
    if (cause.status === 401) return "Phiên đăng nhập đã hết hạn. Giữ trang này mở, đăng nhập lại rồi thử tiếp.";
    if (cause.status === 403) return "Tài khoản hiện tại không có quyền đọc bài chụp này.";
    if (cause.status === 404) return "Không tìm thấy bài chụp đã chọn. Hãy tải lại danh sách tệp.";
    if (cause.status === 409) return "Bài làm đã đóng hoặc đã thay đổi. Hãy kiểm tra trạng thái trước khi trích xuất lại.";
    if (MESSAGES[cause.code]) return MESSAGES[cause.code]!;
    if (cause.status === 429) return MESSAGES.PAPER_OCR_RATE_LIMITED!;
  }
  if (cause instanceof ApiNetworkError) return "Mất kết nối tới máy chủ khi nhận diện. Ảnh và các bước đã lưu vẫn được giữ lại; hãy kiểm tra kết nối rồi thử lại.";
  if (cause instanceof ApiContractError) return MESSAGES.PAPER_OCR_INVALID!;
  // Never display raw upstream messages, response bodies, or configuration.
  return "Chưa trích xuất được bài chụp. Ảnh và các bước đã lưu vẫn còn; hãy thử lại hoặc nhập bước ở dưới.";
}
