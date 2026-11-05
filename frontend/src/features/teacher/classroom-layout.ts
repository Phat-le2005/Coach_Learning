export const CLASSROOM_COLUMNS = 2;
export const CLASSROOM_ROWS = 5;

/** Row 0 is closest to the teacher. Every pupil faces forward along +Z. */
export function classroomSeatPosition(index: number) {
  const column = index % CLASSROOM_COLUMNS;
  const row = Math.floor(index / CLASSROOM_COLUMNS);
  return { x: column === 0 ? -2.25 : 2.25, z: 4.2 - row * 2.8, row, column };
}

export const TEACHER_CAMERA = {
  fov: 45,
  position: { x: .45, y: 7.5, z: 10.5 },
  target: { x: 0, y: .7, z: -1.2 },
} as const;
