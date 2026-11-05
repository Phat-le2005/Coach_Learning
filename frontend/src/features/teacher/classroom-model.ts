import type { ClassroomStudentInfo } from "./classroom-types";

export const CLASSROOM_SEAT_COUNT = 10;
export type ClassroomActivity = "studying" | "help" | "completed" | "offline" | "idle";
export interface ClassroomSeat {
  number: number;
  student: ClassroomStudentInfo | null;
}

export const ACTIVITY_LABELS: Record<ClassroomActivity, string> = {
  studying: "Đang học",
  help: "Cần hỗ trợ",
  completed: "Hoàn thành",
  offline: "Ngoại tuyến",
  idle: "Chưa có hoạt động trực tiếp",
};

export function classroomActivity(student: ClassroomStudentInfo): ClassroomActivity {
  if (student.presence === "offline") return "offline";
  if (student.helpRequest) return "help";
  return student.activity ?? "idle";
}

export function presenceLabel(student: ClassroomStudentInfo): string {
  if (student.presence === "online") return "Đang online";
  if (student.presence === "offline") return "Ngoại tuyến";
  return "Chưa có trạng thái online";
}

function searchable(text: string): string {
  return text.toLocaleLowerCase("vi").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d");
}

export function classroomPage(students: readonly ClassroomStudentInfo[], query: string, requestedPage: number) {
  const term = searchable(query.trim());
  const matches = term ? students.filter((student) => searchable(`${student.name} ${student.email}`).includes(term)) : [...students];
  const matchingIds = new Set(matches.map((student) => student.id));
  // Filtering keeps a student's original desk instead of moving them to desk 1.
  const groups = Array.from({ length: Math.ceil(students.length / CLASSROOM_SEAT_COUNT) }, (_, index) => index)
    .filter((index) => students.slice(index * CLASSROOM_SEAT_COUNT, (index + 1) * CLASSROOM_SEAT_COUNT).some((student) => matchingIds.has(student.id)));
  const pageCount = Math.max(1, groups.length);
  const page = Math.max(0, Math.min(pageCount - 1, Number.isFinite(requestedPage) ? Math.floor(requestedPage) : 0));
  const start = (groups[page] ?? 0) * CLASSROOM_SEAT_COUNT;
  const seats: ClassroomSeat[] = Array.from({ length: CLASSROOM_SEAT_COUNT }, (_, index) => {
    const student = students[start + index];
    return { number: start + index + 1, student: student && matchingIds.has(student.id) ? student : null };
  });
  return { matches, seats, page, pageCount };
}

export function assignmentProgress(student: ClassroomStudentInfo): number | null {
  if (student.totalAssignments === null || student.completedAssignments === null || !Number.isFinite(student.totalAssignments) || !Number.isFinite(student.completedAssignments)) return null;
  if (student.totalAssignments <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round(student.completedAssignments / student.totalAssignments * 100)));
}

export function avatarSeed(id: string): number {
  let seed = 0;
  for (const character of id) seed = (Math.imul(seed, 31) + character.charCodeAt(0)) >>> 0;
  return seed;
}
