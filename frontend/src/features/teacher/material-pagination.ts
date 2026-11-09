export function materialColumns(width: number): number {
  return width >= 1280 ? 4 : width >= 900 ? 3 : width >= 560 ? 2 : 1;
}

export function materialPage<T>(items: readonly T[], requestedPage: number, columns: number) {
  const size = Math.max(1, Math.min(4, Math.floor(columns))) * 2;
  const pageCount = Math.max(1, Math.ceil(items.length / size));
  const page = Math.max(0, Math.min(pageCount - 1, requestedPage));
  const start = page * size;
  return { items: items.slice(start, start + size), page, pageCount, start, end: Math.min(start + size, items.length) };
}

export function materialPageNumbers(current: number, count: number): (number | "gap")[] {
  const pages = Array.from({ length: count }, (_, index) => index)
    .filter(index => count <= 7 || index === 0 || index === count - 1 || Math.abs(index - current) <= 1);
  const result: (number | "gap")[] = [];
  for (const page of pages) {
    const previous = result[result.length - 1];
    if (typeof previous === "number" && page - previous > 1) result.push("gap");
    result.push(page);
  }
  return result;
}
