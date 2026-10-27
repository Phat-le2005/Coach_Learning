export type AttemptStatusTone =
  | "draft"
  | "inProgress"
  | "submitted"
  | "evaluated"
  | "abandoned";

export type AttemptsFilterStatus =
  | "ALL"
  | "IN_PROGRESS"
  | "DRAFT"
  | "SUBMITTED"
  | "EVALUATED"
  | "ABANDONED";

export type AttemptsSortOrder = "updated_desc" | "created_desc" | "created_asc";

export type AttemptsViewMode = "grid" | "list";

export interface AttemptStatusMeta {
  code: string;
  label: string;
  tone: AttemptStatusTone;
  actionLabel: string;
  isResumable: boolean;
}

export interface AttemptCardViewModel {
  id: string;
  href: string;
  shortCode: string;
  title: string;
  contextLabel: string;
  status: AttemptStatusMeta;
  createdAtIso: string;
  updatedAtIso: string;
  submittedAtIso: string | null;
  createdAtLabel: string;
  updatedAtLabel: string | null;
  submittedAtLabel: string | null;
  createdTimestampMs: number;
  updatedTimestampMs: number;
  stepCount: number | null;
  stepSummaryLabel: string;
  revisionNumber: number;
  searchableText: string;
}

export interface AttemptsPaginationViewModel {
  page: number;
  size: number;
  total: number;
  totalPages: number;
  rangeStart: number;
  rangeEnd: number;
  hasPreviousPage: boolean;
  hasNextPage: boolean;
}

export interface StudentAttemptsSubjectOption {
  id: string;
  code?: string;
  name: string;
}

export interface StudentAttemptsViewModel {
  student: {
    displayName: string;
    email?: string;
  };
  subjects: StudentAttemptsSubjectOption[];
  subjectsLoaded: boolean;
  defaultSubjectId?: string;
  activeStatusFilter: AttemptsFilterStatus;
  continueLearningItems: AttemptCardViewModel[];
  totalActiveCount: number;
  libraryItems: AttemptCardViewModel[];
  pagination: AttemptsPaginationViewModel;
}
