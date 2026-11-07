import { notFound, redirect } from "next/navigation";
import { readSession } from "@/lib/auth/server";
import { OcrV2LocalCanvas } from "@/features/math-workspace/components/OcrV2LocalCanvas";
export default async function OcrV2LabPage() {
  if (process.env.NODE_ENV === "production" || process.env.OCR_V2_EXPERIMENTAL !== "1") notFound();
  if (!await readSession()) redirect("/login?returnTo=/ocr-v2-lab");
  return <OcrV2LocalCanvas />;
}
