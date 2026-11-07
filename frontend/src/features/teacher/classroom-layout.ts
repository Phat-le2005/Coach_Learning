export const CLASSROOM_COLUMNS = 2;
export const CLASSROOM_ROWS = 5;

/** Row 0 is closest to the teacher. Every pupil faces forward along +Z. */
export function classroomSeatPosition(index: number) {
  const column = index % CLASSROOM_COLUMNS;
  const row = Math.floor(index / CLASSROOM_COLUMNS);
  return { x: column === 0 ? -2.25 : 2.25, z: 4.2 - row * 2.8, row, column };
}

export const WIDE_CLASSROOM_COLUMNS = 5;
export const WIDE_CLASSROOM_ROWS = 2;

/** Wide 5-column × 2-row horizontal seating that fills the 16:9 widescreen classroom. */
export function classroomWideSeatPosition(index: number) {
  const column = index % WIDE_CLASSROOM_COLUMNS;
  const row = Math.floor(index / WIDE_CLASSROOM_COLUMNS);
  const x = (column - 2) * 3.1;
  const z = row === 0 ? 1.55 : -1.85;
  return { x, z, row, column };
}

export const TEACHER_CAMERA = {
  fov: 45,
  position: { x: .45, y: 7.5, z: 10.5 },
  target: { x: 0, y: .7, z: -1.2 },
} as const;
