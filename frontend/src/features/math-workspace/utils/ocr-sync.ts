/** Do not recognize stale server ink after an unsuccessful local save. */
export async function ensureLatestInkSaved(
  hasUnsavedInk: boolean,
  flushPage: () => Promise<boolean>,
): Promise<boolean> {
  if (!hasUnsavedInk) return true;
  return flushPage();
}
