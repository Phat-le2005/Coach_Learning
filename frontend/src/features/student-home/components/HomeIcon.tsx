import type { CSSProperties } from "react";
import glyphs from "./home-icons.json";

/** Published Phosphor duotone paths; see assets/PHOSPHOR-LICENSE.txt. */
export function HomeIcon({ name, size = 22, style }: {
  name: keyof typeof glyphs; size?: number; style?: CSSProperties;
}) {
  return <svg aria-hidden="true" viewBox="0 0 256 256" width={size} height={size}
    fill="currentColor" style={{ flexShrink: 0, ...style }}
    dangerouslySetInnerHTML={{ __html: glyphs[name] }} />;
}
