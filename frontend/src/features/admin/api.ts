import { getCsrfToken, refreshBrowserSession } from "../../lib/auth/browser";
import { ApiContractError, array, boolean, integer, number, record, string } from "../../lib/api/validation";

export interface AdminSubject {
  id: string;
  curriculum_version_id: string;
  code: string;
  name: string;
  grade_level: number | null;
  description: string | null;
  order_index: number | null;
}

export interface AdminCurriculum {
  id: string;
  code: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminCurriculumVersion {
  id: string;
  curriculum_id: string;
  code: string;
  version: string;
  is_active: boolean;
  effective_from: string | null;
  effective_to: string | null;
  source_reference: string | null;
  created_at: string;
}

export interface AdminProblemTypeTreeNode {
  id: string;
  code: string;
  name: string;
  order_index: number;
  is_active: boolean;
  concept_count: number;
  learning_outcome_count: number;
}

export interface AdminTopicTreeNode {
  id: string;
  code: string;
  name: string;
  order_index: number;
  problem_types: AdminProblemTypeTreeNode[];
}

export interface AdminChapterTreeNode {
  id: string;
  code: string;
  name: string;
  order_index: number;
  topics: AdminTopicTreeNode[];
}

export interface AdminSubjectTree {
  id: string;
  curriculum_version_id: string;
  code: string;
  name: string;
  grade_level: number | null;
  chapters: AdminChapterTreeNode[];
}

export interface AdminQuestionOption {
  id: string;
  label: string;
  content: string;
  order_index: number;
}

export interface AdminQuestion {
  id: string;
  subject_id: string;
  content: string;
  question_type: string;
  difficulty: number;
  correct_answer: string | null;
  explanation: string | null;
  source_type: string;
  source_reference: string | null;
  source_year: number | null;
  cognitive_level: string | null;
  exam_weight: number;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  options: AdminQuestionOption[];
}

export interface AdminSupplyGap {
  id: string;
  signature: string;
  subject_id: string;
  use_case: string;
  target_type: string;
  concept_id: string | null;
  problem_type_id: string | null;
  misconception_definition_id: string | null;
  desired_difficulty: number | null;
  difficulty_min: number;
  difficulty_max: number;
  minimum_required_count: number;
  preferred_count: number;
  approved_eligible_count: number;
  approved_in_band_count: number;
  pipeline_candidate_count: number;
  pipeline_runtime_eligible_count: number;
  severity: string;
  status: string;
  reason_code: string;
  demand_count: number;
  last_observed_at: string;
  last_assessed_at: string;
}

export interface AdminAcquisitionRequest {
  id: string;
  gap_id: string;
  attempt_index: number;
  strategy: string;
  status: string;
  subject_id: string;
  use_case: string;
  target_type: string;
  difficulty_min: number;
  difficulty_max: number;
  minimum_required_count: number;
  preferred_count: number;
  required_new_candidate_count: number;
  existing_candidate_count: number;
  external_candidate_target_count: number;
  created_at: string;
}

export interface AdminValidationBatch {
  id: string;
  acquisition_request_id: string;
  attempt_index: number;
  status: string;
  target_candidate_count_snapshot: number;
  created_at: string;
  updated_at: string;
}

export interface AdminAIRequestLog {
  id: string;
  user_id: string | null;
  task: string;
  provider: string;
  model: string;
  prompt_name: string;
  prompt_version: string;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  success: boolean;
  error_type: string | null;
  estimated_cost: number | null;
  created_at: string;
}

export interface AdminAIRequestLogPagination {
  items: AdminAIRequestLog[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AdminAITaskUsageMetric {
  task: string;
  requests: number;
  successful_requests: number;
  failed_requests: number;
  failure_rate: number;
  average_latency_ms: number;
  total_tokens: number;
  estimated_cost: number;
}

export interface AdminAIUsageSummary {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  failure_rate: number;
  average_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_estimated_cost: number;
  average_requests_per_student_per_day: number;
  requests_per_task: AdminAITaskUsageMetric[];
}

export interface AdminUniversity {
  id: string;
  code: string;
  name: string;
  short_name: string | null;
  description: string | null;
  website: string | null;
  region: string | null;
  is_active: boolean;
  majors_count: number;
  created_at: string;
}

export interface AdminMajor {
  id: string;
  university_id: string;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
}

export interface AdminAdmissionRule {
  id: string;
  university_id: string;
  university_name: string;
  major_id: string;
  major_name: string;
  year: number;
  method_id: string;
  method_code: string;
  method_name: string;
  subject_combination: string;
  quota: number | null;
  historical_score: number | null;
  source_reference: string | null;
  is_active: boolean;
}

export interface AdminAdmissionImportHistory {
  id: string;
  file_name: string;
  file_format: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  imported_rows: number;
  updated_rows: number;
  skipped_rows: number;
  error_rows: number;
  target_year: number | null;
  data_source_name: string | null;
  source_reference: string | null;
  created_at: string;
}

export class AdminApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string
  ) {
    super(message);
    this.name = "AdminApiError";
  }
}

export function parseAdminSubject(value: unknown, path = "subject"): AdminSubject {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    curriculum_version_id: string(row.curriculum_version_id, `${path}.curriculum_version_id`),
    code: string(row.code, `${path}.code`),
    name: string(row.name, `${path}.name`),
    grade_level: row.grade_level === null || row.grade_level === undefined ? null : integer(row.grade_level, `${path}.grade_level`),
    description: row.description === null || row.description === undefined ? null : string(row.description, `${path}.description`),
    order_index: row.order_index === null || row.order_index === undefined ? null : integer(row.order_index, `${path}.order_index`),
  };
}

