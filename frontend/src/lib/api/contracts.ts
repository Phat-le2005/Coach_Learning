import { ApiContractError, array, boolean, integer, nonEmptyString, nullable, number, oneOf, optional, record, string } from "./validation";

export const ROLES = ["STUDENT", "TEACHER", "PARENT", "ADMIN"] as const;
export type Role = (typeof ROLES)[number];

export interface LoginRequest { email: string; password: string }
export interface RefreshRequest { refresh_token: string }
export interface TokenPair { access_token: string; refresh_token: string; token_type: "bearer"; expires_in: number }
export interface UserRead { id: string; email: string; full_name: string; role: Role; is_active: boolean; created_at: string; updated_at: string }
export interface StudentLearningSubjectRead { id: string; code: string; name: string }
export interface StudentCurrentActionRead {
  action_type: string; subject_id: string | null; resource_id: string | null; practice_session_id: string | null;
  assignment_id: string | null; verification_id: string | null; adaptive_repair_session_id: string | null;
  study_task_id: string | null; target_type: string | null; problem_type_id: string | null; concept_id: string | null;
  target_name: string | null; target_code: string | null; reason_code: string | null; repair_cycle_index: number | null; phase: string | null;
}
export interface StudentWeakTargetRead {
  problem_type_id: string | null; concept_id: string | null; target_name: string; target_code: string; code: string | null;
  name: string | null; mastery_score: number; confidence: number; last_practiced_at: string | null;
}
export interface StudentMasterySummaryRead {
  problem_type_started_count: number; concept_started_count: number; mastered_problem_type_count: number;
  weak_problem_type_count: number; mastered_concept_count: number; weak_concept_count: number;
  average_problem_type_mastery: number | null; average_concept_mastery: number | null;
  weak_problem_types: StudentWeakTargetRead[]; weak_concepts: StudentWeakTargetRead[];
}
export interface StudentPriorityTargetRead {
  target_type: string; problem_type_id: string | null; concept_id: string | null; target_name: string; target_code: string;
  reason_code: string; priority_score: number; mastery_score: number; confidence: number; desired_difficulty: number;
}
export interface StudentActiveLearningRead {
  practice_session_id: string | null; practice_session_type: string | null; verification_id: string | null;
  adaptive_repair_session_id: string | null; assignment_id: string | null;
}
export interface StudentReviewTargetRead {
  schedule_id: string; target_type: string; problem_type_id: string | null; concept_id: string | null;
  target_name: string; target_code: string; next_review_at: string; review_interval_days: number;
  review_count: number; last_review_result: string | null;
}
export interface StudentReviewStateRead {
  due_now_count: number; upcoming_count: number; due_targets: StudentReviewTargetRead[];
}
export interface StudentAssignmentStateItemRead {
  assignment_id: string; student_assignment_id: string; classroom_id: string; subject_id: string;
  title: string; status: string; start_at: string; due_at: string | null; score: number | null; is_overdue: boolean;
}
export interface StudentAssignmentStateRead {
  overdue_count: number; in_progress_count: number; pending_count: number; upcoming: StudentAssignmentStateItemRead[];
}
export interface StudyTaskRead {
  id: string; study_plan_id: string; task_type: string; status: string; planned_date: string;
  problem_type_id: string | null; problem_type_name: string | null; concept_id: string | null; concept_name: string | null;
  topic_id: string | null; topic_name: string | null; chapter_id: string | null; chapter_name: string | null;
  subject_id: string | null; subject_name: string | null; estimated_duration_minutes: number;
  priority: number; order_index: number; reason_code: string; completed_at: string | null;
  created_at: string; updated_at: string;
}
export interface StudyDayRead {
  date: string; available_daily_minutes: number; total_estimated_minutes: number;
  tasks: StudyTaskRead[]; completed_count: number; total_count: number;
  days_to_exam: number | null; notice: string | null;
}
export type StudentTodayPlanSnapshotRead = StudyDayRead;
export interface StudentLearningStateRead {
  student_id: string; as_of: string; available_subjects: StudentLearningSubjectRead[]; focus_subject_id: string | null;
  current_action: StudentCurrentActionRead; mastery_summary: StudentMasterySummaryRead;
  priority_targets: StudentPriorityTargetRead[]; active_learning: StudentActiveLearningRead;
  verified_root_causes: Record<string, unknown>[]; repair: Record<string, unknown> | null;
  review: StudentReviewStateRead; assignments: StudentAssignmentStateRead;
  today_plan?: StudyDayRead | null; latest_feedback?: Record<string, unknown> | null;
  class_contexts: Record<string, unknown>[];
}

