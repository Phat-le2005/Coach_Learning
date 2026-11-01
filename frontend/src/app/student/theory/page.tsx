import type { Metadata } from "next";
import { requirePageRole } from "@/lib/auth/page-session";
import { StudentTheoryClient } from "@/features/theory-maps/StudentTheoryClient";

export const metadata: Metadata = { title: "Kho lý thuyết lớp học · EduMS" };
export default async function StudentTheoryPage() {
  await requirePageRole("STUDENT", "/student/theory");
  return <StudentTheoryClient />;
}