export function parseAdminCurriculum(value: unknown, path = "curriculum"): AdminCurriculum {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    code: string(row.code, `${path}.code`),
    name: string(row.name, `${path}.name`),
    description: row.description === null || row.description === undefined ? null : string(row.description, `${path}.description`),
    created_at: string(row.created_at, `${path}.created_at`),
    updated_at: string(row.updated_at, `${path}.updated_at`),
  };
}

export function parseAdminCurriculumVersion(value: unknown, path = "curriculum_version"): AdminCurriculumVersion {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    curriculum_id: string(row.curriculum_id, `${path}.curriculum_id`),
    code: string(row.code, `${path}.code`),
    version: string(row.version, `${path}.version`),
    is_active: boolean(row.is_active, `${path}.is_active`),
    effective_from: row.effective_from === null || row.effective_from === undefined ? null : string(row.effective_from, `${path}.effective_from`),
    effective_to: row.effective_to === null || row.effective_to === undefined ? null : string(row.effective_to, `${path}.effective_to`),
    source_reference: row.source_reference === null || row.source_reference === undefined ? null : string(row.source_reference, `${path}.source_reference`),
    created_at: string(row.created_at, `${path}.created_at`),
  };
}

export function parseAdminSubjectTree(value: unknown, path = "subject_tree"): AdminSubjectTree {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    curriculum_version_id: string(row.curriculum_version_id, `${path}.curriculum_version_id`),
    code: string(row.code, `${path}.code`),
    name: string(row.name, `${path}.name`),
    grade_level: row.grade_level === null || row.grade_level === undefined ? null : integer(row.grade_level, `${path}.grade_level`),
    chapters: array(row.chapters ?? [], `${path}.chapters`, (chap, cPath) => {
      const c = record(chap, cPath);
      return {
        id: string(c.id, `${cPath}.id`),
        code: string(c.code, `${cPath}.code`),
        name: string(c.name, `${cPath}.name`),
        order_index: integer(c.order_index, `${cPath}.order_index`),
        topics: array(c.topics ?? [], `${cPath}.topics`, (top, tPath) => {
          const t = record(top, tPath);
          return {
            id: string(t.id, `${tPath}.id`),
            code: string(t.code, `${tPath}.code`),
            name: string(t.name, `${tPath}.name`),
            order_index: integer(t.order_index, `${tPath}.order_index`),
            problem_types: array(t.problem_types ?? [], `${tPath}.problem_types`, (pt, pPath) => {
              const p = record(pt, pPath);
              return {
                id: string(p.id, `${pPath}.id`),
                code: string(p.code, `${pPath}.code`),
                name: string(p.name, `${pPath}.name`),
                order_index: integer(p.order_index, `${pPath}.order_index`),
                is_active: boolean(p.is_active, `${pPath}.is_active`),
                concept_count: integer(p.concept_count, `${pPath}.concept_count`),
                learning_outcome_count: integer(p.learning_outcome_count, `${pPath}.learning_outcome_count`),
              };
            }),
          };
        }),
      };
    }),
  };
}

