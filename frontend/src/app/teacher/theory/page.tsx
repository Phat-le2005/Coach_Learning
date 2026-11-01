import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { requirePageRole } from "@/lib/auth/page-session";

export const metadata: Metadata = { title: "Kho tri thức giáo viên · EduMS" };
export default async function TeacherTheoryPage() {
  await requirePageRole("TEACHER", "/teacher/theory");
  redirect("/teacher?tab=theory");
}
