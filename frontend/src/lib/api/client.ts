import type {
  ConceptMasteryRead,
  InkDocumentRead,
  InkPageRead,
  InkPageWrite,
  InkSaveRead,
  LoginRequest,
  ProblemRead,
  ProblemTypeMasteryRead,
  RefreshRequest,
  SolutionAttemptRead,
  StudentLearningStateRead,
  StudentMasteryRead,
  TokenPair,
  UserRead,
} from "./contracts";
import {
  parseConceptMastery,
  parseInkDocumentRead,
  parseInkPageRead,
  parseInkSaveRead,
  parseProblemRead,
  parseProblemTypeMastery,
  parseSolutionAttemptRead,
  parseStudentLearningState,
  parseStudentMastery,
  parseTokenPair,
  parseUserRead,
  validateLoginRequest,
} from "./contracts";
import { ApiContractError, record, string } from "./validation";

export type ApiErrorCategory = "unauthorized" | "forbidden" | "not_found" | "conflict" | "validation" | "unavailable" | "http";
export interface ApiErrorEnvelope { error: { code: string; message: string; details?: unknown } }

export class ApiResponseError extends Error {
  constructor(message: string, public readonly status: number, public readonly code: string, public readonly category: ApiErrorCategory, public readonly details?: unknown) {
    super(message);
    this.name = "ApiResponseError";
  }
}

export class ApiNetworkError extends Error {
  constructor(message: string, public readonly cause?: unknown) {
    super(message);
    this.name = "ApiNetworkError";
  }
}

export const API_PATHS = {
  login: "/auth/login",
  refresh: "/auth/refresh",
  me: "/auth/me",
  studentLearningState: "/students/me/learning-state",
  studentMastery: "/students/me/mastery",
  studentProblemTypeMastery: (id: string) => `/students/me/mastery/problem-types/${encodeURIComponent(id)}`,
  studentConceptMastery: (id: string) => `/students/me/mastery/concepts/${encodeURIComponent(id)}`,
  mathAttempt: (id: string) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}`,
  mathAttemptProblem: (id: string) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}/problem`,
  mathInkDocument: (id: string) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}/ink`,
  mathInkPage: (id: string, pageIndex: number) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}/ink/pages/${pageIndex}`,
} as const;

type ResponseParser<T> = (value: unknown, path?: string) => T;
type Fetcher = typeof fetch;
export interface ApiClientOptions { baseUrl: string; fetcher?: Fetcher }

function statusCategory(status: number): ApiErrorCategory {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422) return "validation";
  if (status === 503) return "unavailable";
  return "http";
}

function parseErrorEnvelope(value: unknown): ApiErrorEnvelope | null {
  try {
    const outer = record(value, "error_response");
    const detail = record(outer.error, "error_response.error");
    let details: unknown;
    if (detail.details !== undefined && detail.details !== null) {
      if (!Array.isArray(detail.details)) throw new ApiContractError("Expected validation issue array", "error_response.error.details");
      details = detail.details.map((item, index) => {
        const issue = record(item, `error_response.error.details[${index}]`);
        return { field: string(issue.field, `error_response.error.details[${index}].field`), message: string(issue.message, `error_response.error.details[${index}].message`) };
      });
    }
    return { error: { code: string(detail.code, "error_response.error.code"), message: string(detail.message, "error_response.error.message"), ...(details === undefined ? {} : { details }) } };
  } catch {
    return null;
  }
}

export function normalizeApiBaseUrl(value: string): string {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) throw new Error("API_BASE_URL must be an HTTP(S) URL without credentials.");
  if (url.pathname !== "/" || url.search || url.hash) throw new Error("API_BASE_URL must contain only the origin; canonical API paths are root paths.");
  return url.origin;
}

export function getBackendBaseUrl(): string {
  const value = process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!value) throw new Error("API_BASE_URL is not configured.");
  return normalizeApiBaseUrl(value);
}

