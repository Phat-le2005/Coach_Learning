"""Audit all local question records; symbolic PASS has a deliberately narrow scope."""
from __future__ import annotations

from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import sympy as sp

from .quality import compare_transcriptions
from .safe_math import UnsupportedMath, assignment, derivative_check, equivalent
from .storage import file_hash, read_json, write_json, write_jsonl
from .step_segmentation import propose_steps, validate_grounding
from .native_math import candidates_for_step
from .fraction_layout import candidates_for_step as fraction_candidates
from .text_cleanup import overlap


def formula_groups(step):
    groups = []
    for candidate in step.get("latex_candidates", []):
        owner = next((g for g in groups if candidate["page_number"] == g[0]["page_number"]
                      and overlap(candidate["bbox"], g[0]["bbox"])), None)
        if owner is None:
            groups.append([candidate])
        else:
            owner.append(candidate)
    return groups


def audit_question(source: dict, proposal: dict, pages: dict | None = None) -> dict:
    steps, bases, derivatives, checks, flags = [], {}, [], [], []
    source_definitions = []
    if pages is not None and source.get('stem',{}).get('source_spans'):
        stem_source = {**source,'solution':source['stem']}
        stem_proposal = propose_steps(stem_source,pages,corrections=[])
        for step in stem_proposal['steps']:
            native,_ = candidates_for_step({**step,'kind_candidate':'MODEL_SETUP'},pages)
            fractions,_ = fraction_candidates({**step,'kind_candidate':'MODEL_SETUP'},pages)
            for candidate in native+fractions:
                try:
                    expression = assignment(candidate['latex'])
                except (UnsupportedMath,ValueError,TypeError,NotImplementedError):
                    continue
                if expression['derivative_order'] or not expression['chain_consistent']:
                    continue
                existing = [c for c in source_definitions if c.get('function_label')==expression['label']]
                if existing and not any(c['page_number']==candidate['page_number'] and overlap(c['bbox'],candidate['bbox']) for c in existing):
                    # Later equations may describe a symmetry line/tangent rather
                    # than redefine the function being studied in the question.
                    continue
                candidate['function_label'] = expression['label']
                source_definitions.append(candidate)
                bases.setdefault(expression['label'],[]).append({'expression':expression,'number':0,
                    'latex':candidate['latex'],'block_id':candidate['block_id'],'canonical_selected':False,
                    'page_number':candidate['page_number'],'bbox':candidate['bbox'],'source_part':'STEM',
                    'derivation_scope':candidate.get('derivation_scope','FULL_SOURCE_CHAIN')})
    for number, step in enumerate(proposal["steps"], 1):
        step = {**step, "latex_candidates": list(step.get("latex_candidates", []))}
        native_rejections = []
        if pages is not None:
            native, native_rejections = candidates_for_step(step, pages)
            step["latex_candidates"].extend(native)
            fractions, fraction_rejections = fraction_candidates(step,pages)
            step["latex_candidates"].extend(fractions)
            native_rejections.extend(fraction_rejections)
        output = {"step_id": step["step_id"], "number": number, "kind": step["kind_candidate"],
                  "title": step["title"], "text_candidate": step["text_candidate"],
                  "source_spans": step["source_spans"], "formula_groups": [], "flags": [],
                  "native_layout_rejections": native_rejections}
        if step["kind_candidate"] == "SIGN_TABLE":
            output["flags"].append("TABLE_IMAGE_RETAINED_NOT_STRUCTURED")
        for group in formula_groups(step):
            parsed, errors, conflicts = [], [], []
            for candidate in group:
                try:
                    parsed.append(assignment(candidate["latex"]))
                except (UnsupportedMath, ValueError, TypeError, NotImplementedError):
                    parsed.append(None)
                    errors.append("UNSUPPORTED_OR_AMBIGUOUS_MATH")
            for a, b in combinations(group, 2):
                conflicts.extend(compare_transcriptions(a["latex"], b["latex"])["flags"])
            valid = [p for p in parsed if p is not None]
            agreement = bool(valid) and len(valid) == len(group) and all(equivalent(valid[0], p) for p in valid[1:])
            if valid and not agreement:
                conflicts.append("OCR_FORMULA_ALTERNATIVES_UNRESOLVED")
            if any(not p["chain_consistent"] for p in valid):
                conflicts.append("SOURCE_EQUALITY_CHAIN_INCONSISTENT")
            selected = group[0]["latex"] if agreement and not conflicts else None
            formula = {"selected_latex": selected,
                       "selection_status": "PARSED_SOURCE_CANDIDATE_NOT_VISUALLY_VERIFIED" if selected else "UNRESOLVED",
                       "alternatives": group, "flags": sorted(set(errors + conflicts))}
            output["formula_groups"].append(formula)
            output["flags"].extend(formula["flags"])
            # Check each parseable OCR hypothesis, without declaring it canonical.
            # A PASS for one reading never resolves competing source readings.
            for candidate, expression in zip(group, parsed):
                if expression is None or not expression["chain_consistent"]:
                    continue
                entry = {"expression": expression, "number": number, "latex": candidate["latex"],
                         "block_id": candidate["block_id"], "canonical_selected": selected is not None,
                         "page_number": candidate["page_number"], "bbox": candidate["bbox"]}
                if candidate.get('derivation_scope'):
                    entry['derivation_scope'] = candidate['derivation_scope']
                entry['conditions_raw']=candidate.get('conditions_raw') or expression.get('conditions_raw','')
                if expression["derivative_order"] == 0:
                    # OCR can lose the prime in a derivative line. Such a reading
                    # is not a new base function for checking a later derivative.
                    lost_prime_alternative = (step["kind_candidate"] == "DERIVATIVE_CALCULATION" and
                        any(p["label"] == expression["label"] and p["derivative_order"] > 0 for p in valid))
                    if not lost_prime_alternative:
                        bases.setdefault(expression["label"], []).append(entry)
                elif step["kind_candidate"] != "ROOT_FINDING":
                    derivatives.append(entry)
        output["flags"] = sorted(set(output["flags"]))
        flags.extend(output["flags"])
        steps.append(output)
    for candidate in derivatives:
        derivative, number = candidate["expression"], candidate["number"]
        candidates = [b for b in bases.get(derivative["label"], []) if b["number"] <= number]
        if candidates:
            latest = max(b['number'] for b in candidates)
            candidates = [b for b in candidates if b['number']==latest]
        if candidates:
            for base in candidates[:6]:
                try:
                    check = derivative_check(base["expression"], derivative)
                    if (check['status']=='FAIL' and base['expression']['expression'].free_symbols
                            - derivative['expression'].free_symbols - {sp.Symbol(derivative['variable'] or base['expression']['variable'] or 'x')}):
                        check = {'status':'NOT_ASSESSED','reason':'SUBSTITUTION_OR_PARAMETER_ELIMINATION_REQUIRES_REVIEW'}
                except (UnsupportedMath, ValueError, TypeError, NotImplementedError):
                    check = {"status": "NOT_ASSESSED", "reason": "SYMBOLIC_CHECK_UNSUPPORTED"}
                checks.append({"step_number": number, "base_step_number": base["number"],
                    "base_candidate": {k: v for k, v in base.items() if k != "expression"},
                    "derivative_candidate": {k: v for k, v in candidate.items() if k != "expression"},
                    "evidence_scope": "OCR_HYPOTHESIS_IDENTITY_NOT_SOURCE_VERIFICATION", **check})
        else:
            checks.append({"step_number": number, "status": "NOT_ASSESSED", "reason": "NO_UNAMBIGUOUS_BASE_FORMULA"})
    if any(c["status"] == "FAIL" for c in checks):
        flags.append("DERIVATIVE_FORMULAS_DISAGREE")
    if not any(c["status"] in {"PASS", "FAIL"} for c in checks):
        flags.append("NO_SUPPORTED_MATHEMATICAL_CHECK")
    return {"schema_version": "local-math-audit/v1", "question_id": source["question_id"],
            "source_number": source["source_number"], "source_sha256": source["source_sha256"],
            "source_definitions":source_definitions,
            "steps": steps, "checks": checks, "flags": sorted(set(flags)),
            "answer_check": "NOT_ASSESSED_SOURCE_ANSWER_IS_NOT_A_PROOF",
            "academic_review": "PENDING", "grading_support": "NOT_ASSESSED", "publishable": False}


