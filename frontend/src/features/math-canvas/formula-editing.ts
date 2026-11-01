export function insertMathSnippet(source: string, start: number, end: number, prefix: string, suffix: string, placeholder: string) {
  start = Math.max(0, Math.min(source.length, start));
  end = Math.max(start, Math.min(source.length, end));
  const selection = source.slice(start, end);
  const selected = prefix === "pi" ? "" : selection || placeholder;
  if (suffix === "^2" && selection) { prefix = "("; suffix = ")^2"; }
  const text = source.slice(0, start) + prefix + selected + suffix + source.slice(end);
  if (text.length > 500) return null;
  const inside = start + prefix.length;
  const replacePlaceholder = !selection && !!placeholder;
  return { text, selectionStart: replacePlaceholder ? inside : inside + selected.length + suffix.length,
    selectionEnd: replacePlaceholder ? inside + selected.length : inside + selected.length + suffix.length };
}
