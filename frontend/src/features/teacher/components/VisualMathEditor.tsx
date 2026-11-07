"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { MathfieldElement } from "mathlive";
import katex from "katex";
import { ArrowLeft, ArrowRight, CornerDownRight, Delete, Sigma, Undo2, Redo2, X } from "lucide-react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import { splitMathText, type MathTextPart } from "../math-text";
import { MATH_SYMBOL_GROUPS, QUICK_MATH_KEYS, searchMathSymbols, type MathSymbol } from "../math-symbols";
import "mathlive/fonts.css";
import styles from "./VisualMathEditor.module.css";

type FormulaPart = Extract<MathTextPart, { kind: "math" }>;

function formulaElement(part: FormulaPart): HTMLSpanElement {
  const element = document.createElement("span");
  element.contentEditable = "false";
  element.tabIndex = 0;
  element.setAttribute("role", "button");
  element.setAttribute("aria-label", "Sửa công thức toán");
  element.dataset.mathToken = part.raw;
  element.dataset.latex = part.latex;
  element.dataset.open = part.open;
  element.dataset.close = part.close;
  element.className = `${styles.formula} ${part.display ? styles.displayFormula : ""}`;
  try {
    element.innerHTML = katex.renderToString(part.latex, { displayMode: part.display, throwOnError: true, strict: "ignore", trust: false, maxExpand: 100, maxSize: 20 });
  } catch { element.textContent = "Công thức cần kiểm tra — bấm để sửa"; }
  return element;
}

function renderValue(element: HTMLElement, value: string) {
  const fragment = document.createDocumentFragment();
  for (const part of splitMathText(value)) fragment.append(part.kind === "text" ? document.createTextNode(part.raw) : formulaElement(part));
  element.replaceChildren(fragment);
}

function serializeValue(element: HTMLElement): string {
  function read(parent: Node): string {
    let result = "";
    for (const node of Array.from(parent.childNodes)) {
      if (node.nodeType === Node.TEXT_NODE) { result += node.textContent ?? ""; continue; }
      if (!(node instanceof HTMLElement)) continue;
      if (node.dataset.mathToken !== undefined) { result += node.dataset.mathToken; continue; }
      if (node.tagName === "BR") { result += "\n"; continue; }
      const block = node.tagName === "DIV" || node.tagName === "P";
      // Browsers represent the empty line after Enter as <div><br></div>.
      // The BR is a caret placeholder, not a second newline.
      const emptyLine = block && node.childNodes.length === 1 && node.firstChild instanceof HTMLBRElement;
      if (block && node.previousSibling && (!result.endsWith("\n") || emptyLine)) result += "\n";
      if (!emptyLine) result += read(node);
      if (block && node.nextSibling && !result.endsWith("\n")) result += "\n";
    }
    return result;
  }
  if (element.childNodes.length === 1 && element.firstChild instanceof HTMLBRElement) return "";
  return read(element);
}