def run(pilot: Path, output: Path, *, pdf: Path) -> tuple[list[dict], dict]:
    manifest = read_json(pilot / "manifest.json")
    digest = file_hash(pdf)
    if digest != manifest["source_sha256"]:
        raise ValueError("REQUESTED_PDF_DIFFERS_FROM_PILOT_SOURCE")
    path = pilot / "questions.enriched.candidates.jsonl"
    sources = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    pages = {p["page_number"]: p for p in (read_json(path) for path in (pilot / "pages").glob("*.json"))}
    if len(pages) != manifest["page_count"] or any(p["source_sha256"] != digest for p in pages.values()):
        raise ValueError("PILOT_PAGES_DO_NOT_MATCH_REQUESTED_PDF")
    generation = file_hash(path)
    if len({s["question_id"] for s in sources}) != len(sources):
        raise ValueError("DUPLICATE_QUESTION_ID")
    audits = []
    for source in sources:
        if source["source_sha256"] != digest:
            raise ValueError("QUESTION_SOURCE_HASH_MISMATCH")
        # Rebuild from immutable extraction with NO saved editorial corrections.
        proposal = propose_steps(source, pages, corrections=[])
        validate_grounding(proposal, source, pages)
        audits.append(audit_question(source, proposal, pages))
    report = {"schema_version": "local-math-audit-report/v1", "source_sha256": digest,
        "source_path": str(pdf.resolve()), "page_count": manifest["page_count"], "question_count": len(audits),
        "proposed_step_count": sum(len(a["steps"]) for a in audits),
        "symbolic_check_counts": dict(Counter(c["status"] for a in audits for c in a["checks"])),
        "questions_with_supported_checks": sum(any(c["status"] in {"PASS", "FAIL"} for c in a["checks"]) for a in audits),
        "flag_counts": dict(Counter(f for a in audits for f in a["flags"])),
        "formula_group_count": sum(len(s["formula_groups"]) for a in audits for s in a["steps"]),
        "selected_formula_groups": sum(g["selected_latex"] is not None for a in audits for s in a["steps"] for g in s["formula_groups"]),
        "native_geometry_candidates": sum(c["parser_id"].startswith("native-baseline-math/") for a in audits for s in a["steps"] for g in s["formula_groups"] for c in g["alternatives"]),
        "native_fraction_candidates": sum(c["parser_id"].startswith("native-fraction-tree/") for a in audits for s in a["steps"] for g in s["formula_groups"] for c in g["alternatives"]),
        "stem_native_definitions":sum(len(a['source_definitions']) for a in audits),
        "candidate_generation": generation, "editorial_corrections_used": False,
        "algorithm_versions":{'baseline':'native-baseline-math/v1','fractions':'native-fraction-tree/v1','steps':'layout-reasoning/v2'},
        "source_image_verification": "NOT_AUTOMATICALLY_ESTABLISHED", "academic_approved_count": 0,
        "grading_ready_count": 0, "publishable_count": 0, "cloud_api_calls": 0}
    write_jsonl(output / "questions.math-audit.jsonl", audits)
    write_json(output / "questions.math-audit.pretty.json", audits)
    write_json(output / "math-report.json", report)
    return audits, report
