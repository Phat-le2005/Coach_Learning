import { notFound, redirect } from "next/navigation";
import { readSession } from "@/lib/auth/server";
import { OcrEvaluationWorkbench } from "@/features/math-workspace/components/OcrEvaluationWorkbench";
export default async function OcrEvaluationPage() {
  if (process.env.NODE_ENV === "production" || process.env.OCR_V2_EXPERIMENTAL !== "1") notFound();
  if (!await readSession()) redirect("/login?returnTo=/ocr-v2-lab/evaluation");
  return <OcrEvaluationWorkbench />;
}
