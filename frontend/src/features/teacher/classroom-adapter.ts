import type { TeacherStudent } from "./api";
import type { ClassroomStudentInfo } from "./classroom-types";

/** The roster API has no presence, individual mastery or completion evidence. */
export function classroomStudents(students: readonly TeacherStudent[]): ClassroomStudentInfo[] {
  return students.filter((student) => !student.is_synthetic).map((student) => ({
    id: student.student_id,
    name: student.full_name,
    email: student.email,
    status: student.status,
    avatarSeed: student.student_id,
    overallMastery: null,
    completedAssignments: null,
    totalAssignments: null,
    latestActivityAt: null,
    weakTopics: [],
    presence: "unknown",
  }));
}