export const DERIVED_MASTERY_STATES = [
  "NOT_STARTED",
  "LEARNING",
  "WEAK",
  "PRACTICING",
  "MASTERED",
  "REVIEW_DUE",
] as const;
export type DerivedMasteryState = (typeof DERIVED_MASTERY_STATES)[number];

export interface MasteryMetricRead {
  mastery_score: number;
  confidence: number;
  attempt_count: number;
  correct_count: number;
  last_practiced_at: string | null;
  last_updated_at: string | null;
  state: DerivedMasteryState;
}

export interface ProblemTypeMasteryRead extends MasteryMetricRead {
  problem_type_id: string;
  topic_id: string;
  code: string;
  name: string;
}

export interface ConceptMasteryRead extends MasteryMetricRead {
  concept_id: string;
  subject_id: string;
  code: string;
  name: string;
}

export interface AggregateMasteryRead extends MasteryMetricRead {
  problem_type_count: number;
  started_problem_type_count: number;
}

export interface TopicMasteryRead extends AggregateMasteryRead {
  topic_id: string;
  chapter_id: string;
  code: string;
  name: string;
  problem_types: ProblemTypeMasteryRead[];
}

export interface ChapterMasteryRead extends AggregateMasteryRead {
  chapter_id: string;
  subject_id: string;
  code: string;
  name: string;
  topics: TopicMasteryRead[];
}

export interface SubjectMasteryRead extends AggregateMasteryRead {
  subject_id: string;
  code: string;
  name: string;
  chapters: ChapterMasteryRead[];
  concepts: ConceptMasteryRead[];
}

export interface StudentMasteryRead {
  student_id: string;
  subjects: SubjectMasteryRead[];
}

const nullableString = (value: unknown, path: string) => nullable(value, path, string);
const optionalNullableRecord = (value: unknown, path: string) => optional(value, path, (item, itemPath) => nullable(item, itemPath, record));

export function validateLoginRequest(value: LoginRequest): LoginRequest {
  const email = value.email.trim().toLowerCase();
  if (!email || !email.includes("@") || email.length > 254) throw new Error("Email không hợp lệ.");
  if (!value.password || value.password.length > 128) throw new Error("Mật khẩu không hợp lệ.");
  return { email, password: value.password };
}

export function parseTokenPair(value: unknown, path = "response"): TokenPair {
  const source = record(value, path);
  const expiresIn = integer(source.expires_in, `${path}.expires_in`);
  if (expiresIn <= 0) throw new Error("Token expiry must be positive.");
  return {
    access_token: nonEmptyString(source.access_token, `${path}.access_token`),
    refresh_token: nonEmptyString(source.refresh_token, `${path}.refresh_token`),
    token_type: oneOf(source.token_type, `${path}.token_type`, ["bearer"] as const),
    expires_in: expiresIn,
  };
}

export function parseUserRead(value: unknown, path = "response"): UserRead {
  const source = record(value, path);
  return {
    id: nonEmptyString(source.id, `${path}.id`), email: nonEmptyString(source.email, `${path}.email`),
    full_name: nonEmptyString(source.full_name, `${path}.full_name`), role: oneOf(source.role, `${path}.role`, ROLES),
    is_active: boolean(source.is_active, `${path}.is_active`), created_at: nonEmptyString(source.created_at, `${path}.created_at`),
    updated_at: nonEmptyString(source.updated_at, `${path}.updated_at`),
  };
}