/** Editable prose with atomic, clickable formulas. Parent updates never reset an IME/caret. */
export function VisualMathEditor({ id, label, value, disabled = false, maxLength, onChange }: {
  id: string; label: string; value: string; disabled?: boolean; maxLength: number; onChange: (value: string) => void;
}) {
  const editor = useRef<HTMLDivElement>(null);
  const lastValue = useRef<string | null>(null);
  const selection = useRef<Range | null>(null);
  const composing = useRef(false);
  const [activeFormula, setActiveFormula] = useState<{ node: HTMLElement | null; latex: string } | null>(null);
  const [error, setError] = useState("");

  useLayoutEffect(() => {
    if (!editor.current || composing.current || value === lastValue.current) return;
    renderValue(editor.current, value);
    lastValue.current = value;
  }, [value]);

  function rememberSelection() {
    const selected = window.getSelection();
    if (!editor.current || !selected?.rangeCount || !editor.current.contains(selected.getRangeAt(0).commonAncestorContainer)) return;
    const range = selected.getRangeAt(0).cloneRange();
    const tokenAt = (node: Node) => (node instanceof Element ? node : node.parentElement)?.closest<HTMLElement>("[data-math-token]");
    const start = tokenAt(range.startContainer), end = tokenAt(range.endContainer);
    if (range.collapsed && start) { range.setStartAfter(start); range.collapse(true); }
    else { if (start) range.setStartBefore(start); if (end) range.setEndAfter(end); }
    selection.current = range;
  }

  function emit() {
    if (!editor.current || composing.current) return;
    const next = serializeValue(editor.current);
    if (next.length > maxLength) {
      renderValue(editor.current, lastValue.current ?? value);
      setError("Nội dung quá dài. Hãy rút gọn phần vừa nhập.");
      return;
    }
    lastValue.current = next;
    setError("");
    onChange(next);
    rememberSelection();
  }

  function openFormula(node: HTMLElement | null = null) {
    if (disabled) return;
    rememberSelection();
    setActiveFormula({ node, latex: node?.dataset.latex ?? "" });
  }

  function restoreSelection() {
    const root = editor.current;
    if (!root) return null;
    root.focus();
    const range = selection.current?.commonAncestorContainer.isConnected && root.contains(selection.current.commonAncestorContainer)
      ? selection.current.cloneRange() : document.createRange();
    if (!selection.current?.commonAncestorContainer.isConnected || !root.contains(range.commonAncestorContainer)) { range.selectNodeContents(root); range.collapse(false); }
    const selected = window.getSelection(); selected?.removeAllRanges(); selected?.addRange(range);
    return range;
  }

  function applyFormula(latex: string) {
    const root = editor.current;
    if (!root || !activeFormula) return;
    const old = activeFormula.node;
    const open = old?.dataset.open ?? "$";
    const close = old?.dataset.close ?? "$";
    const raw = open + latex + close;
    const selectedContent = document.createElement("div");
    if (selection.current) selectedContent.append(selection.current.cloneContents());
    const projected = serializeValue(root).length - (old?.dataset.mathToken?.length ?? serializeValue(selectedContent).length) + raw.length;
    if (projected > maxLength) return "Công thức làm nội dung vượt giới hạn độ dài.";
    const token = formulaElement({ kind: "math", raw, latex, open, close, display: open === "$$" || open === "\\[" });
    if (old?.isConnected && root.contains(old)) old.replaceWith(token);
    else {
      const range = restoreSelection();
      if (!range) return;
      range.deleteContents(); range.insertNode(token);
    }
    const range = document.createRange(); range.setStartAfter(token); range.collapse(true);
    emit();
    selection.current = range;
    setActiveFormula(null);
    requestAnimationFrame(restoreSelection);
  }

  return <div className={styles.field}>
    <div className={styles.fieldHeader}>
      <span id={`${id}-label`} className={styles.label}>{label}</span>
      <button type="button" className={styles.insertButton} disabled={disabled} onMouseDown={(e) => e.preventDefault()} onClick={() => openFormula()}>
        <Sigma size={15} aria-hidden="true" /> Chèn công thức
      </button>
    </div>
    <div id={id} ref={editor} className={styles.prose} contentEditable={!disabled} suppressContentEditableWarning
      role="textbox" aria-labelledby={`${id}-label`} aria-multiline="true" aria-disabled={disabled} tabIndex={disabled ? -1 : 0}
      data-testid={`visual-editor-${id}`} onInput={emit} onSelect={rememberSelection} onMouseUp={rememberSelection} onKeyUp={rememberSelection} onBlur={rememberSelection}
      onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; emit(); }}
      onPaste={(event) => { event.preventDefault(); document.execCommand("insertText", false, event.clipboardData.getData("text/plain")); emit(); }}
      onClick={(event) => { const node = (event.target as Element).closest<HTMLElement>("[data-math-token]"); if (node && editor.current?.contains(node)) openFormula(node); }}
      onKeyDown={(event) => {
        if ((event.key === "Enter" || event.key === " ") && event.target instanceof HTMLElement && event.target.dataset.mathToken !== undefined) { event.preventDefault(); openFormula(event.target); }
      }} />
    <p className={styles.help}>Gõ chữ như bình thường. Bấm vào công thức để sửa bằng bảng ký hiệu.</p>
    {error && <p className={styles.error} role="alert">{error}</p>}
    {activeFormula && <FormulaDialog initialValue={activeFormula.latex} editing={!!activeFormula.node} onApply={applyFormula}
      onCancel={() => { setActiveFormula(null); requestAnimationFrame(restoreSelection); }} />}
  </div>;
}

