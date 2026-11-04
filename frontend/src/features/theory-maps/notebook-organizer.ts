import type { TheoryNode } from "./api";

export interface ParsedTopic {
  concept: TheoryNode;
  formulas: TheoryNode[];
  methods: TheoryNode[];
  examples: TheoryNode[];
  notes: TheoryNode[];
}

export interface ParsedSection {
  section: TheoryNode;
  topics: ParsedTopic[];
  standaloneItems: TheoryNode[];
}

/**
 * Splits example body into problem statement (question) and step-by-step solution.
 */
export function parseExampleBody(body: string): { question: string; solution: string } {
  if (!body) return { question: "", solution: "" };
  const parts = body.split(/(?:Lời giải:|Hướng dẫn giải:|\bGiải:)/i);
  if (parts.length > 1) {
    const question = parts[0].replace(/^Đề bài:\s*/i, "").trim();
    const solution = parts.slice(1).join("\n").trim();
    return { question, solution };
  }
  return { question: body.replace(/^Đề bài:\s*/i, "").trim(), solution: "" };
}

/**
 * Formats multi-line math solution into cleanly separated steps or bullet points.
 */
export function formatSolutionLines(solution: string): string[] {
  if (!solution) return [];
  return solution
    .split(/\n+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/**
 * Organizes a flat or semi-hierarchical list of TheoryNodes into structured
 * Sections and Topics (Dạng toán) with associated Formulas, Methods, Examples, and Trap Notes.
 */
export function organizeTheoryNotebook(nodes: TheoryNode[]): {
  root: TheoryNode | undefined;
  sections: ParsedSection[];
} {
  if (!nodes.length) {
    return { root: undefined, sections: [] };
  }

  const root = nodes.find((node) => node.parent_id === null);
  const rootId = root?.id ?? null;
  const directSections = nodes.filter((n) => n.parent_id === rootId && n.kind === "SECTION");

  // Fallback: If no explicit SECTION kind, treat top-level items as sections
  const sectionNodes =
    directSections.length > 0
      ? directSections
      : nodes.filter((n) => n.parent_id === rootId || n.parent_id === null);

  const sections: ParsedSection[] = [];
  const processedIds = new Set<string>();
  if (rootId) processedIds.add(rootId);

  // Helper to gather all descendant nodes recursively under any parent
  const getDescendants = (parentId: string): TheoryNode[] => {
    const direct = nodes.filter((n) => n.parent_id === parentId);
    return [...direct, ...direct.flatMap((d) => getDescendants(d.id))];
  };

  for (const sec of sectionNodes) {
    processedIds.add(sec.id);
    const allSecNodes = getDescendants(sec.id);

    // Find concepts (topics / dạng toán) either direct or nested under sub-groupings,
    // excluding child concepts that are already sub-items of another concept
    const conceptNodes = allSecNodes.filter(
      (n) =>
        (n.kind === "CONCEPT" || /^Dạng\s+/i.test(n.title)) &&
        !allSecNodes.some(
          (other) =>
            other.id === n.parent_id &&
            (other.kind === "CONCEPT" || /^Dạng\s+/i.test(other.title))
        )
    );
    const topics: ParsedTopic[] = [];

    for (const concept of conceptNodes) {
      processedIds.add(concept.id);
      const subItems = nodes.filter((n) => n.parent_id === concept.id);
      subItems.forEach((item) => processedIds.add(item.id));

      const formulas = [
        ...(concept.latex ? [concept] : []),
        ...subItems.filter(
          (item) =>
            item.kind === "FORMULA" ||
            item.kind === "QUICK_TRICK" ||
            item.title.includes("📐") ||
            item.title.includes("⚡") ||
            item.title.includes("Công thức") ||
            item.title.includes("Mẹo")
        ),
      ];
      const methods = [
        ...(concept.learning_steps && concept.learning_steps.length > 0 ? [concept] : []),
        ...subItems.filter(
          (item) =>
            item.kind === "METHOD" ||
            item.learning_steps.length > 0 ||
            item.title.includes("📝") ||
            item.title.includes("Phương pháp") ||
            item.title.includes("Quy trình") ||
            item.title.includes("Dạng")
        ),
      ];
      const examples = [
        ...(concept.kind === "EXAMPLE" ? [concept] : []),
        ...subItems.filter(
          (item) => item.kind === "EXAMPLE" || item.title.includes("💡") || item.title.includes("Ví dụ")
        ),
      ];
      const notes = [
        ...(concept.kind === "NOTE" ? [concept] : []),
        ...subItems.filter(
          (item) =>
            item.kind === "NOTE" ||
            item.title.includes("⚠️") ||
            item.title.includes("Bẫy") ||
            item.title.includes("Lưu ý") ||
            item.title.includes("Chú ý") ||
            item.title.includes("Nhận xét")
        ),
      ];

      topics.push({
        concept,
        formulas,
        methods,
        examples,
        notes,
      });
    }

    // Standalone items placed under this section (excluding grouping containers)
    const standalone = allSecNodes.filter(
      (n) =>
        !conceptNodes.some((c) => c.id === n.id) &&
        !processedIds.has(n.id) &&
        !/^[AB]\.\s+(?:LÝ THUYẾT|CÁC DẠNG)/i.test(n.title)
    );
    standalone.forEach((item) => processedIds.add(item.id));

    // Also mark intermediate grouping sections as processed so they don't leak into orphans
    allSecNodes
      .filter((n) => /^[AB]\.\s+(?:LÝ THUYẾT|CÁC DẠNG)/i.test(n.title))
      .forEach((item) => processedIds.add(item.id));

    sections.push({
      section: sec,
      topics,
      standaloneItems: standalone,
    });
  }

  // Capture any remaining unprocessed nodes so no knowledge is omitted
  const orphanNodes = nodes.filter((n) => !processedIds.has(n.id) && n.id !== rootId);
  if (orphanNodes.length > 0) {
    sections.push({
      section: {
        id: "extra_section",
        parent_id: rootId,
        kind: "SECTION",
        title: "Các kiến thức & Dạng toán bổ sung",
        body: "Các nội dung mở rộng được trích xuất từ tài liệu bài học.",
        latex: null,
        learning_steps: [],
        source_page: 1,
        source_quote: "",
        reviewed: true,
      },
      topics: orphanNodes.map((n) => ({
        concept: n,
        formulas: n.latex ? [n] : [],
        methods: n.learning_steps.length > 0 ? [n] : [],
        examples: n.kind === "EXAMPLE" ? [n] : [],
        notes: n.kind === "NOTE" ? [n] : [],
      })),
      standaloneItems: [],
    });
  }

  return { root, sections };
}
