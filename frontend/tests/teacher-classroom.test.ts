import assert from "node:assert/strict";
import test from "node:test";
import { assignmentProgress, avatarSeed, classroomActivity, classroomPage, presenceLabel } from "../src/features/teacher/classroom-model";
import { DEMO_CLASSROOM_STUDENTS as INITIAL_STUDENTS } from "../src/features/teacher/classroom-demo";
import { classroomStudents } from "../src/features/teacher/classroom-adapter";
import type { ClassroomStudentInfo } from "../src/features/teacher/classroom-types";
import { CLASSROOM_COLUMNS, CLASSROOM_ROWS, classroomSeatPosition, TEACHER_CAMERA } from "../src/features/teacher/classroom-layout";
import { celebrationProgress, classMomentSummary, defaultDeskStyle, parseClassroomStyles, serializeClassroomStyles } from "../src/features/teacher/classroom-personalization";

const student: ClassroomStudentInfo = {
  id: "student-1", name: "Đỗ Ngọc Ánh", email: "anh@example.com", status: "ACTIVE",
  overallMastery: 20, completedAssignments: 3, totalAssignments: 8,
  latestActivityAt: "Vừa xong", avatarSeed: "NA", weakTopics: ["Đạo hàm"],
};

test("ten pupils occupy five forward-facing rows with a central aisle", () => {
  const positions = Array.from({ length: 10 }, (_, index) => classroomSeatPosition(index));
  assert.equal(CLASSROOM_COLUMNS * CLASSROOM_ROWS, 10);
  assert.equal(new Set(positions.map((position) => `${position.x},${position.z}`)).size, 10);
  for (let row = 0; row < CLASSROOM_ROWS; row++) {
    const left = positions[row * 2];
    const right = positions[row * 2 + 1];
    assert.equal(left.z, right.z);
    assert.ok(left.x < 0 && right.x > 0);
    assert.ok(right.x - left.x > 3);
    assert.ok(TEACHER_CAMERA.position.z > left.z);
    if (row > 0) assert.ok(left.z < positions[(row - 1) * 2].z);
  }
  assert.ok(Math.abs(TEACHER_CAMERA.position.x) < 1);
  assert.ok(TEACHER_CAMERA.position.y > 2);
});

test("enrollment, low mastery and recent activity do not invent presence or a raised hand", () => {
  assert.equal(presenceLabel(student), "Chưa có trạng thái online");
  assert.equal(classroomActivity(student), "idle");
  assert.equal(classroomActivity({ ...student, presence: "online", activity: "studying" }), "studying");
});

test("explicit support requests and offline state determine the avatar pose", () => {
  const help = { ...student, presence: "online" as const, activity: "completed" as const, helpRequest: { id: "help-1", message: "Cần hỗ trợ" } };
  assert.equal(classroomActivity(help), "help");
  assert.equal(classroomActivity({ ...help, presence: "offline" }), "offline");
});

test("a class larger than ten keeps every student across seat groups", () => {
  const roster = Array.from({ length: 23 }, (_, index) => ({ ...student, id: `student-${index}` }));
  const first = classroomPage(roster, "", 0);
  const last = classroomPage(roster, "", 2);
  assert.equal(first.pageCount, 3);
  assert.equal(first.seats.length, 10);
  assert.equal(last.seats.filter((seat) => seat.student).length, 3);
  assert.equal(last.seats[2].student?.id, "student-22");
  assert.equal(last.seats[3].student, null);
  assert.equal(last.seats[0].number, 21);
  assert.equal(classroomPage(roster, "", 100).page, 2);
});

test("Vietnamese search, empty results, and shrinking a filtered roster are safe", () => {
  assert.equal(classroomPage([student], "do ngoc anh", 2).seats[0].student?.id, student.id);
  assert.equal(classroomPage([student], "ANH@EXAMPLE", 0).matches.length, 1);
  const empty = classroomPage([student], "missing", 2);
  assert.equal(empty.matches.length, 0);
  assert.equal(empty.page, 0);
  assert.ok(empty.seats.every((seat) => seat.student === null));
});

test("search preserves desk numbers and reaches matching students beyond the first ten", () => {
  const roster = Array.from({ length: 23 }, (_, index) => ({ ...student, id: `student-${index}`, name: `Student ${index}` }));
  roster[6].name = "Đỗ Gia Hân";
  roster[22].name = "Đỗ Ngọc Ánh";
  const first = classroomPage(roster, "do", 0);
  const last = classroomPage(roster, "do", 1);
  assert.equal(first.pageCount, 2);
  assert.equal(first.seats[6].student?.id, "student-6");
  assert.equal(first.seats[0].student, null);
  assert.equal(last.seats[2].number, 23);
  assert.equal(last.seats[2].student?.id, "student-22");
});