function parseSubject(value: unknown, path: string): StudentLearningSubjectRead {
  const source = record(value, path);
  return { id: nonEmptyString(source.id, `${path}.id`), code: nonEmptyString(source.code, `${path}.code`), name: nonEmptyString(source.name, `${path}.name`) };
}

function parseCurrentAction(value: unknown, path: string): StudentCurrentActionRead {
  const source = record(value, path);
  return {
    action_type: nonEmptyString(source.action_type, `${path}.action_type`), subject_id: nullableString(source.subject_id, `${path}.subject_id`),
    resource_id: nullableString(source.resource_id, `${path}.resource_id`), practice_session_id: nullableString(source.practice_session_id, `${path}.practice_session_id`),
    assignment_id: nullableString(source.assignment_id, `${path}.assignment_id`), verification_id: nullableString(source.verification_id, `${path}.verification_id`),
    adaptive_repair_session_id: nullableString(source.adaptive_repair_session_id, `${path}.adaptive_repair_session_id`),
    study_task_id: nullableString(source.study_task_id, `${path}.study_task_id`), target_type: nullableString(source.target_type, `${path}.target_type`),
    problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`), concept_id: nullableString(source.concept_id, `${path}.concept_id`),
    target_name: nullableString(source.target_name, `${path}.target_name`), target_code: nullableString(source.target_code, `${path}.target_code`),
    reason_code: nullableString(source.reason_code, `${path}.reason_code`),
    repair_cycle_index: nullable(source.repair_cycle_index, `${path}.repair_cycle_index`, integer), phase: nullableString(source.phase, `${path}.phase`),
  };
}

function parseWeakTarget(value: unknown, path: string): StudentWeakTargetRead {
  const source = record(value, path);
  return {
    problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`), concept_id: nullableString(source.concept_id, `${path}.concept_id`),
    target_name: nonEmptyString(source.target_name, `${path}.target_name`), target_code: nonEmptyString(source.target_code, `${path}.target_code`),
    code: nullableString(source.code, `${path}.code`), name: nullableString(source.name, `${path}.name`),
    mastery_score: number(source.mastery_score, `${path}.mastery_score`), confidence: number(source.confidence, `${path}.confidence`),
    last_practiced_at: nullableString(source.last_practiced_at, `${path}.last_practiced_at`),
  };
}

function parseMastery(value: unknown, path: string): StudentMasterySummaryRead {
  const source = record(value, path);
  return {
    problem_type_started_count: integer(source.problem_type_started_count, `${path}.problem_type_started_count`), concept_started_count: integer(source.concept_started_count, `${path}.concept_started_count`),
    mastered_problem_type_count: integer(source.mastered_problem_type_count, `${path}.mastered_problem_type_count`), weak_problem_type_count: integer(source.weak_problem_type_count, `${path}.weak_problem_type_count`),
    mastered_concept_count: integer(source.mastered_concept_count, `${path}.mastered_concept_count`), weak_concept_count: integer(source.weak_concept_count, `${path}.weak_concept_count`),
    average_problem_type_mastery: nullable(source.average_problem_type_mastery, `${path}.average_problem_type_mastery`, number),
    average_concept_mastery: nullable(source.average_concept_mastery, `${path}.average_concept_mastery`, number),
    weak_problem_types: array(source.weak_problem_types, `${path}.weak_problem_types`, parseWeakTarget),
    weak_concepts: array(source.weak_concepts, `${path}.weak_concepts`, parseWeakTarget),
  };
}