export function parseAdminQuestion(value: unknown, path = "question"): AdminQuestion {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    subject_id: string(row.subject_id, `${path}.subject_id`),
    content: string(row.content, `${path}.content`),
    question_type: string(row.question_type, `${path}.question_type`),
    difficulty: number(row.difficulty, `${path}.difficulty`),
    correct_answer: row.correct_answer === null || row.correct_answer === undefined ? null : string(row.correct_answer, `${path}.correct_answer`),
    explanation: row.explanation === null || row.explanation === undefined ? null : string(row.explanation, `${path}.explanation`),
    source_type: string(row.source_type, `${path}.source_type`),
    source_reference: row.source_reference === null || row.source_reference === undefined ? null : string(row.source_reference, `${path}.source_reference`),
    source_year: row.source_year === null || row.source_year === undefined ? null : integer(row.source_year, `${path}.source_year`),
    cognitive_level: row.cognitive_level === null || row.cognitive_level === undefined ? null : string(row.cognitive_level, `${path}.cognitive_level`),
    exam_weight: number(row.exam_weight, `${path}.exam_weight`),
    status: string(row.status, `${path}.status`),
    created_by: string(row.created_by, `${path}.created_by`),
    created_at: string(row.created_at, `${path}.created_at`),
    updated_at: string(row.updated_at, `${path}.updated_at`),
    options: array(row.options ?? [], `${path}.options`, (opt, oPath) => {
      const o = record(opt, oPath);
      return {
        id: string(o.id, `${oPath}.id`),
        label: string(o.label, `${oPath}.label`),
        content: string(o.content, `${oPath}.content`),
        order_index: integer(o.order_index, `${oPath}.order_index`),
      };
    }),
  };
}

export function parseAdminSupplyGap(value: unknown, path = "supply_gap"): AdminSupplyGap {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    signature: string(row.signature, `${path}.signature`),
    subject_id: string(row.subject_id, `${path}.subject_id`),
    use_case: string(row.use_case, `${path}.use_case`),
    target_type: string(row.target_type, `${path}.target_type`),
    concept_id: row.concept_id === null || row.concept_id === undefined ? null : string(row.concept_id, `${path}.concept_id`),
    problem_type_id: row.problem_type_id === null || row.problem_type_id === undefined ? null : string(row.problem_type_id, `${path}.problem_type_id`),
    misconception_definition_id: row.misconception_definition_id === null || row.misconception_definition_id === undefined ? null : string(row.misconception_definition_id, `${path}.misconception_definition_id`),
    desired_difficulty: row.desired_difficulty === null || row.desired_difficulty === undefined ? null : number(row.desired_difficulty, `${path}.desired_difficulty`),
    difficulty_min: number(row.difficulty_min, `${path}.difficulty_min`),
    difficulty_max: number(row.difficulty_max, `${path}.difficulty_max`),
    minimum_required_count: integer(row.minimum_required_count, `${path}.minimum_required_count`),
    preferred_count: integer(row.preferred_count, `${path}.preferred_count`),
    approved_eligible_count: integer(row.approved_eligible_count, `${path}.approved_eligible_count`),
    approved_in_band_count: integer(row.approved_in_band_count, `${path}.approved_in_band_count`),
    pipeline_candidate_count: integer(row.pipeline_candidate_count, `${path}.pipeline_candidate_count`),
    pipeline_runtime_eligible_count: integer(row.pipeline_runtime_eligible_count ?? 0, `${path}.pipeline_runtime_eligible_count`),
    severity: string(row.severity, `${path}.severity`),
    status: string(row.status, `${path}.status`),
    reason_code: string(row.reason_code, `${path}.reason_code`),
    demand_count: integer(row.demand_count, `${path}.demand_count`),
    last_observed_at: string(row.last_observed_at, `${path}.last_observed_at`),
    last_assessed_at: string(row.last_assessed_at, `${path}.last_assessed_at`),
  };
}

