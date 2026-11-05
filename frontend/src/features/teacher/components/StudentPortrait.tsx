import { avatarSeed } from "../classroom-model";
import { BAG_COLORS, type DeskStyle } from "../classroom-personalization";

export function StudentPortrait({ id, style }: { id: string; style: DeskStyle }) {
  const seed = avatarSeed(id);
  const skin = ["#f3c49d", "#ffd3ad", "#deac83", "#ffceac"][seed % 4];
  const hair = ["#45312d", "#593c32", "#302b35", "#694733"][Math.floor(seed / 3) % 4];
  return <svg viewBox="0 0 100 100" aria-hidden="true"><rect width="100" height="100" rx="28" fill="#f2eadd" /><path d="M22 100Q20 65 50 67Q80 65 78 100" fill={BAG_COLORS[style.bagColor].hex} /><ellipse cx="50" cy="45" rx="29" ry="31" fill={skin} /><ellipse cx="21" cy="49" rx="5" ry="7" fill={skin} /><ellipse cx="79" cy="49" rx="5" ry="7" fill={skin} /><path d="M21 42Q15 6 49 10Q86 8 80 43Q69 32 65 26Q43 44 21 36" fill={hair} />{seed % 3 === 1 && <><circle cx="25" cy="23" r="12" fill={hair} /><circle cx="76" cy="23" r="12" fill={hair} /></>}<ellipse cx="39" cy="48" rx="3" ry="4" fill="#3a2f32" /><ellipse cx="61" cy="48" rx="3" ry="4" fill="#3a2f32" /><ellipse cx="31" cy="58" rx="5" ry="2.5" fill="#eaa795" /><ellipse cx="69" cy="58" rx="5" ry="2.5" fill="#eaa795" /><path d="M44 60Q50 66 56 60" fill="none" stroke="#9a6451" strokeWidth="2" strokeLinecap="round" />{style.glasses && <g fill="none" stroke="#4a4b52" strokeWidth="2"><circle cx="38" cy="49" r="9" /><circle cx="62" cy="49" r="9" /><path d="M47 49H53M29 47L23 44M71 47L77 44" /></g>}<path d="M39 75L50 82L61 75" fill="none" stroke="#fff9ed" strokeWidth="6" strokeLinejoin="round" /></svg>;
}