function parsePriority(value: unknown, path: string): StudentPriorityTargetRead {
  const source = record(value, path);
  return {
    target_type: nonEmptyString(source.target_type, `${path}.target_type`), problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`),
    concept_id: nullableString(source.concept_id, `${path}.concept_id`), target_name: nonEmptyString(source.target_name, `${path}.target_name`),
    target_code: nonEmptyString(source.target_code, `${path}.target_code`), reason_code: nonEmptyString(source.reason_code, `${path}.reason_code`),
    priority_score: number(source.priority_score, `${path}.priority_score`), mastery_score: number(source.mastery_score, `${path}.mastery_score`),
    confidence: number(source.confidence, `${path}.confidence`), desired_difficulty: number(source.desired_difficulty, `${path}.desired_difficulty`),
  };
}

function parseActiveLearning(value: unknown, path: string): StudentActiveLearningRead {
  const source = record(value, path);
  return {
    practice_session_id: nullableString(source.practice_session_id, `${path}.practice_session_id`), practice_session_type: nullableString(source.practice_session_type, `${path}.practice_session_type`),
    verification_id: nullableString(source.verification_id, `${path}.verification_id`), adaptive_repair_session_id: nullableString(source.adaptive_repair_session_id, `${path}.adaptive_repair_session_id`),
    assignment_id: nullableString(source.assignment_id, `${path}.assignment_id`),
  };
}

function parseReviewTarget(value: unknown, path: string): StudentReviewTargetRead {
  const source = record(value, path);
  return {
    schedule_id: nonEmptyString(source.schedule_id, `${path}.schedule_id`),
    target_type: nonEmptyString(source.target_type, `${path}.target_type`),
    problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`),
    concept_id: nullableString(source.concept_id, `${path}.concept_id`),
    target_name: nonEmptyString(source.target_name, `${path}.target_name`),
    target_code: nonEmptyString(source.target_code, `${path}.target_code`),
    next_review_at: nonEmptyString(source.next_review_at, `${path}.next_review_at`),
    review_interval_days: number(source.review_interval_days, `${path}.review_interval_days`),
    review_count: integer(source.review_count, `${path}.review_count`),
    last_review_result: nullableString(source.last_review_result, `${path}.last_review_result`),
  };
}

function parseReview(value: unknown, path: string): StudentReviewStateRead {
  const source = record(value, path);
  return {
    due_now_count: integer(source.due_now_count, `${path}.due_now_count`),
    upcoming_count: integer(source.upcoming_count, `${path}.upcoming_count`),
    due_targets: array(source.due_targets, `${path}.due_targets`, parseReviewTarget),
  };
}

function parseAssignmentItem(value: unknown, path: string): StudentAssignmentStateItemRead {
  const source = record(value, path);
  return {
    assignment_id: nonEmptyString(source.assignment_id, `${path}.assignment_id`),
    student_assignment_id: nonEmptyString(source.student_assignment_id, `${path}.student_assignment_id`),
    classroom_id: nonEmptyString(source.classroom_id, `${path}.classroom_id`),
    subject_id: nonEmptyString(source.subject_id, `${path}.subject_id`),
    title: nonEmptyString(source.title, `${path}.title`),
    status: nonEmptyString(source.status, `${path}.status`),
    start_at: nonEmptyString(source.start_at, `${path}.start_at`),
    due_at: nullableString(source.due_at, `${path}.due_at`),
    score: nullable(source.score, `${path}.score`, number),
    is_overdue: boolean(source.is_overdue, `${path}.is_overdue`),
  };
}

function parseAssignments(value: unknown, path: string): StudentAssignmentStateRead {
  const source = record(value, path);
  return {
    overdue_count: integer(source.overdue_count, `${path}.overdue_count`),
    in_progress_count: integer(source.in_progress_count, `${path}.in_progress_count`),
    pending_count: integer(source.pending_count, `${path}.pending_count`),
    upcoming: array(source.upcoming, `${path}.upcoming`, parseAssignmentItem),
  };
}

