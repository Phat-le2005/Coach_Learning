/** Backend requires an explicit goal date. Never invent an exam or its date. */
export function studyGoalPayload(body: Record<string, unknown>) {
  const date = typeof body.exam_date === "string" ? body.exam_date : "";
  const parsed = new Date(`${date}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) {
    throw new Error("Chọn mốc hoàn thành hợp lệ để tạo kế hoạch học.");
  }
  return {
    target_exam: typeof body.target_exam === "string" && body.target_exam.trim() ? body.target_exam.trim() : "Mục tiêu học tập cá nhân",
    exam_date: date,
    available_daily_minutes: body.available_daily_minutes ?? 30,
    status: "ACTIVE",
    target_university: body.target_university ?? null,
    target_major: body.target_major ?? null,
    subject_goals: body.subject_id ? [{ subject_id: body.subject_id, target_score: body.target_score ?? 8, current_score: body.current_score ?? null, priority: 1 }] : [],
  };
}
