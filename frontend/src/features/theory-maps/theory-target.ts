import type { TheorySummary } from "./api";
/** A curriculum label is not a document ID. Abstain when the name is absent or ambiguous. */
export function resolveTheoryDocument(items: TheorySummary[], topic?: string | null) {
  const query = topic?.normalize("NFC").trim().toLocaleLowerCase("vi");
  if (!query) return items[0] ?? null;
  const exact = items.filter(item => item.title.normalize("NFC").trim().toLocaleLowerCase("vi") === query);
  if (exact.length === 1) return exact[0];
  if (exact.length > 1) return null;
  const matches = items.filter(item => {
    const title = item.title.normalize("NFC").trim().toLocaleLowerCase("vi");
    return title && (title.includes(query) || query.includes(title));
  });
  return matches.length === 1 ? matches[0] : null;
}
