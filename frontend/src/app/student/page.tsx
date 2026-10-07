import type { Metadata } from "next";

import { StudentHome, StudentHomeDisconnected } from "@/features/student-home/StudentHome";
import { studentHomePreviewData } from "@/features/student-home/preview-data";

export const metadata: Metadata = {
  title: "Không gian học tập",
  description: "Tổng quan học tập cá nhân hóa của học sinh EduMS.",
};

export default function StudentPage() {
  const previewMode = process.env.NEXT_PUBLIC_UI_PREVIEW_MODE === "true";

  if (!previewMode) {
    return <StudentHomeDisconnected />;
  }

  return (
    <StudentHome
      data={studentHomePreviewData}
      showPreviewBadge
    />
  );
}
