/** Local development shortcuts only. All problem content comes from the backend. */
export const DERIVATIVE_TEST_EXAMPLES = [
  { id: "c0000000-0000-0000-0000-000000000101", label: "Đạo hàm 01 · Khoảng đơn điệu của hàm bậc ba" },
  { id: "c0000000-0000-0000-0000-000000000102", label: "Đạo hàm 02 · Tiệm cận ngang của hàm phân thức" },
  { id: "c0000000-0000-0000-0000-000000000103", label: "Đạo hàm 03 · Số lượng vi khuẩn lớn nhất" },
  { id: "c0000000-0000-0000-0000-000000000104", label: "Đạo hàm 04 · Hộp không nắp có thể tích lớn nhất" },
  { id: "c0000000-0000-0000-0000-000000000105", label: "Đạo hàm 05 · Tối ưu hàng rào khu đất" },
  { id: "c0000000-0000-0000-0000-000000000106", label: "Đạo hàm 06 · Chi phí xuất bản trung bình nhỏ nhất" },
  { id: "c0000000-0000-0000-0000-000000000107", label: "Đạo hàm 07 · Nồng độ muối và tiệm cận ngang" },
  { id: "c0000000-0000-0000-0000-000000000108", label: "Đạo hàm 08 · Khảo sát lợi nhuận nghề dệt" },
  { id: "c0000000-0000-0000-0000-000000000109", label: "Đạo hàm 09 · Mô hình tăng trưởng nấm men" },
  { id: "c0000000-0000-0000-0000-000000000110", label: "Đạo hàm 10 · Vận tốc và độ cao của vật" },
] as const;

export const LEGACY_STEP_REVIEW_EXAMPLES = [
  { id: "c0000000-0000-0000-0000-000000000001", label: "Bài 1 · Khảo sát hàm bậc ba (bài cũ)" },
  { id: "c0000000-0000-0000-0000-000000000002", label: "Ví dụ 7 · Chứng minh g(x)=x/(x−1) nghịch biến" },
] as const;
export const STEP_REVIEW_EXAMPLES = [...LEGACY_STEP_REVIEW_EXAMPLES, ...DERIVATIVE_TEST_EXAMPLES] as const;

export function stepReviewSeedCommand(id: string): string {
  if (DERIVATIVE_TEST_EXAMPLES.some((example) => example.id === id)) return "python -m app.seed_derivative_test_pack --apply";
  return id === LEGACY_STEP_REVIEW_EXAMPLES[1].id
    ? "python -m app.seed_dataset_step_review_demo"
    : "python -m app.seed_step_review_demo";
}

export function resolveStepReviewExample(value: unknown) {
  if (value === null) return STEP_REVIEW_EXAMPLES[0];
  return typeof value === "string" ? STEP_REVIEW_EXAMPLES.find((example) => example.id === value) ?? null : null;
}
