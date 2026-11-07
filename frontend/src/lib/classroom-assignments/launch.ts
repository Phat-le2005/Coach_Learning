import { getBackendBaseUrl } from "@/lib/api/client";

export interface ClassroomNavQuestion {
  index: number;
  label: string;
  problemId: string;
  attemptId: string | null;
  isCurrent: boolean;
  status: string;
  score?: number | null;
}

export interface ClassroomNavData {
  studentAssignmentId: string;
  assignmentId: string;
  title: string;
  deliveryMode: "PRACTICE" | "EXAM";
  assignmentStatus: string;
  currentIndex: number;
  totalQuestions: number;
  questions: ClassroomNavQuestion[];
}

export interface LaunchClassroomCanvasResult {
  attemptId: string;
  nav: ClassroomNavData;
}

/**
 * Prepares the classroom assignment and ensures an attempt exists on the Canvas
 * for the requested (or next available) question.
 */
export async function launchClassroomCanvasAttempt(
  accessToken: string,
  assignmentIdOrStudentAssignmentId: string,
  requestedIndex?: number
): Promise<LaunchClassroomCanvasResult | null> {
  const backendUrl = getBackendBaseUrl();
  const headers = {
    Authorization: `Bearer ${accessToken}`,
    Accept: "application/json",
    "Content-Type": "application/json",
  };

  try {
    // 1. Get student assignment detail
    const asgRes = await fetch(
      `${backendUrl}/students/me/assignments/${encodeURIComponent(assignmentIdOrStudentAssignmentId)}`,
      { headers, cache: "no-store" }
    );
    if (!asgRes.ok) return null;
    const assignment = await asgRes.json();
    const saId = assignment.id; // student_assignment_id

    // 2. Prepare assignment (creates StudentAssignmentMaterialItems / AssignmentStudentQuestions)
    try {
      await fetch(
        `${backendUrl}/api/v2/math-solutions/student-assignments/${encodeURIComponent(saId)}/prepare`,
        { method: "POST", headers, cache: "no-store" }
      );
    } catch {
      // Ignore if already prepared
    }

    // 3. Get problems list
    const problemsRes = await fetch(
      `${backendUrl}/api/v2/math-solutions/student-assignments/${encodeURIComponent(saId)}/problems`,
      { headers, cache: "no-store" }
    );
    let problems: any[] = [];
    if (problemsRes.ok) {
      problems = await problemsRes.json();
    }
    if (problems.length === 0 && assignment.questions && assignment.questions.length > 0) {
      problems = assignment.questions;
    }
    if (problems.length === 0) return null;

    // 4. Get existing attempts for this student assignment
    const attemptsRes = await fetch(
      `${backendUrl}/api/v2/math-solutions/attempts?student_assignment_id=${encodeURIComponent(saId)}&size=100`,
      { headers, cache: "no-store" }
    );
    let existingAttempts: any[] = [];
    if (attemptsRes.ok) {
      const attemptsData = await attemptsRes.json();
      existingAttempts = attemptsData.items || [];
    }

    // 5. Determine target index
    let targetIndex = 0;
    if (
      requestedIndex !== undefined &&
      requestedIndex >= 0 &&
      requestedIndex < problems.length
    ) {
      targetIndex = requestedIndex;
    } else {
      // Find first question not yet finished
      for (let i = 0; i < problems.length; i++) {
        const p = problems[i];
        const match = existingAttempts.find((a: any) =>
          p.student_assignment_material_item_id
            ? a.student_assignment_material_item_id === p.student_assignment_material_item_id
            : a.assignment_student_question_id === p.assignment_student_question_id
        );
        if (!match || (match.status !== "SUBMITTED" && match.status !== "EVALUATED")) {
          targetIndex = i;
          break;
        }
      }
    }

    const targetProblem = problems[targetIndex];

    // 6. Find or create attempt for target problem
    let targetAttempt = existingAttempts.find((a: any) =>
      targetProblem.student_assignment_material_item_id
        ? a.student_assignment_material_item_id === targetProblem.student_assignment_material_item_id
        : a.assignment_student_question_id === targetProblem.assignment_student_question_id
    );

    if (!targetAttempt) {
      const isExam = assignment.delivery_mode === "EXAM";
      const payload = {
        source_kind: targetProblem.source_kind || "TEACHER_MATERIAL",
        context_type: "CLASSROOM_ASSIGNMENT",
        mode: isExam ? "INDEPENDENT_SOLUTION" : "GUIDED_LEARNING",
        create_idempotency_key: crypto.randomUUID(),
        student_assignment_id: saId,
        student_assignment_material_item_id:
          targetProblem.student_assignment_material_item_id ||
          (targetProblem.source_kind === "TEACHER_MATERIAL" ? targetProblem.id : null),
        assignment_student_question_id:
          targetProblem.assignment_student_question_id || null,
        question_id: targetProblem.question_id || null,
      };

      const createRes = await fetch(`${backendUrl}/api/v2/math-solutions/attempts`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        cache: "no-store",
      });

      if (createRes.ok) {
        targetAttempt = await createRes.json();
        existingAttempts.push(targetAttempt);
      } else {
        // If 409 conflict, try refetching attempt list
        const retryRes = await fetch(
          `${backendUrl}/api/v2/math-solutions/attempts?student_assignment_id=${encodeURIComponent(saId)}&size=100`,
          { headers, cache: "no-store" }
        );
        if (retryRes.ok) {
          const retryData = await retryRes.json();
          existingAttempts = retryData.items || [];
          targetAttempt = existingAttempts.find((a: any) =>
            targetProblem.student_assignment_material_item_id
              ? a.student_assignment_material_item_id === targetProblem.student_assignment_material_item_id
              : a.assignment_student_question_id === targetProblem.assignment_student_question_id
          );
        }
      }
    }

    if (!targetAttempt || !targetAttempt.id) {
      return null;
    }

    // 7. Construct navigation data
    const questionsNav: ClassroomNavQuestion[] = problems.map((p, idx) => {
      const match = existingAttempts.find((a: any) =>
        p.student_assignment_material_item_id
          ? a.student_assignment_material_item_id === p.student_assignment_material_item_id
          : a.assignment_student_question_id === p.assignment_student_question_id
      );
      return {
        index: idx,
        label: `Câu ${idx + 1}`,
        problemId: p.id,
        attemptId: match?.id ?? null,
        isCurrent: idx === targetIndex,
        status: match?.status ?? "NOT_STARTED",
        score: match?.final_score ?? null,
      };
    });

    const navData: ClassroomNavData = {
      studentAssignmentId: saId,
      assignmentId: assignment.assignment_id || assignment.id,
      title: assignment.title,
      deliveryMode: assignment.delivery_mode,
      assignmentStatus: assignment.status,
      currentIndex: targetIndex,
      totalQuestions: problems.length,
      questions: questionsNav,
    };

    return {
      attemptId: targetAttempt.id,
      nav: navData,
    };
  } catch {
    return null;
  }
}

