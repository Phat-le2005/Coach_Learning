import type { NotebookBlock, TheoryNode, TheoryNotebook } from "./api";

export function notebookHeadingKey(title: string): string {
  return (title.normalize("NFKC").toLocaleLowerCase("vi").match(/[\p{L}\p{N}]+/gu) ?? [])
    .map((part) => /^\d+$/.test(part) ? String(Number(part)) : part)
    .join(" ");
}

export interface NotebookPosition { sectionIndex: number; cardIndex: number }

export function findNotebookPosition(
  book: TheoryNotebook,
  target: { page?: number; blockId?: string; title?: string },
): NotebookPosition | null {
  const candidates: (NotebookPosition & { block: NotebookBlock })[] = [];
  book.sections.forEach((section, sectionIndex) => section.blocks.forEach((block, cardIndex) => {
    if (target.page === undefined || block.page === target.page) candidates.push({ sectionIndex, cardIndex, block });
  }));
  if (candidates.length === 0) return null;

  // 1. Heading match takes precedence: ordinals and blockIds can be stale across re-extractions.
  if (target.title) {
    const targetKey = notebookHeadingKey(target.title);
    const exact = candidates.filter(({ block }) => notebookHeadingKey(block.title) === targetKey);
    if (exact.length >= 1) return exact[0];

    // Substring / partial key match
    const partial = candidates.filter(({ block }) => {
      const bKey = notebookHeadingKey(block.title);
      return (bKey.length >= 4 && targetKey.includes(bKey)) || (targetKey.length >= 4 && bKey.includes(targetKey));
    });
    if (partial.length >= 1) {
      if (target.blockId) {
        const byId = partial.find(({ block }) => block.id === target.blockId);
        if (byId) return byId;
      }
      partial.sort((a, b) => {
        const aKey = notebookHeadingKey(a.block.title);
        const bKey = notebookHeadingKey(b.block.title);
        return bKey.length - aKey.length;
      });
      return partial[0];
    }

    // A missing heading must NEVER fall back to a stale blockId or first card!
    return null;
  }

  // 2. If no title provided, match by explicit blockId
  if (target.blockId) {
    const byId = candidates.find(({ block }) => block.id === target.blockId);
    if (byId) return byId;
  }

  return null;
}

export function resolveNotebookLesson(book: TheoryNotebook, node: TheoryNode): NotebookBlock[] {
  const position = findNotebookPosition(book, { page: node.source_page, title: node.title, blockId: node.block_id ?? undefined });
  if (!position) return [];
  const section = book.sections[position.sectionIndex];
  const selected = section.blocks[position.cardIndex];
  const rest = section.blocks.slice(position.cardIndex + 1);
  if (selected.kind === "METHOD" || /^a\s+lý thuyết/.test(notebookHeadingKey(selected.title))) {
    return [selected, ...rest];
  }
  const continuation: NotebookBlock[] = [];
  for (const block of rest) {
    if (block.kind !== "CONTINUATION" && !(selected.kind === "EXAMPLE" && block.kind === "STEP")) break;
    continuation.push(block);
  }
  return [selected, ...continuation];
}

/** Adjacent slices share a source boundary, so stack them without cutting a
 * fraction or superscript into separate cards. Never merge across a page gap. */
export function groupSourceRegions(blocks: NotebookBlock[]): NotebookBlock[][] {
  const regions: NotebookBlock[][] = [];
  for (const block of blocks) {
    const previous = regions.at(-1)?.at(-1);
    if (!previous || previous.page !== block.page || previous.ordinal + 1 !== block.ordinal) regions.push([]);
    regions[regions.length - 1].push(block);
  }
  return regions;
}