function parseStudyTask(value: unknown, path: string): StudyTaskRead {
  const source = record(value, path);
  return {
    id: nonEmptyString(source.id, `${path}.id`),
    study_plan_id: nonEmptyString(source.study_plan_id, `${path}.study_plan_id`),
    task_type: nonEmptyString(source.task_type, `${path}.task_type`),
    status: nonEmptyString(source.status, `${path}.status`),
    planned_date: nonEmptyString(source.planned_date, `${path}.planned_date`),
    problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`),
    problem_type_name: nullableString(source.problem_type_name, `${path}.problem_type_name`),
    concept_id: nullableString(source.concept_id, `${path}.concept_id`),
    concept_name: nullableString(source.concept_name, `${path}.concept_name`),
    topic_id: nullableString(source.topic_id, `${path}.topic_id`),
    topic_name: nullableString(source.topic_name, `${path}.topic_name`),
    chapter_id: nullableString(source.chapter_id, `${path}.chapter_id`),
    chapter_name: nullableString(source.chapter_name, `${path}.chapter_name`),
    subject_id: nullableString(source.subject_id, `${path}.subject_id`),
    subject_name: nullableString(source.subject_name, `${path}.subject_name`),
    estimated_duration_minutes: integer(source.estimated_duration_minutes, `${path}.estimated_duration_minutes`),
    priority: integer(source.priority, `${path}.priority`),
    order_index: integer(source.order_index, `${path}.order_index`),
    reason_code: nonEmptyString(source.reason_code, `${path}.reason_code`),
    completed_at: nullableString(source.completed_at, `${path}.completed_at`),
    created_at: nonEmptyString(source.created_at, `${path}.created_at`),
    updated_at: nonEmptyString(source.updated_at, `${path}.updated_at`),
  };
}

function parseTodayPlan(value: unknown, path: string): StudyDayRead | null {
  if (value === null || value === undefined) return null;
  const source = record(value, path);
  return {
    date: nonEmptyString(source.date, `${path}.date`),
    available_daily_minutes: integer(source.available_daily_minutes, `${path}.available_daily_minutes`),
    total_estimated_minutes: integer(source.total_estimated_minutes, `${path}.total_estimated_minutes`),
    tasks: array(source.tasks, `${path}.tasks`, parseStudyTask),
    completed_count: integer(source.completed_count, `${path}.completed_count`),
    total_count: integer(source.total_count, `${path}.total_count`),
    days_to_exam: nullable(source.days_to_exam, `${path}.days_to_exam`, integer),
    notice: nullableString(source.notice, `${path}.notice`),
  };
}

export function parseStudentLearningState(value: unknown, path = "response"): StudentLearningStateRead {
  const source = record(value, path);
  return {
    student_id: nonEmptyString(source.student_id, `${path}.student_id`), as_of: nonEmptyString(source.as_of, `${path}.as_of`),
    available_subjects: array(source.available_subjects, `${path}.available_subjects`, parseSubject), focus_subject_id: nullableString(source.focus_subject_id, `${path}.focus_subject_id`),
    current_action: parseCurrentAction(source.current_action, `${path}.current_action`), mastery_summary: parseMastery(source.mastery_summary, `${path}.mastery_summary`),
    priority_targets: array(source.priority_targets, `${path}.priority_targets`, parsePriority), active_learning: parseActiveLearning(source.active_learning, `${path}.active_learning`),
    verified_root_causes: array(source.verified_root_causes, `${path}.verified_root_causes`, record), repair: nullable(source.repair, `${path}.repair`, record),
    review: parseReview(source.review, `${path}.review`), assignments: parseAssignments(source.assignments, `${path}.assignments`),
    today_plan: parseTodayPlan(source.today_plan, `${path}.today_plan`), latest_feedback: optionalNullableRecord(source.latest_feedback, `${path}.latest_feedback`),
    class_contexts: array(source.class_contexts ?? [], `${path}.class_contexts`, record),
  };
}

export function parseDerivedMasteryState(value: unknown, path = "state"): DerivedMasteryState {
  return oneOf(value, path, DERIVED_MASTERY_STATES);
}

function parseMetricFields(source: Record<string, unknown>, path: string): MasteryMetricRead {
  return {
    mastery_score: number(source.mastery_score, `${path}.mastery_score`),
    confidence: number(source.confidence, `${path}.confidence`),
    attempt_count: integer(source.attempt_count, `${path}.attempt_count`),
    correct_count: integer(source.correct_count, `${path}.correct_count`),
    last_practiced_at: nullableString(source.last_practiced_at, `${path}.last_practiced_at`),
    last_updated_at: nullableString(source.last_updated_at, `${path}.last_updated_at`),
    state: parseDerivedMasteryState(source.state, `${path}.state`),
  };
}

export function parseProblemTypeMastery(value: unknown, path = "problem_type"): ProblemTypeMasteryRead {
  const source = record(value, path);
  return {
    ...parseMetricFields(source, path),
    problem_type_id: nonEmptyString(source.problem_type_id, `${path}.problem_type_id`),
    topic_id: nonEmptyString(source.topic_id, `${path}.topic_id`),
    code: nonEmptyString(source.code, `${path}.code`),
    name: nonEmptyString(source.name, `${path}.name`),
  };
}

export function parseConceptMastery(value: unknown, path = "concept"): ConceptMasteryRead {
  const source = record(value, path);
  return {
    ...parseMetricFields(source, path),
    concept_id: nonEmptyString(source.concept_id, `${path}.concept_id`),
    subject_id: nonEmptyString(source.subject_id, `${path}.subject_id`),
    code: nonEmptyString(source.code, `${path}.code`),
    name: nonEmptyString(source.name, `${path}.name`),
  };
}

export function parseTopicMastery(value: unknown, path = "topic"): TopicMasteryRead {
  const source = record(value, path);
  return {
    ...parseMetricFields(source, path),
    topic_id: nonEmptyString(source.topic_id, `${path}.topic_id`),
    chapter_id: nonEmptyString(source.chapter_id, `${path}.chapter_id`),
    code: nonEmptyString(source.code, `${path}.code`),
    name: nonEmptyString(source.name, `${path}.name`),
    problem_type_count: integer(source.problem_type_count, `${path}.problem_type_count`),
    started_problem_type_count: integer(source.started_problem_type_count, `${path}.started_problem_type_count`),
    problem_types: array(source.problem_types, `${path}.problem_types`, parseProblemTypeMastery),
  };
}

export function parseChapterMastery(value: unknown, path = "chapter"): ChapterMasteryRead {
  const source = record(value, path);
  return {
    ...parseMetricFields(source, path),
    chapter_id: nonEmptyString(source.chapter_id, `${path}.chapter_id`),
    subject_id: nonEmptyString(source.subject_id, `${path}.subject_id`),
    code: nonEmptyString(source.code, `${path}.code`),
    name: nonEmptyString(source.name, `${path}.name`),
    problem_type_count: integer(source.problem_type_count, `${path}.problem_type_count`),
    started_problem_type_count: integer(source.started_problem_type_count, `${path}.started_problem_type_count`),
    topics: array(source.topics, `${path}.topics`, parseTopicMastery),
  };
}

export function parseSubjectMastery(value: unknown, path = "subject"): SubjectMasteryRead {
  const source = record(value, path);
  return {
    ...parseMetricFields(source, path),
    subject_id: nonEmptyString(source.subject_id, `${path}.subject_id`),
    code: nonEmptyString(source.code, `${path}.code`),
    name: nonEmptyString(source.name, `${path}.name`),
    problem_type_count: integer(source.problem_type_count, `${path}.problem_type_count`),
    started_problem_type_count: integer(source.started_problem_type_count, `${path}.started_problem_type_count`),
    chapters: array(source.chapters, `${path}.chapters`, parseChapterMastery),
    concepts: array(source.concepts, `${path}.concepts`, parseConceptMastery),
  };
}

export function parseStudentMastery(value: unknown, path = "response"): StudentMasteryRead {
  const source = record(value, path);
  return {
    student_id: nonEmptyString(source.student_id, `${path}.student_id`),
    subjects: array(source.subjects, `${path}.subjects`, parseSubjectMastery),
  };
}

// -----------------------------------------------------------------------------
// Math Ink & Math Solutions V2 Contracts
// -----------------------------------------------------------------------------

export interface InkPoint {
  x: number;
  y: number;
  pressure: number;
}

export interface InkStroke {
  id: string;
  tool: "PEN" | "HIGHLIGHTER";
  color: string;
  width: number;
  points: InkPoint[];
}

export interface InkPageWrite {
  expected_document_revision: number;
  client_action_id: string;
  strokes: InkStroke[];
}

export interface InkPageSummary {
  page_index: number;
  stroke_count: number;
  point_count: number;
  sha256: string;
}

export interface InkDocumentRead {
  document_revision: number;
  pages: InkPageSummary[];
}

export interface InkPageRead {
  document_revision: number;
  page_index: number;
  strokes: InkStroke[];
}

export interface InkSaveRead {
  document_revision: number;
  page_index: number;
  sha256: string;
}

export interface ProblemOptionRead {
  id: string;
  label: string;
  content: string;
  order_index: number;
}

export interface ProblemRead {
  id: string;
  content: string;
  question_type: string;
  options: ProblemOptionRead[];
  order_index?: number | null;
  is_read_only: boolean;
  source_kind?: string;
  context_type?: string;
}

export const STEP_KINDS = [
  "ASSUMPTION",
  "DERIVATIVE_CALCULATION",
  "ROOT_FINDING",
  "SIGN_TABLE",
  "VARIATION_TABLE",
  "CONCLUSION",
  "EXPLANATION",
  "CUSTOM",
] as const;

export type StepKind = (typeof STEP_KINDS)[number];

export interface OCRRecognizeRequest {
  page_index: number;
  stroke_ids?: string[] | null;
  hint_topic?: string | null;
  include_alternatives?: boolean;
}

export interface OCRRecognizeResponse {
  latex: string;
  confidence: number;
  suggested_step_type: StepKind;
  explanation_text: string | null;
  detected_symbols: string[];
  alternative_latex: string[];
}

export interface StepMutationRequest {
  expected_attempt_revision: number;
  client_action_id: string;
  step_type: StepKind;
  content_latex?: string | null;
  explanation_text?: string | null;
}

export interface SolutionAttemptRead {
  id: string;
  student_id?: string;
  question_id: string | null;
  status: string;
  current_revision: number;
  created_at: string;
  updated_at?: string;
}

export interface MathAttemptsPageRead {
  items: SolutionAttemptRead[];
  total: number;
  page: number;
  size: number;
  total_pages: number;
}

export interface PracticeSessionStartRead {
  id: string;
  subject_id: string;
}

export function parseInkPoint(value: unknown, path = "point"): InkPoint {
  const source = record(value, path);
  return {
    x: number(source.x, `${path}.x`),
    y: number(source.y, `${path}.y`),
    pressure: typeof source.pressure === "number" ? source.pressure : 0.5,
  };
}

export function parseInkStroke(value: unknown, path = "stroke"): InkStroke {
  const source = record(value, path);
  const toolVal = string(source.tool, `${path}.tool`);
  if (toolVal !== "PEN" && toolVal !== "HIGHLIGHTER") {
    throw new ApiContractError(`Invalid stroke tool: ${toolVal}`, `${path}.tool`);
  }
  return {
    id: nonEmptyString(source.id, `${path}.id`),
    tool: toolVal,
    color: string(source.color, `${path}.color`),
    width: number(source.width, `${path}.width`),
    points: array(source.points, `${path}.points`, parseInkPoint),
  };
}

export function parseInkPageSummary(value: unknown, path = "page_summary"): InkPageSummary {
  const source = record(value, path);
  return {
    page_index: integer(source.page_index, `${path}.page_index`),
    stroke_count: integer(source.stroke_count, `${path}.stroke_count`),
    point_count: integer(source.point_count, `${path}.point_count`),
    sha256: string(source.sha256, `${path}.sha256`),
  };
}

export function parseInkDocumentRead(value: unknown, path = "ink_document"): InkDocumentRead {
  const source = record(value, path);
  return {
    document_revision: integer(source.document_revision, `${path}.document_revision`),
    pages: array(source.pages, `${path}.pages`, parseInkPageSummary),
  };
}

export function parseInkPageRead(value: unknown, path = "ink_page"): InkPageRead {
  const source = record(value, path);
  return {
    document_revision: integer(source.document_revision, `${path}.document_revision`),
    page_index: integer(source.page_index, `${path}.page_index`),
    strokes: array(source.strokes, `${path}.strokes`, parseInkStroke),
  };
}

export function parseInkSaveRead(value: unknown, path = "ink_save"): InkSaveRead {
  const source = record(value, path);
  return {
    document_revision: integer(source.document_revision, `${path}.document_revision`),
    page_index: integer(source.page_index, `${path}.page_index`),
    sha256: string(source.sha256, `${path}.sha256`),
  };
}

export function parseProblemOptionRead(value: unknown, path = "option"): ProblemOptionRead {
  const source = record(value, path);
  return {
    id: nonEmptyString(source.id, `${path}.id`),
    label: string(source.label, `${path}.label`),
    content: string(source.content, `${path}.content`),
    order_index: integer(source.order_index, `${path}.order_index`),
  };
}

export function parseProblemRead(value: unknown, path = "problem"): ProblemRead {
  const source = record(value, path);
  return {
    id: nonEmptyString(source.id, `${path}.id`),
    content: string(source.content, `${path}.content`),
    question_type: string(source.question_type, `${path}.question_type`),
    options: array(source.options, `${path}.options`, parseProblemOptionRead),
    order_index: typeof source.order_index === "number" ? source.order_index : null,
    is_read_only: typeof source.is_read_only === "boolean" ? source.is_read_only : false,
    source_kind: typeof source.source_kind === "string" ? source.source_kind : undefined,
    context_type: typeof source.context_type === "string" ? source.context_type : undefined,
  };
}

export function parseSolutionAttemptRead(value: unknown, path = "attempt"): SolutionAttemptRead {
  const source = record(value, path);
  const rev = typeof source.attempt_revision_number === "number"
    ? source.attempt_revision_number
    : (typeof source.current_revision === "number" ? integer(source.current_revision, `${path}.current_revision`) : 1);
  return {
    id: nonEmptyString(source.id, `${path}.id`),
    student_id: typeof source.student_id === "string" ? source.student_id : undefined,
    question_id: typeof source.question_id === "string" ? source.question_id : null,
    status: string(source.status, `${path}.status`),
    current_revision: rev,
    created_at: typeof source.created_at === "string" ? source.created_at : (typeof source.started_at === "string" ? source.started_at : ""),
    updated_at: typeof source.updated_at === "string" ? source.updated_at : undefined,
  };
}

export function parseMathAttemptsPageRead(value: unknown, path = "attempts"): MathAttemptsPageRead {
  const source = record(value, path);
  return {
    items: array(source.items, `${path}.items`, parseSolutionAttemptRead),
    total: integer(source.total, `${path}.total`),
    page: integer(source.page, `${path}.page`),
    size: integer(source.size, `${path}.size`),
    total_pages: integer(source.total_pages, `${path}.total_pages`),
  };
}

export function parsePracticeSessionStartRead(value: unknown, path = "practice_session"): PracticeSessionStartRead {
  const source = record(value, path);
  return {
    id: nonEmptyString(source.id, `${path}.id`),
    subject_id: nonEmptyString(source.subject_id, `${path}.subject_id`),
  };
}

export function parseOCRRecognizeResponse(value: unknown, path = "ocr_recognize"): OCRRecognizeResponse {
  const source = record(value, path);
  const stepTypeVal = string(source.suggested_step_type, `${path}.suggested_step_type`) as StepKind;
  return {
    latex: string(source.latex, `${path}.latex`),
    confidence: number(source.confidence, `${path}.confidence`),
    suggested_step_type: stepTypeVal,
    explanation_text: typeof source.explanation_text === "string" ? source.explanation_text : null,
    detected_symbols: array(source.detected_symbols ?? [], `${path}.detected_symbols`, (v, p) => string(v, p)),
    alternative_latex: array(source.alternative_latex ?? [], `${path}.alternative_latex`, (v, p) => string(v, p)),
  };
}