/**
 * Loads the classroom assignment navigation details without mutating attempt state.
 */
export async function getClassroomAssignmentNav(
  accessToken: string,
  studentAssignmentId: string,
  currentAttemptId: string
): Promise<ClassroomNavData | null> {
  const backendUrl = getBackendBaseUrl();
  const headers = {
    Authorization: `Bearer ${accessToken}`,
    Accept: "application/json",
  };

  try {
    const asgRes = await fetch(
      `${backendUrl}/students/me/assignments/${encodeURIComponent(studentAssignmentId)}`,
      { headers, cache: "no-store" }
    );
    if (!asgRes.ok) return null;
    const assignment = await asgRes.json();

    const problemsRes = await fetch(
      `${backendUrl}/api/v2/math-solutions/student-assignments/${encodeURIComponent(studentAssignmentId)}/problems`,
      { headers, cache: "no-store" }
    );
    let problems: any[] = [];
    if (problemsRes.ok) {
      problems = await problemsRes.json();
    }
    if (problems.length === 0 && assignment.questions) {
      problems = assignment.questions;
    }
    if (problems.length === 0) return null;

    const attemptsRes = await fetch(
      `${backendUrl}/api/v2/math-solutions/attempts?student_assignment_id=${encodeURIComponent(studentAssignmentId)}&size=100`,
      { headers, cache: "no-store" }
    );
    let existingAttempts: any[] = [];
    if (attemptsRes.ok) {
      const data = await attemptsRes.json();
      existingAttempts = data.items || [];
    }

    let currentIndex = 0;
    const questionsNav: ClassroomNavQuestion[] = problems.map((p, idx) => {
      const match = existingAttempts.find((a: any) =>
        p.student_assignment_material_item_id
          ? a.student_assignment_material_item_id === p.student_assignment_material_item_id
          : a.assignment_student_question_id === p.assignment_student_question_id
      );
      const isCurrent = match?.id === currentAttemptId;
      if (isCurrent) currentIndex = idx;
      return {
        index: idx,
        label: `Câu ${idx + 1}`,
        problemId: p.id,
        attemptId: match?.id ?? null,
        isCurrent,
        status: match?.status ?? "NOT_STARTED",
        score: match?.final_score ?? null,
      };
    });

    return {
      studentAssignmentId,
      assignmentId: assignment.assignment_id || assignment.id,
      title: assignment.title,
      deliveryMode: assignment.delivery_mode,
      assignmentStatus: assignment.status,
      currentIndex,
      totalQuestions: problems.length,
      questions: questionsNav,
    };
  } catch {
    return null;
  }
}