export function parseAdminAcquisitionRequest(value: unknown, path = "acquisition_request"): AdminAcquisitionRequest {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    gap_id: string(row.gap_id, `${path}.gap_id`),
    attempt_index: integer(row.attempt_index, `${path}.attempt_index`),
    strategy: string(row.strategy, `${path}.strategy`),
    status: string(row.status, `${path}.status`),
    subject_id: string(row.subject_id, `${path}.subject_id`),
    use_case: string(row.use_case, `${path}.use_case`),
    target_type: string(row.target_type, `${path}.target_type`),
    difficulty_min: number(row.difficulty_min, `${path}.difficulty_min`),
    difficulty_max: number(row.difficulty_max, `${path}.difficulty_max`),
    minimum_required_count: integer(row.minimum_required_count, `${path}.minimum_required_count`),
    preferred_count: integer(row.preferred_count, `${path}.preferred_count`),
    required_new_candidate_count: integer(row.required_new_candidate_count, `${path}.required_new_candidate_count`),
    existing_candidate_count: integer(row.existing_candidate_count, `${path}.existing_candidate_count`),
    external_candidate_target_count: integer(row.external_candidate_target_count, `${path}.external_candidate_target_count`),
    created_at: string(row.created_at, `${path}.created_at`),
  };
}

export function parseAdminValidationBatch(value: unknown, path = "validation_batch"): AdminValidationBatch {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    acquisition_request_id: string(row.acquisition_request_id, `${path}.acquisition_request_id`),
    attempt_index: integer(row.attempt_index, `${path}.attempt_index`),
    status: string(row.status, `${path}.status`),
    target_candidate_count_snapshot: integer(row.target_candidate_count_snapshot, `${path}.target_candidate_count_snapshot`),
    created_at: string(row.created_at, `${path}.created_at`),
    updated_at: string(row.updated_at, `${path}.updated_at`),
  };
}

export function parseAdminAIUsageSummary(value: unknown, path = "ai_usage_summary"): AdminAIUsageSummary {
  const row = record(value, path);
  return {
    total_requests: integer(row.total_requests, `${path}.total_requests`),
    successful_requests: integer(row.successful_requests, `${path}.successful_requests`),
    failed_requests: integer(row.failed_requests, `${path}.failed_requests`),
    failure_rate: number(row.failure_rate, `${path}.failure_rate`),
    average_latency_ms: number(row.average_latency_ms, `${path}.average_latency_ms`),
    total_input_tokens: integer(row.total_input_tokens, `${path}.total_input_tokens`),
    total_output_tokens: integer(row.total_output_tokens, `${path}.total_output_tokens`),
    total_tokens: integer(row.total_tokens, `${path}.total_tokens`),
    total_estimated_cost: number(row.total_estimated_cost, `${path}.total_estimated_cost`),
    average_requests_per_student_per_day: number(
      row.average_requests_per_student_per_day ?? 0,
      `${path}.average_requests_per_student_per_day`
    ),
    requests_per_task: array(row.requests_per_task ?? [], `${path}.requests_per_task`, (item, p) => {
      const t = record(item, p);
      return {
        task: string(t.task, `${p}.task`),
        requests: integer(t.requests, `${p}.requests`),
        successful_requests: integer(t.successful_requests, `${p}.successful_requests`),
        failed_requests: integer(t.failed_requests, `${p}.failed_requests`),
        failure_rate: number(t.failure_rate, `${p}.failure_rate`),
        average_latency_ms: number(t.average_latency_ms, `${p}.average_latency_ms`),
        total_tokens: integer(t.total_tokens, `${p}.total_tokens`),
        estimated_cost: number(t.estimated_cost, `${p}.estimated_cost`),
      };
    }),
  };
}

