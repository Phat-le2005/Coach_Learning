export type TeacherTab = "materials" | "classroom" | "student_workspace" | "analytics";

export type MaterialCategory = "theory" | "practice";

export interface TeacherMaterial {
  id: string;
  title: string;
  category: MaterialCategory;
  topic: string;
  format: "pdf" | "docx" | "exam";
  gradeLevel: number;
  description: string;
  itemCount?: number;
  assignedClassrooms: string[];
  updatedAt: string;
  fileSize: string;
  downloadsCount: number;
}

export interface ClassroomStudentInfo {
  id: string;
  name: string;
  email: string;
  status: "ACTIVE" | "INACTIVE";
  overallMastery: number;
  completedAssignments: number;
  totalAssignments: number;
  latestActivityAt: string;
  avatarSeed: string;
  weakTopics: string[];
}

export interface StudentStepSolution {
  stepIndex: number;
  stepKind: string;
  latex: string;
  explanation: string;
  status: "VERIFIED" | "PENDING" | "ERROR";
  aiFeedback?: string;
}

export interface StudentAttemptInspection {
  attemptId: string;
  studentId: string;
  studentName: string;
  studentEmail: string;
  problemId: string;
  problemTitle: string;
  problemContent: string;
  revision: number;
  status: "IN_PROGRESS" | "SUBMITTED" | "EVALUATED";
  score?: number;
  lastActive: string;
  strokesCount: number;
  drawnFormulaPreview: string; // text representation or svg/strokes
  steps: StudentStepSolution[];
  teacherNote?: string;
}

export interface CompetencyTopicMetric {
  code: string;
  name: string;
  masteryPercent: number;
  studentCountPassed: number;
  studentCountTotal: number;
  status: "STRONG" | "AVERAGE" | "WEAK";
  commonMisconception?: string;
}

export interface ClassroomOverview {
  id: string;
  name: string;
  gradeLevel: number;
  academicYear: string;
  totalStudents: number;
  activeStudents: number;
  averageMastery: number;
  assignmentCompletionRate: number;
  needsAttentionCount: number;
}
