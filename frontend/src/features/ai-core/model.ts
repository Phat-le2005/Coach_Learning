import type { StudentMasteryRead } from "../../lib/api/contracts";

export interface CoreMasteryRow {
  id: string; name: string; kind: "Khái niệm" | "Dạng bài"; state: string;
  score: number | null; confidence: number | null; attempts: number;
}
export interface CoreRelation { from: string; to: string; kind: "Tiên quyết" | "Dạng bài → khái niệm" }
export interface CoreGraph {
  concepts: number; mappings: number; prerequisites: number; synthetic: boolean; relations: CoreRelation[];
}

export function coreMasteryRows(mastery: StudentMasteryRead): CoreMasteryRow[] {
  return mastery.subjects.flatMap(subject => [
    ...subject.concepts.map(row => ({ ...row, id: row.concept_id, kind: "Khái niệm" as const })),
    ...subject.chapters.flatMap(chapter => chapter.topics.flatMap(topic => topic.problem_types.map(row => (
      { ...row, id: row.problem_type_id, kind: "Dạng bài" as const }
    )))),
  ]).map(row => ({
    id: row.id, name: row.name, kind: row.kind, state: row.state,
    score: row.attempt_count > 0 && row.state !== "NOT_STARTED" ? row.mastery_score : null,
    confidence: row.attempt_count > 0 && row.state !== "NOT_STARTED" ? row.confidence : null,
    attempts: row.attempt_count,
  })).sort((a, b) => Number(a.score === null) - Number(b.score === null) || (a.score ?? 0) - (b.score ?? 0) || a.name.localeCompare(b.name, "vi"));
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("INVALID_CORE_SNAPSHOT");
  return value as Record<string, unknown>;
}
function text(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) throw new Error("INVALID_CORE_SNAPSHOT");
  return value;
}
function list(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new Error("INVALID_CORE_SNAPSHOT");
  return value;
}

/** Project only graph data from the authenticated student's snapshot; do not ship the private profile. */
export function coreGraph(value: unknown, studentId: string, masteryRows: CoreMasteryRow[]): CoreGraph {
  const root = object(value), profile = object(root.basic_profile), knowledge = object(root.knowledge_state);
  if (profile.student_id !== studentId) throw new Error("CORE_IDENTITY_MISMATCH");
  if (typeof profile.is_synthetic !== "boolean") throw new Error("INVALID_CORE_SNAPSHOT");
  const concepts = list(knowledge.concepts), mappings = list(knowledge.problem_type_concept_links);
  const names = new Map(masteryRows.map(row => [row.id, row.name]));
  concepts.forEach(value => { const row = object(value); names.set(text(row.concept_id), text(row.name)); });
  const prerequisites = new Map<string, CoreRelation>();
  concepts.forEach(value => {
    const row = object(value), target = text(row.concept_id);
    list(row.prerequisites).forEach(value => {
      const prerequisite = object(value), source = text(prerequisite.concept_id);
      prerequisites.set(`${source}:${target}`, { from: text(prerequisite.name), to: text(row.name), kind: "Tiên quyết" });
    });
  });
  const links = new Map<string, CoreRelation>();
  mappings.forEach(value => {
    const row = object(value), source = text(row.problem_type_id), target = text(row.concept_id);
    links.set(`${source}:${target}`, { from: names.get(source) ?? source, to: names.get(target) ?? target, kind: "Dạng bài → khái niệm" });
  });
  return { concepts: concepts.length, mappings: links.size, prerequisites: prerequisites.size,
    synthetic: profile.is_synthetic, relations: [...prerequisites.values(), ...links.values()] };
}

export function masteryChange(before: number | null | undefined, after: number | null): number | null {
  return before == null || after === null ? null : Math.round((after - before) * 1000) / 10;
}
