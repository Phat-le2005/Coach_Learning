import type {
  InkDocumentRead,
  InkPageRead,
  InkPageSummary,
  InkPageWrite,
  InkPoint,
  InkSaveRead,
  InkStroke,
  ProblemOptionRead,
  ProblemRead,
  SolutionAttemptRead,
} from "@/lib/api/contracts";

export type {
  InkDocumentRead,
  InkPageRead,
  InkPageSummary,
  InkPageWrite,
  InkPoint,
  InkSaveRead,
  InkStroke,
  ProblemOptionRead,
  ProblemRead,
  SolutionAttemptRead,
};

export type DrawingTool = "pen" | "highlighter" | "eraser" | "lasso";
export type PaperGrid = "grid" | "lines" | "plain";
export type SyncStatus = "saved" | "saving" | "unsaved" | "offline" | "conflict" | "error";

export interface ColorOption {
  name: string;
  value: string;
}

export const WORKSPACE_COLORS: ColorOption[] = [
  { name: "Đen", value: "#0f172a" },
  { name: "Xanh dương", value: "#2563eb" },
  { name: "Đỏ", value: "#dc2626" },
  { name: "Xanh lá", value: "#059669" },
  { name: "Cam", value: "#d97706" },
  { name: "Tím", value: "#7c3aed" },
];

export const PEN_WIDTHS = [1, 2, 3, 5, 8] as const;
export const HIGHLIGHTER_WIDTHS = [12, 18, 24] as const;

export const A4_WIDTH = 794;
export const A4_HEIGHT = 1123;
export const A4_ASPECT_RATIO = A4_HEIGHT / A4_WIDTH;

export const MAX_PAGES = 30;
export const MAX_STROKES_PER_PAGE = 400;
export const MAX_POINTS_PER_STROKE = 3000;
export const MAX_POINTS_PER_PAGE = 15000;

export interface PageHistory {
  past: InkStroke[][];
  present: InkStroke[];
  future: InkStroke[][];
}

export interface PageState {
  pageIndex: number;
  strokes: InkStroke[];
  history: PageHistory;
  isDirty: boolean;
  clientActionId: string;
  lastSavedAt: number | null;
}

export interface WorkspaceState {
  attemptId: string;
  documentRevision: number;
  currentPageIndex: number;
  pageCount: number;
  pages: Map<number, PageState>;
  syncStatus: SyncStatus;
  syncErrorMessage?: string;
  currentTool: DrawingTool;
  penColor: string;
  penWidth: number;
  highlighterColor: string;
  highlighterWidth: number;
  paperGrid: PaperGrid;
  zoomLevel: number;
  isProblemPaneCollapsed: boolean;
}
