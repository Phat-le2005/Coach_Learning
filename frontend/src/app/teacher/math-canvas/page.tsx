import type { Metadata } from "next";
import { requirePageRole } from "@/lib/auth/page-session";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { TeacherCanvasReview } from "@/features/math-canvas/TeacherCanvasReview";

export const metadata: Metadata = { title: "Math Canvas · Xem lại bài học" };
export default async function TeacherMathCanvasPage() {
  await requirePageRole("TEACHER", "/teacher/math-canvas");
  return <><SessionHeartbeat /><TeacherCanvasReview /></>;
}
