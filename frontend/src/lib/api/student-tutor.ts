export const TUTOR_MESSAGE_MAX_LENGTH = 2000;

export interface StudentTutorRequest {
  message: string;
  stream: false;
}

/** Keep the UI request scoped to a single question; never forward arbitrary client fields. */
export function parseStudentTutorRequest(value: unknown): StudentTutorRequest | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const message = (value as Record<string, unknown>).message;
  if (typeof message !== "string") return null;
  const trimmed = message.trim();
  if (!trimmed || trimmed.length > TUTOR_MESSAGE_MAX_LENGTH) return null;
  return { message: trimmed, stream: false };
}

export function parseStudentTutorReply(value: unknown): string | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const reply = (value as Record<string, unknown>).reply;
  return typeof reply === "string" && reply.trim() ? reply.trim() : null;
}
