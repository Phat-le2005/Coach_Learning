import { ApiContractError, array, integer, oneOf, record, string } from "./validation";

export interface QuestionVisual {
  index: number;
  path: string;
  url: string;
  role: "question" | "answer" | "solution";
}

/** Only cookie-authenticated application URLs may be embedded in question HTML. */
export function isQuestionImageUrl(url: string): boolean {
  return /^\/api\/(?:[\w.-]+\/)*[\w.-]+$/.test(url)
    && !url.split("/").some((part) => part === "." || part === "..");
}

export function parseQuestionVisuals(value: unknown, path = "visuals"): QuestionVisual[] {
  return array(value ?? [], path, (value, p) => {
    const row = record(value, p);
    const url = string(row.url, `${p}.url`);
    const index = integer(row.index, `${p}.index`);
    if (index < 0 || !isQuestionImageUrl(url)) throw new ApiContractError("Invalid question image", p);
    return {
      index, url, path: string(row.path, `${p}.path`),
      role: oneOf(row.role ?? "question", `${p}.role`, ["question", "answer", "solution"] as const),
    };
  });
}

const imagePattern = () => /!\[([^\]\n]*)\]\(\s*(?:<([^>\n]+)>|([^\s)]+))\s*\)/g;

export function prepareQuestionVisuals(content: string, visuals: readonly QuestionVisual[],
  role: QuestionVisual["role"] = "question", gallery = true, relatedContent: readonly string[] = []): string {
  const used = new Set<string>();
  for (const other of relatedContent) {
    for (const match of other.matchAll(imagePattern())) used.add((match[2] ?? match[3]).replace(/^\.\//, ""));
  }
  const safe = visuals.filter((visual) => isQuestionImageUrl(visual.url));
  const prepared = content.replace(imagePattern(), (_match, alt: string, angle: string, plain: string) => {
    const path = (angle ?? plain).replace(/^\.\//, "");
    const visual = safe.find((visual) => visual.path === path || visual.url === path);
    if (!visual) return "[Hình minh họa chưa khả dụng]";
    if (used.has(visual.path)) return "";
    used.add(visual.path);
    // Strip bracket delimiters in labels, then let MathRenderer escape HTML.
    return `![${alt.replace(/[\[\]\r\n]/g, " ")}](${visual.url})`;
  });
  const additional = gallery ? safe.filter((visual) => visual.role === role && !used.has(visual.path)) : [];
  const unique = additional.filter((visual) => {
    if (used.has(visual.path)) return false;
    used.add(visual.path);
    return true;
  });
  return [prepared, ...unique.map((visual) => `![Hình minh họa](${visual.url})`)].join("\n\n");
}