export function parseAdminAIRequestLogPagination(value: unknown, path = "ai_logs"): AdminAIRequestLogPagination {
  const row = record(value, path);
  return {
    items: array(row.items ?? [], `${path}.items`, (item, p) => {
      const l = record(item, p);
      return {
        id: string(l.id, `${p}.id`),
        user_id: l.user_id === null || l.user_id === undefined ? null : string(l.user_id, `${p}.user_id`),
        task: string(l.task, `${p}.task`),
        provider: string(l.provider, `${p}.provider`),
        model: string(l.model, `${p}.model`),
        prompt_name: string(l.prompt_name, `${p}.prompt_name`),
        prompt_version: string(l.prompt_version, `${p}.prompt_version`),
        latency_ms: number(l.latency_ms, `${p}.latency_ms`),
        input_tokens: l.input_tokens === null || l.input_tokens === undefined ? null : integer(l.input_tokens, `${p}.input_tokens`),
        output_tokens: l.output_tokens === null || l.output_tokens === undefined ? null : integer(l.output_tokens, `${p}.output_tokens`),
        success: boolean(l.success, `${p}.success`),
        error_type: l.error_type === null || l.error_type === undefined ? null : string(l.error_type, `${p}.error_type`),
        estimated_cost: l.estimated_cost === null || l.estimated_cost === undefined ? null : number(l.estimated_cost, `${p}.estimated_cost`),
        created_at: string(l.created_at, `${p}.created_at`),
      };
    }),
    total: integer(row.total, `${path}.total`),
    page: integer(row.page, `${path}.page`),
    page_size: integer(row.page_size, `${path}.page_size`),
    total_pages: integer(row.total_pages, `${path}.total_pages`),
  };
}

export function parseAdminUniversity(value: unknown, path = "university"): AdminUniversity {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    code: string(row.code, `${path}.code`),
    name: string(row.name, `${path}.name`),
    short_name: row.short_name === null || row.short_name === undefined ? null : string(row.short_name, `${path}.short_name`),
    description: row.description === null || row.description === undefined ? null : string(row.description, `${path}.description`),
    website: row.website === null || row.website === undefined ? null : string(row.website, `${path}.website`),
    region: row.region === null || row.region === undefined ? null : string(row.region, `${path}.region`),
    is_active: boolean(row.is_active, `${path}.is_active`),
    majors_count: integer(row.majors_count ?? 0, `${path}.majors_count`),
    created_at: string(row.created_at, `${path}.created_at`),
  };
}

export function parseAdminMajor(value: unknown, path = "major"): AdminMajor {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    university_id: string(row.university_id, `${path}.university_id`),
    code: string(row.code, `${path}.code`),
    name: string(row.name, `${path}.name`),
    description: row.description === null || row.description === undefined ? null : string(row.description, `${path}.description`),
    is_active: boolean(row.is_active, `${path}.is_active`),
    created_at: string(row.created_at, `${path}.created_at`),
  };
}

