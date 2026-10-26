"use client";

import { KnowledgeForestTree, type KnowledgeForestTreeProps } from "./KnowledgeForestTree";

export interface KnowledgeWorldFallbackProps extends KnowledgeForestTreeProps {}

/**
 * 2D Fallback view for devices without WebGL support or when the user toggles 2D mode.
 */
export function KnowledgeWorldFallback(props: KnowledgeWorldFallbackProps) {
  return <KnowledgeForestTree {...props} />;
}
