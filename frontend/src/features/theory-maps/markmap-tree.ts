import type { TheoryNode } from "./api";

export interface SafeMapNode {
  content: string;
  payload: { nodeId: string };
  children: SafeMapNode[];
}

export function escapeMapText(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character] ?? character);
}

/** Convert LaTeX symbols into clean, universally readable Unicode math for mind map branch labels. */
export function latexToReadable(latex: string): string {
  if (!latex) return "";
  let s = latex.trim();
  s = s.replace(/\\Delta(?:')?/g, "Δ'");
  s = s.replace(/\\ge/g, "≥");
  s = s.replace(/\\le/g, "≤");
  s = s.replace(/\\neq/g, "≠");
  s = s.replace(/\\pm/g, "±");
  s = s.replace(/\\cdot/g, "·");
  s = s.replace(/\\times/g, "×");
  s = s.replace(/\\iff/g, "⟺");
  s = s.replace(/\\implies/g, "⟹");
  s = s.replace(/\\forall/g, "∀");
  s = s.replace(/\\exists/g, "∃");
  s = s.replace(/\\in/g, "∈");
  s = s.replace(/\\notin/g, "∉");
  s = s.replace(/\\infty/g, "∞");
  s = s.replace(/\\mathbb\{R\}/g, "ℝ");
  s = s.replace(/\\quad/g, " ");
  s = s.replace(/\\qquad/g, " ");
  s = s.replace(/\\text\{([^}]+)\}/g, "$1");
  s = s.replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, "($1)/($2)");
  s = s.replace(/\\sqrt\{([^}]+)\}/g, "√($1)");
  s = s.replace(/\^2/g, "²");
  s = s.replace(/\^3/g, "³");
  s = s.replace(/\^4/g, "⁴");
  s = s.replace(/_0/g, "₀");
  s = s.replace(/_1/g, "₁");
  s = s.replace(/_2/g, "₂");
  s = s.replace(/_i/g, "ᵢ");
  s = s.replace(/\\max(?:_[A-Za-z0-9_{}]+)?/g, "max");
  s = s.replace(/\\min(?:_[A-Za-z0-9_{}]+)?/g, "min");
  s = s.replace(/\\lim(?:_[A-Za-z0-9_{}]+)?/g, "lim");
  s = s.replace(/\\begin\{cases\}|\\end\{cases\}/g, "");
  s = s.replace(/\\\\/g, "; ");
  s = s.replace(/[{}]/g, "");
  s = s.replace(/\s+/g, " ").trim();
  return s;
}

function formatNodeLabel(node: TheoryNode): string {
  let title = node.title.trim();
  const readable = node.latex ? latexToReadable(node.latex) : "";

  if (node.kind === "FORMULA") {
    const prefix = title.startsWith("📐") ? "" : "📐 ";
    if (readable && !title.includes(readable)) {
      return `${prefix}${escapeMapText(title)}: <strong>${escapeMapText(readable)}</strong>`;
    }
    return `${prefix}${escapeMapText(title)}`;
  }

  if (node.kind === "EXAMPLE") {
    const prefix = title.startsWith("💡") ? "" : "💡 ";
    return `${prefix}${escapeMapText(title)}`;
  }

  if (node.kind === "NOTE") {
    const prefix = title.startsWith("⚠️") ? "" : "⚠️ ";
    return `${prefix}${escapeMapText(title)}`;
  }

  // If node has latex formula but is not named formula, display concise formula if title is short
  if (readable && !title.includes(readable) && title.length < 50 && (node.kind === "CONCEPT" || node.kind === "SECTION")) {
    return `${escapeMapText(title)} (<strong>${escapeMapText(readable)}</strong>)`;
  }

  return escapeMapText(title);
}

/** Keep the root and one real branch, without pulling in its siblings. */
export function scopeTheoryNodes(nodes: TheoryNode[], scopeId: string): TheoryNode[] {
  const root = nodes.find((node) => node.parent_id === null);
  if (!root || scopeId === root.id || !nodes.some((node) => node.id === scopeId)) return nodes;
  const included = new Set([scopeId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const node of nodes) {
      if (node.parent_id && included.has(node.parent_id) && !included.has(node.id)) {
        included.add(node.id);
        changed = true;
      }
    }
  }
  included.add(root.id);
  return nodes.filter((node) => included.has(node.id));
}

/** Converts TheoryNode hierarchy into Markmap tree with visible formulas and concrete steps. */
export function toMarkmapTree(nodes: TheoryNode[]): SafeMapNode | null {
  const root = nodes.find((node) => node.parent_id === null);
  if (!root) return null;
  const visited = new Set<string>();

  const build = (node: TheoryNode, depth: number): SafeMapNode => {
    visited.add(node.id);
    const realChildren = depth >= 20 ? [] : nodes.filter((child) => child.parent_id === node.id && !visited.has(child.id))
      .map((child) => build(child, depth + 1));

    // If node is a leaf with no children, expand its concrete pedagogical content directly onto the tree!
    let virtualChildren: SafeMapNode[] = [];
    if (realChildren.length === 0) {
      // 1. If it has a LaTeX formula and node itself is not a FORMULA card, show formula child branch
      if (node.latex && node.kind !== "FORMULA") {
        const readable = latexToReadable(node.latex);
        if (readable) {
          virtualChildren.push({
            content: `📐 Công thức: <strong>${escapeMapText(readable)}</strong>`,
            payload: { nodeId: node.id },
            children: [],
          });
        }
      }

      // 2. If it has step-by-step methods, branch out the concrete steps!
      if (node.learning_steps.length > 0) {
        for (const step of node.learning_steps) {
          const stepFormula = step.latex ? ` (<strong>${escapeMapText(latexToReadable(step.latex))}</strong>)` : "";
          virtualChildren.push({
            content: `📝 ${escapeMapText(step.instruction)}${stepFormula}`,
            payload: { nodeId: node.id },
            children: [],
          });
        }
      }

      // 3. If it is an example with body, show sample problem / solution branch
      if (node.kind === "EXAMPLE" && node.body.trim()) {
        const lines = node.body.split("\n").filter((l) => l.trim());
        const summary = lines[0]?.slice(0, 95) ?? "";
        if (summary) {
          virtualChildren.push({
            content: `✍️ ${escapeMapText(summary)}...`,
            payload: { nodeId: node.id },
            children: [],
          });
        }
      }
    }

    return {
      content: formatNodeLabel(node),
      payload: { nodeId: node.id },
      children: realChildren.length > 0 ? realChildren : virtualChildren,
    };
  };

  return build(root, 0);
}
