/** Display contract for the classroom. Missing evidence stays null/unknown. */
export interface ClassroomStudentInfo {
  id: string;
  name: string;
  email: string;
  status: string;
  overallMastery: number | null;
  completedAssignments: number | null;
  totalAssignments: number | null;
  latestActivityAt: string | null;
  avatarSeed: string;
  weakTopics: string[];
  /** Enrollment and presence are independent. */
  presence?: "online" | "offline" | "unknown";
  activity?: "studying" | "completed" | "idle";
  helpRequest?: { id: string; message: string };
}