test("progress handles empty assignments and out-of-range counts without NaN", () => {
  assert.equal(assignmentProgress(student), 38);
  assert.equal(assignmentProgress({ ...student, totalAssignments: 0 }), 0);
  assert.equal(assignmentProgress({ ...student, completedAssignments: 20 }), 100);
  assert.equal(assignmentProgress({ ...student, completedAssignments: -1 }), 0);
});

test("the demo has ten unique students and its summary matches the roster", () => {
  assert.equal(INITIAL_STUDENTS.length, 10);
  assert.equal(new Set(INITIAL_STUDENTS.map((item) => item.id)).size, 10);
  const seed = avatarSeed(INITIAL_STUDENTS[0].id);
  assert.equal(seed, avatarSeed([...INITIAL_STUDENTS].reverse()[9].id));
});

test("desk style is stable per student and storage only accepts supported choices for known pupils", () => {
  assert.deepEqual(defaultDeskStyle(student.id), defaultDeskStyle(student.id));
  const style = { bagColor: "peach" as const, decoration: "star" as const, glasses: true };
  const parsed = parseClassroomStyles(serializeClassroomStyles({ [student.id]: style, outsider: style }), [student.id]);
  assert.deepEqual(parsed[student.id], style);
  assert.equal(parsed.outsider, undefined);
  assert.deepEqual(Object.keys(parseClassroomStyles('{"version":1,"students":{"student-1":{"bagColor":"url(evil)","decoration":"star","glasses":true}}}', [student.id])), []);
});

test("damaged local preferences and prototype keys cannot break the classroom", () => {
  for (const value of [null, "invalid", "[]", '{"version":2,"students":{}}']) assert.equal(Object.keys(parseClassroomStyles(value, [student.id])).length, 0);
  const parsed = parseClassroomStyles('{"version":1,"students":{"__proto__":{"bagColor":"mint","decoration":"star","glasses":true}}}', ["__proto__"]);
  assert.equal(Object.getPrototypeOf(parsed), null);
  assert.equal(Object.keys(parsed).length, 0);
});

test("shared moments omit student identities and preserve actual completion counts", () => {
  const anonymous = classMomentSummary(INITIAL_STUDENTS, "Private classroom name", false);
  assert.equal(anonymous.completed, 3);
  assert.equal(anonymous.total, 10);
  assert.equal(anonymous.goalReached, false);
  const serialized = JSON.stringify(anonymous);
  assert.ok(!serialized.includes("Private classroom name"));
  for (const item of INITIAL_STUDENTS) { assert.ok(!serialized.includes(item.email)); assert.ok(!serialized.includes(item.id)); assert.ok(!serialized.includes(item.name)); }
  assert.equal(classMomentSummary(INITIAL_STUDENTS, "Lớp 12A", true).classroom, "Lớp 12A");
});

test("empty assignments never award a class milestone, and celebrations end after two seconds", () => {
  assert.equal(classMomentSummary([], "", false).goalReached, false);
  assert.equal(classMomentSummary([{ ...student, totalAssignments: 0 }], "", false).goalReached, false);
  assert.equal(classMomentSummary([{ ...student, completedAssignments: 8 }], "", false).goalReached, true);
  assert.equal(celebrationProgress(-1, 1000), 0);
  assert.equal(celebrationProgress(1000, 500), 0);
  assert.equal(celebrationProgress(1000, 2000), 1);
  assert.equal(celebrationProgress(1000, 3000), 0);
  assert.equal(celebrationProgress(1000, 9000), 0);
});

test("live roster keeps missing evidence unknown and excludes synthetic pupils", () => {
  const record = { student_id: "real-1", full_name: "Bạn thật", email: "real@example.test", status: "ACTIVE", is_synthetic: false };
  const live = classroomStudents([record, { ...record, student_id: "synthetic", is_synthetic: true }]);
  assert.equal(live.length, 1);
  assert.equal(live[0].id, record.student_id);
  assert.equal(live[0].name, record.full_name);
  assert.equal(live[0].overallMastery, null);
  assert.equal(live[0].completedAssignments, null);
  assert.equal(live[0].totalAssignments, null);
  assert.equal(live[0].latestActivityAt, null);
  assert.equal(live[0].helpRequest, undefined);
  assert.equal(presenceLabel(live[0]), "Chưa có trạng thái online");
  assert.equal(classroomActivity(live[0]), "idle");
  assert.equal(assignmentProgress(live[0]), null);
  const summary = classMomentSummary(live, "Private", false, false);
  assert.equal(summary.hasProgress, false);
  assert.equal(summary.goalReached, false);
  assert.equal(summary.isDemo, false);
  assert.deepEqual(classroomStudents([]), []);
});

test("unknown or incomplete progress never awards completion", () => {
  for (const change of [{ totalAssignments: null }, { completedAssignments: null }, { totalAssignments: NaN }]) {
    const partial = { ...student, ...change };
    assert.equal(assignmentProgress(partial), null);
    assert.equal(classMomentSummary([partial], "", false, false).hasProgress, false);
    assert.equal(classMomentSummary([partial], "", false, false).goalReached, false);
  }
});