function FormulaDialog({ initialValue, editing, onApply, onCancel }: {
  initialValue: string; editing: boolean; onApply: (latex: string) => string | void; onCancel: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const mathfield = useRef<MathfieldElement | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [latex, setLatex] = useState(initialValue);
  const [group, setGroup] = useState("common");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let active = true;
    dialog.current?.showModal();
    void import("mathlive").then(({ MathfieldElement: Field }) => {
      if (!active || !host.current) return;
      // Fonts are bundled by Next via the CSS import. No CDN, model or cloud service.
      Field.fontsDirectory = null; Field.soundsDirectory = null; Field.computeEngine = null;
      const field = new Field();
      field.mathVirtualKeyboardPolicy = "manual";
      field.smartFence = true;
      field.setAttribute("aria-label", "Soạn công thức trực quan");
      field.setAttribute("data-testid", "teacher-mathfield");
      field.addEventListener("input", () => { setLatex(field.getValue("latex")); setError(""); });
      mathfield.current = field;
      host.current.replaceChildren(field);
      field.setValue(initialValue, { silenceNotifications: true });
      setReady(true);
      field.focus();
    }).catch(() => { if (active) setError("Chưa tải được bảng công thức. Hãy đóng và mở lại."); });
    return () => { active = false; mathfield.current?.remove(); mathfield.current = null; };
  }, [initialValue]);

  function insert(symbol: MathSymbol) {
    const field = mathfield.current;
    if (!field) return;
    field.focus();
    field.insert(symbol.insert, { format: "latex", selectionMode: symbol.insert.includes("#") ? "placeholder" : "after", focus: true, feedback: false });
    setLatex(field.getValue("latex")); setError("");
  }
  function command(name: "moveToPreviousChar" | "moveToNextChar" | "moveToNextPlaceholder" | "deleteBackward" | "undo" | "redo") {
    const field = mathfield.current; if (!field) return;
    field.focus(); field.executeCommand(name); setLatex(field.getValue("latex"));
  }
  function apply() {
    const field = mathfield.current;
    if (!field) return;
    const value = field.getValue("latex");
    if (!value.trim()) { setError("Hãy nhập hoặc chọn ký hiệu để tạo công thức."); return; }
    if (field.errors.length || /\\placeholder\b/.test(value)) { setError("Hãy điền đủ các ô trống và kiểm tra lại công thức trước khi chèn."); return; }
    try { katex.renderToString(value, { throwOnError: true, strict: "ignore", trust: false, maxExpand: 100, maxSize: 20 }); }
    catch { setError("Công thức có ký hiệu chưa hiển thị được. Hãy kiểm tra hoặc chọn lại mẫu tương ứng."); return; }
    const problem = onApply(value);
    if (problem) setError(problem);
  }
  const symbols = searchMathSymbols(query, group);
  return <dialog ref={dialog} className={styles.dialog} aria-labelledby="formula-dialog-title" onCancel={(e) => { e.preventDefault(); onCancel(); }}>
    <div className={styles.dialogHeader}>
      <h3 id="formula-dialog-title">{editing ? "Chỉnh sửa công thức" : "Chèn công thức toán"}</h3>
      <button type="button" aria-label="Đóng bảng công thức" onClick={onCancel}><X size={18} aria-hidden="true" /></button>
    </div>
    <div className={styles.dialogBody}>
      <p className={styles.help}>Chọn ký hiệu hoặc mẫu, rồi bấm vào ô trống để điền số/chữ. Không cần nhập mã công thức.</p>
      {!ready && !error && <p role="status">Đang mở bàn phím toán…</p>}
      <div ref={host} className={styles.mathfieldHost} />
      <div className={styles.navigation} role="group" aria-label="Di chuyển và sửa công thức">
        <button type="button" aria-label="Sang trái" onMouseDown={(e) => e.preventDefault()} onClick={() => command("moveToPreviousChar")}><ArrowLeft size={16} aria-hidden="true" /></button>
        <button type="button" aria-label="Sang phải" onMouseDown={(e) => e.preventDefault()} onClick={() => command("moveToNextChar")}><ArrowRight size={16} aria-hidden="true" /></button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => command("moveToNextPlaceholder")}><CornerDownRight size={15} aria-hidden="true" /> Ô tiếp</button>
        <button type="button" aria-label="Xóa ký hiệu trước" onMouseDown={(e) => e.preventDefault()} onClick={() => command("deleteBackward")}><Delete size={16} aria-hidden="true" /></button>
        <button type="button" aria-label="Hoàn tác công thức" onMouseDown={(e) => e.preventDefault()} onClick={() => command("undo")}><Undo2 size={16} aria-hidden="true" /></button>
        <button type="button" aria-label="Làm lại công thức" onMouseDown={(e) => e.preventDefault()} onClick={() => command("redo")}><Redo2 size={16} aria-hidden="true" /></button>
      </div>
      <div className={styles.quickKeys} role="group" aria-label="Nhập số và biến">
        {QUICK_MATH_KEYS.map((key) => <button key={key.id} type="button" aria-label={`Nhập ${key.label}`} disabled={!ready} onMouseDown={(e) => e.preventDefault()} onClick={() => insert(key)}>{key.label}</button>)}
      </div>
      <label className={styles.search}>Tìm ký hiệu
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ví dụ: căn, tích phân, lambda, sigma…" />
      </label>
      <div className={styles.groups} role="group" aria-label="Nhóm ký hiệu toán">
        {MATH_SYMBOL_GROUPS.map((g) => <button key={g.id} type="button" aria-pressed={!query && group === g.id} onClick={() => { setGroup(g.id); setQuery(""); }}>{g.label}</button>)}
      </div>
      <div className={styles.symbols} role="group" aria-label="Bảng ký hiệu toán">
        {symbols.map((symbol) => <button key={symbol.id} type="button" aria-label={symbol.label} title={symbol.label} disabled={!ready}
          onMouseDown={(e) => e.preventDefault()} onClick={() => insert(symbol)}><MathRenderer content={`$${symbol.latex}$`} inline /><span>{symbol.label}</span></button>)}
      </div>
      {!symbols.length && <p role="status">Chưa tìm thấy ký hiệu. Hãy thử tên khác hoặc chọn nhóm bên trên.</p>}
      <details className={styles.advanced}><summary>Mã công thức (tùy chọn)</summary>
        <textarea aria-label="Mã LaTeX của công thức" value={latex} onChange={(e) => { setLatex(e.target.value); mathfield.current?.setValue(e.target.value, { silenceNotifications: true }); }} />
      </details>
      {error && <p className={styles.error} role="alert">{error}</p>}
    </div>
    <div className={styles.dialogFooter}>
      <button type="button" onClick={onCancel}>Hủy</button>
      <button type="button" className={styles.apply} disabled={!ready || !latex.trim()} onClick={apply}>{editing ? "Cập nhật công thức" : "Chèn vào nội dung"}</button>
    </div>
  </dialog>;
}