export function parseAdminAdmissionRule(value: unknown, path = "admission_rule"): AdminAdmissionRule {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    university_id: string(row.university_id, `${path}.university_id`),
    university_name: string(row.university_name ?? "", `${path}.university_name`),
    major_id: string(row.major_id, `${path}.major_id`),
    major_name: string(row.major_name ?? "", `${path}.major_name`),
    year: integer(row.year, `${path}.year`),
    method_id: string(row.method_id, `${path}.method_id`),
    method_code: string(row.method_code ?? "", `${path}.method_code`),
    method_name: string(row.method_name ?? "", `${path}.method_name`),
    subject_combination: string(row.subject_combination, `${path}.subject_combination`),
    quota: row.quota === null || row.quota === undefined ? null : integer(row.quota, `${path}.quota`),
    historical_score: row.historical_score === null || row.historical_score === undefined ? null : number(row.historical_score, `${path}.historical_score`),
    source_reference: row.source_reference === null || row.source_reference === undefined ? null : string(row.source_reference, `${path}.source_reference`),
    is_active: boolean(row.is_active, `${path}.is_active`),
  };
}

export function parseAdminAdmissionImportHistory(value: unknown, path = "import_history"): AdminAdmissionImportHistory {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    file_name: string(row.file_name, `${path}.file_name`),
    file_format: string(row.file_format, `${path}.file_format`),
    status: string(row.status, `${path}.status`),
    total_rows: integer(row.total_rows, `${path}.total_rows`),
    valid_rows: integer(row.valid_rows, `${path}.valid_rows`),
    imported_rows: integer(row.imported_rows, `${path}.imported_rows`),
    updated_rows: integer(row.updated_rows, `${path}.updated_rows`),
    skipped_rows: integer(row.skipped_rows, `${path}.skipped_rows`),
    error_rows: integer(row.error_rows, `${path}.error_rows`),
    target_year: row.target_year === null || row.target_year === undefined ? null : integer(row.target_year, `${path}.target_year`),
    data_source_name: row.data_source_name === null || row.data_source_name === undefined ? null : string(row.data_source_name, `${path}.data_source_name`),
    source_reference: row.source_reference === null || row.source_reference === undefined ? null : string(row.source_reference, `${path}.source_reference`),
    created_at: string(row.created_at, `${path}.created_at`),
  };
}

