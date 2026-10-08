import type { DerivedMasteryState } from "@/lib/api/contracts";
import type { KnowledgeBiome, KnowledgeStatusFilter } from "./types";

export function getMasteryStateLabel(state: DerivedMasteryState): string {
  switch (state) {
    case "MASTERED":
      return "Đã vững vàng";
    case "PRACTICING":
      return "Đang luyện tập";
    case "LEARNING":
      return "Đang học";
    case "WEAK":
      return "Cần cải thiện";
    case "REVIEW_DUE":
      return "Đến hạn ôn tập";
    case "NOT_STARTED":
      return "Chưa bắt đầu";
    default:
      return "Chưa đo lường";
  }
}

export function getMasteryStateDescription(state: DerivedMasteryState): string {
  switch (state) {
    case "MASTERED":
      return "Đã đạt độ vững cao (≥ 80%) và độ tin cậy ổn định. Kiến thức đã được củng cố chắc chắn.";
    case "PRACTICING":
      return "Đang trong tiến trình rèn luyện tích cực với độ thành thạo trên mức cơ bản.";
    case "LEARNING":
      return "Đang tiếp thu kiến thức mới, cần làm thêm bài tập để đánh giá chuẩn xác.";
    case "WEAK":
      return "Phát hiện lỗ hổng kiến thức hoặc tỷ lệ làm đúng chưa đạt yêu cầu. Cần ưu tiên bù đắp.";
    case "REVIEW_DUE":
      return "Đã đến chu kỳ ôn tập giãn cách để duy trì trí nhớ dài hạn và chống quên lãng.";
    case "NOT_STARTED":
      return "Chưa có lượt làm bài nào được ghi nhận cho nội dung này.";
    default:
      return "Chưa có đủ dữ liệu thực nghiệm để đo lường năng lực.";
  }
}

export function getMasteryStateAccent(
  state: DerivedMasteryState
): "mint" | "aqua" | "amber" | "coral" | "sky" | "violet" {
  switch (state) {
    case "MASTERED":
      return "mint";
    case "PRACTICING":
      return "sky";
    case "LEARNING":
      return "aqua";
    case "WEAK":
      return "coral";
    case "REVIEW_DUE":
      return "amber";
    case "NOT_STARTED":
    default:
      return "violet";
  }
}

export function getBiomeLabel(biome: KnowledgeBiome): string {
  switch (biome) {
    case "meadow":
      return "Đồng cỏ Khởi nguyên";
    case "river":
      return "Dòng chảy Chuyên đề";
    case "mountain":
      return "Đỉnh cao Năng lực";
    case "forest":
      return "Rừng già Đại thụ";
    case "sky":
      return "Chân trời Mở rộng";
    default:
      return "Vùng cảnh quan";
  }
}

export const STATUS_FILTERS: Array<{ id: KnowledgeStatusFilter; label: string }> = [
  { id: "ALL", label: "Tất cả" },
  { id: "MASTERED", label: "Đã vững" },
  { id: "PRACTICING", label: "Đang luyện" },
  { id: "LEARNING", label: "Đang học" },
  { id: "WEAK", label: "Cần cải thiện" },
  { id: "REVIEW_DUE", label: "Đến hạn ôn" },
  { id: "NOT_STARTED", label: "Chưa học" },
];
