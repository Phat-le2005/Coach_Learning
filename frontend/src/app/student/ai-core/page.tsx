import type { Metadata } from "next";

import { PageState } from "@/components/app-shell/PageState";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { SessionRecovery } from "@/components/auth/SessionRecovery";
import { GradientButton } from "@/components/ui/GradientButton";
import { AICoreView } from "@/features/ai-core/AICoreView";
import { coreGraph, coreMasteryRows, type CoreGraph } from "@/features/ai-core/model";
import { ApiResponseError, createBackendApiClient, getBackendBaseUrl } from "@/lib/api/client";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

export const metadata: Metadata = { title: "AI Core", description: "Quan sát luồng bài làm, đồ thị kiến thức, mastery và đề xuất học tập." };

export default async function AICorePage() {
  const session = await requirePageRole("STUDENT", "/student/ai-core");
  const token = await readAccessToken();
  if (!token) return <SessionRecovery />;
  const client = createBackendApiClient();
  const [stateResult, masteryResult, attemptsResult, graphResult] = await Promise.allSettled([
    client.studentLearningState(token), client.studentMastery(token), client.listMathAttempts(token, { page: 1, size: 6 }),
    fetch(`${getBackendBaseUrl()}/students/me/digital-twin`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(15_000),
    }).then(async response => {
      if (!response.ok) throw new ApiResponseError("Không đọc được hồ sơ học tập.", response.status, "CORE_SNAPSHOT_UNAVAILABLE", response.status === 401 ? "unauthorized" : "unavailable");
      return response.json() as Promise<unknown>;
    }),
  ]);
  if ([stateResult, masteryResult, attemptsResult, graphResult].some(result => result.status === "rejected" && result.reason instanceof ApiResponseError && result.reason.status === 401)) return <SessionRecovery />;
  if (stateResult.status === "rejected") return <main style={{ maxWidth: 780, margin: "80px auto", padding: 20 }}><PageState kind="error" title="Chưa đọc được AI Core" description="Dữ liệu học tập hiện chưa sẵn sàng. Em hãy thử tải lại trang." action={<GradientButton href="/student/ai-core">Thử lại</GradientButton>} /></main>;

  const state = stateResult.value;
  const warnings: string[] = [];
  const masteryAvailable = masteryResult.status === "fulfilled" && masteryResult.value.student_id === state.student_id;
  const mastery = masteryAvailable && masteryResult.status === "fulfilled" ? coreMasteryRows(masteryResult.value) : [];
  if (!masteryAvailable) warnings.push("Chưa đọc được dữ liệu mastery phù hợp với học sinh hiện tại; các chỉ số được giữ trống.");
  const attemptsAvailable = attemptsResult.status === "fulfilled" && attemptsResult.value.items.every(attempt => !attempt.student_id || attempt.student_id === state.student_id);
  if (!attemptsAvailable) warnings.push("Chưa đọc được danh sách bài làm; không thay thế bằng dữ liệu mẫu.");
  let graph: CoreGraph | null = null;
  if (graphResult.status === "fulfilled") {
    try { graph = coreGraph(graphResult.value, state.student_id, mastery); } catch { /* Preserve the other modules when the graph contract or identity fails. */ }
  }
  if (!graph) warnings.push("Chưa đọc được đồ thị kiến thức phù hợp; các quan hệ được giữ trống.");
  return <><SessionHeartbeat /><AICoreView key={state.student_id} displayName={session.fullName} email={session.email} asOf={state.as_of}
    state={state} graph={graph} mastery={mastery} masteryAvailable={masteryAvailable} warnings={warnings}
    attemptTotal={attemptsAvailable && attemptsResult.status === "fulfilled" ? attemptsResult.value.total : null}
    attempts={attemptsAvailable && attemptsResult.status === "fulfilled" ? attemptsResult.value.items.map(attempt => ({
      id: attempt.id, status: attempt.status, createdAt: attempt.created_at, steps: attempt.steps?.length ?? null, revision: attempt.current_revision,
    })) : []} /></>;
}