async function request<T>(path: string, parse: (value: unknown) => T, init: RequestInit = {}): Promise<T> {
  async function send(): Promise<Response> {
    try {
      return await fetch(`/api/admin/${path}`, {
        ...init,
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch {
      throw new AdminApiError("Không thể kết nối đến máy chủ. Hãy kiểm tra backend.", 503, "NETWORK_ERROR");
    }
  }
  let response = await send();
  if (response.status === 401) {
    try {
      await refreshBrowserSession();
      response = await send();
    } catch {
      throw new AdminApiError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", 401, "SESSION_EXPIRED");
    }
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope =
      body && typeof body === "object" && "error" in body
        ? (body as { error?: { code?: string; message?: string } }).error
        : undefined;
    throw new AdminApiError(
      envelope?.message ?? `Yêu cầu thất bại (${response.status}).`,
      response.status,
      envelope?.code ?? "HTTP_ERROR"
    );
  }
  try {
    return parse(body);
  } catch (error) {
    if (error instanceof ApiContractError) {
      throw new AdminApiError("Dữ liệu backend không đúng hợp đồng API.", 503, "CONTRACT_ERROR");
    }
    throw error;
  }
}

export const adminApi = {
  // Subjects & Curriculum
  subjects: () => request("subjects?offset=0&limit=200", (v) => array(v, "subjects", parseAdminSubject)),
  createSubject: async (data: { code: string; name: string; grade_level?: number | null; description?: string | null }) =>
    request("subjects", parseAdminSubject, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify(data),
    }),
  curricula: () => request("curricula", (v) => array(v, "curricula", parseAdminCurriculum)),
  curriculumVersions: (curriculumId?: string) => {
    const q = curriculumId ? `?curriculum_id=${encodeURIComponent(curriculumId)}` : "";
    return request(`curriculum-versions${q}`, (v) => array(v, "curriculum_versions", parseAdminCurriculumVersion));
  },
  curriculumTree: (subjectId: string) =>
    request(`subjects/${encodeURIComponent(subjectId)}/curriculum-tree`, parseAdminSubjectTree),
  createChapter: async (data: { subject_id: string; code: string; name: string; order_index: number }) =>
    request("chapters", (v) => v, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify(data),
    }),
  createTopic: async (data: { chapter_id: string; code: string; name: string; order_index: number }) =>
    request("topics", (v) => v, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify(data),
    }),
  createProblemType: async (data: { topic_id: string; code: string; name: string; order_index: number }) =>
    request("problem-types", (v) => v, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify(data),
    }),
  createConcept: async (data: { subject_id: string; code: string; name: string; grade_level?: number | null }) =>
    request("concepts", (v) => v, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify(data),
    }),

  // Question Bank & Supply Pipeline
  questions: (params?: { subject?: string; status?: string; limit?: number }) => {
    const q = new URLSearchParams({ offset: "0", limit: String(params?.limit ?? 100) });
    if (params?.subject) q.set("subject", params.subject);
    if (params?.status) q.set("status", params.status);
    return request(`questions?${q.toString()}`, (v) => array(v, "questions", parseAdminQuestion));
  },
  approveQuestion: async (questionId: string) =>
    request(`questions/${encodeURIComponent(questionId)}/approve`, parseAdminQuestion, {
      method: "POST",
      headers: { "X-CSRF-Token": await getCsrfToken() },
    }),
  supplyGaps: (subjectId?: string) => {
    const q = new URLSearchParams({ offset: "0", limit: "100" });
    if (subjectId) q.set("subject_id", subjectId);
    return request(`question-supply/gaps?${q.toString()}`, (v) => array(v, "supply_gaps", parseAdminSupplyGap));
  },
  reassessOpenGaps: async () =>
    request("question-supply/gaps/reassess-open", (v) => array(v, "supply_gaps", parseAdminSupplyGap), {
      method: "POST",
      headers: { "X-CSRF-Token": await getCsrfToken() },
    }),
  planGapAcquisition: async (gapId: string) =>
    request(`question-supply/gaps/${encodeURIComponent(gapId)}/acquisition`, parseAdminAcquisitionRequest, {
      method: "POST",
      headers: { "X-CSRF-Token": await getCsrfToken() },
    }),
  acquisitionRequests: () =>
    request("question-acquisition/requests?offset=0&limit=100", (v) =>
      array(v, "acquisition_requests", parseAdminAcquisitionRequest)
    ),
  validationBatches: () =>
    request("question-validation/batches?offset=0&limit=100", (v) =>
      array(v, "validation_batches", parseAdminValidationBatch)
    ),

  // AI Governance & Observability
  aiUsageSummary: () => request("ai/usage/summary", parseAdminAIUsageSummary),
  aiUsageLogs: (page = 1, pageSize = 50) =>
    request(`ai/usage?page=${page}&page_size=${pageSize}`, parseAdminAIRequestLogPagination),

  // University Admission Governance
  universities: (search?: string) => {
    const q = new URLSearchParams({ offset: "0", limit: "100" });
    if (search) q.set("search", search);
    return request(`admission/universities?${q.toString()}`, (v) => array(v, "universities", parseAdminUniversity));
  },
  createUniversity: async (data: {
    code: string;
    name: string;
    short_name?: string | null;
    region?: string | null;
    website?: string | null;
  }) =>
    request("admission/universities", parseAdminUniversity, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify(data),
    }),
  majorsByUniversity: (universityId: string) =>
    request(`admission/universities/${encodeURIComponent(universityId)}/majors`, (v) =>
      array(v, "majors", parseAdminMajor)
    ),
  createMajor: async (data: { university_id: string; code: string; name: string; description?: string | null }) =>
    request("admission/majors", parseAdminMajor, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify(data),
    }),
  rulesByMajor: (majorId: string) =>
    request(`admission/majors/${encodeURIComponent(majorId)}/rules`, (v) =>
      array(v, "admission_rules", parseAdminAdmissionRule)
    ),
  admissionImportHistory: () =>
    request("admission/import/history?offset=0&limit=50", (v) =>
      array(v, "import_history", parseAdminAdmissionImportHistory)
    ),
};
