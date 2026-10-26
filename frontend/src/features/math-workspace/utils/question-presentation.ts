/** Detect text-layer extraction that cannot safely represent a maths question. */
export function hasBrokenMathExtraction(text: string): boolean {
  if (/[\uE000-\uF8FF]/u.test(text)) return true;
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.length < 10) return false;
  const fragments = lines.filter((line) => line.length <= 3).length;
  return fragments >= 6 && fragments * 2 >= lines.length;
}

export function problemNeedsSourceReview(content: string, options: readonly { content: string }[]): boolean {
  return hasBrokenMathExtraction(content) || options.some((option) => hasBrokenMathExtraction(option.content));
}