export function createApiClient({ baseUrl, fetcher = fetch }: ApiClientOptions) {
  const origin = normalizeApiBaseUrl(baseUrl);

  async function request<T>(path: string, parser: ResponseParser<T>, init: RequestInit = {}, accessToken?: string): Promise<T> {
    if (!path.startsWith("/") || path.startsWith("/api/v1")) throw new Error(`Non-canonical API path: ${path}`);
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    let response: Response;
    try {
      response = await fetcher(`${origin}${path}`, { ...init, headers, cache: "no-store" });
    } catch (error) {
      throw new ApiNetworkError("Không thể kết nối tới EduMS API.", error);
    }
    let body: unknown = null;
    const raw = await response.text();
    if (raw) {
      try { body = JSON.parse(raw) as unknown; }
      catch { if (response.ok) throw new ApiContractError("Expected a JSON response"); }
    }
    if (!response.ok) {
      const envelope = parseErrorEnvelope(body);
      throw new ApiResponseError(envelope?.error.message ?? "EduMS API trả về lỗi không hợp lệ.", response.status, envelope?.error.code ?? "HTTP_ERROR", statusCategory(response.status), envelope?.error.details);
    }
    return parser(body);
  }

  return {
    login(input: LoginRequest): Promise<TokenPair> {
      return request(API_PATHS.login, parseTokenPair, { method: "POST", body: JSON.stringify(validateLoginRequest(input)) });
    },
    refresh(refreshToken: string): Promise<TokenPair> {
      const body: RefreshRequest = { refresh_token: refreshToken };
      return request(API_PATHS.refresh, parseTokenPair, { method: "POST", body: JSON.stringify(body) });
    },
    me(accessToken: string): Promise<UserRead> { return request(API_PATHS.me, parseUserRead, { method: "GET" }, accessToken); },
    studentLearningState(accessToken: string, subjectId?: string): Promise<StudentLearningStateRead> {
      const suffix = subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : "";
      return request(`${API_PATHS.studentLearningState}${suffix}`, parseStudentLearningState, { method: "GET" }, accessToken);
    },
    studentMastery(accessToken: string): Promise<StudentMasteryRead> {
      return request(API_PATHS.studentMastery, parseStudentMastery, { method: "GET" }, accessToken);
    },
    studentProblemTypeMastery(accessToken: string, problemTypeId: string): Promise<ProblemTypeMasteryRead> {
      return request(API_PATHS.studentProblemTypeMastery(problemTypeId), parseProblemTypeMastery, { method: "GET" }, accessToken);
    },
    studentConceptMastery(accessToken: string, conceptId: string): Promise<ConceptMasteryRead> {
      return request(API_PATHS.studentConceptMastery(conceptId), parseConceptMastery, { method: "GET" }, accessToken);
    },
    getMathAttempt(accessToken: string, attemptId: string): Promise<SolutionAttemptRead> {
      return request(API_PATHS.mathAttempt(attemptId), parseSolutionAttemptRead, { method: "GET" }, accessToken);
    },
    getMathAttemptProblem(accessToken: string, attemptId: string): Promise<ProblemRead> {
      return request(API_PATHS.mathAttemptProblem(attemptId), parseProblemRead, { method: "GET" }, accessToken);
    },
    getMathInkDocument(accessToken: string, attemptId: string): Promise<InkDocumentRead> {
      return request(API_PATHS.mathInkDocument(attemptId), parseInkDocumentRead, { method: "GET" }, accessToken);
    },
    getMathInkPage(accessToken: string, attemptId: string, pageIndex: number): Promise<InkPageRead> {
      return request(API_PATHS.mathInkPage(attemptId, pageIndex), parseInkPageRead, { method: "GET" }, accessToken);
    },
    saveMathInkPage(accessToken: string, attemptId: string, pageIndex: number, payload: InkPageWrite): Promise<InkSaveRead> {
      return request(
        API_PATHS.mathInkPage(attemptId, pageIndex),
        parseInkSaveRead,
        { method: "PUT", body: JSON.stringify(payload) },
        accessToken,
      );
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
export function createBackendApiClient(): ApiClient { return createApiClient({ baseUrl: getBackendBaseUrl() }); }

export type HealthResponse = { status: "ok" };
export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  let response: Response;
  try {
    response = await fetch(`${getBackendBaseUrl()}/health`, { headers: { Accept: "application/json" }, cache: "no-store", signal });
  } catch (error) {
    throw new ApiNetworkError("Không thể kết nối tới EduMS API.", error);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope = parseErrorEnvelope(body);
    throw new ApiResponseError(envelope?.error.message ?? "EduMS API trả về lỗi.", response.status, envelope?.error.code ?? "HTTP_ERROR", statusCategory(response.status), envelope?.error.details);
  }
  const source = record(body, "response");
  if (source.status !== "ok") throw new ApiContractError("Expected status=ok", "response.status");
  return { status: "ok" };
}
