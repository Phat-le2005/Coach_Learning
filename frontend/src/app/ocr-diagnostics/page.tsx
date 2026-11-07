import { notFound } from "next/navigation";
import { OcrDiagnosticsWorkbench } from "@/features/math-workspace/components/OcrDiagnosticsWorkbench";

export default function OcrDiagnosticsPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <OcrDiagnosticsWorkbench />;
}
