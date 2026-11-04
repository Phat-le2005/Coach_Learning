"""Plan and resume PDF/ZIP corpus extraction through bounded Gemini page windows.

Planning is local-only. Running requires an explicit call limit and sends just
selected window images, not the archive or an entire large PDF, to Gemini.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import time
import zipfile

import pypdfium2 as pdfium
from jsonschema import Draft202012Validator

from .gemini_client import DEFAULT_ENV, GeminiClient, GeminiConfig, GeminiError, content_hash
from .gemini_contracts import STAGING_SCHEMA, WINDOW_PROMPT, WINDOW_SCHEMA, filter_context_units, validate_window
from .gemini_jobs import execute_job, writer_lock
from .local_client import create_client, resolve_provider
from .storage import file_hash, read_json, write_json, write_jsonl


def make_windows(page_count: int, core_size: int = 2, overlap: int = 1) -> list[dict]:
    if page_count < 1 or not 1 <= core_size <= 6 or not 0 <= overlap <= 3:
        raise ValueError("INVALID_WINDOW_PARAMETERS")
    return [{"core_pages": list(range(first, min(page_count + 1, first + core_size))),
             "context_pages": list(range(max(1, first - overlap), min(page_count, first + core_size - 1 + overlap) + 1))}
            for first in range(1, page_count + 1, core_size)]


def inventory(input_path: Path, output: Path) -> list[dict]:
    input_path = input_path.resolve()
    materialized = []
    if input_path.is_dir():
        materialized = [(str(p.relative_to(input_path)), p) for p in sorted(input_path.rglob("*.pdf"))
                        if not p.resolve().is_relative_to(output.resolve())]
    elif input_path.suffix.lower() == ".pdf":
        materialized = [(input_path.name, input_path)]
    elif input_path.suffix.lower() == ".zip":
        # Write by content hash only; archive paths are metadata, never extraction destinations.
        with zipfile.ZipFile(input_path) as archive:
            entries = [i for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith(".pdf")]
            for info in entries:
                if info.file_size > 600_000_000 or info.file_size / max(1, info.compress_size) > 1500:
                    raise ValueError("ARCHIVE_ENTRY_EXCEEDS_SAFETY_LIMIT")
                digest = hashlib.sha256()
                pending = output / "sources" / "extract.pending"
                pending.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, pending.open("wb") as dst:
                    for chunk in iter(lambda: src.read(1024 * 1024), b""):
                        digest.update(chunk)
                        dst.write(chunk)
                target = pending.with_name(digest.hexdigest() + ".pdf")
                if target.exists():
                    if file_hash(target) != digest.hexdigest():
                        raise ValueError("MATERIALIZED_SOURCE_HASH_MISMATCH")
                    pending.unlink()
                else:
                    pending.replace(target)
                materialized.append((info.filename, target.resolve()))
    else:
        raise ValueError("INPUT_MUST_BE_PDF_DIRECTORY_OR_ZIP")
    documents, seen = [], set()
    for label, path in materialized:
        digest = file_hash(path)
        if digest in seen:
            continue
        seen.add(digest)
        with pdfium.PdfDocument(str(path)) as pdf:
            count = len(pdf)
        if count < 1:
            raise ValueError("EMPTY_PDF")
        documents.append({"document_id": digest[:16], "label": label, "path": str(path.resolve()),
                          "sha256": digest, "bytes": path.stat().st_size, "page_count": count})
    if not documents:
        raise ValueError("NO_PDF_SOURCES_FOUND")
    return documents


def plan(input_path: Path, output: Path, *, core_size=2, overlap=1) -> dict:
    output = output.resolve()
    with writer_lock(output):
        documents = inventory(input_path, output)
        jobs = []
        for doc in documents:
            for window in make_windows(doc["page_count"], core_size, overlap):
                jobs.append({"job_id": f"{doc['document_id']}:p{window['core_pages'][0]:04d}",
                             "document_id": doc["document_id"], **window})
        result = {"schema_version": "pdf-corpus-plan/v1", "input_path": str(input_path.resolve()),
                  "core_size": core_size, "overlap": overlap, "documents": documents, "jobs": jobs,
                  "document_count": len(documents), "page_count": sum(d["page_count"] for d in documents),
                  "window_count": len(jobs), "api_calls": 0}
        write_json(output / "plan.json", result)
        return {k: result[k] for k in ("schema_version", "document_count", "page_count", "window_count", "api_calls")}


def render_window(doc: dict, window: dict, output: Path, *, dpi=160) -> dict:
    references, native = [], []
    page_root = output / "pages" / doc["document_id"]
    page_root.mkdir(parents=True, exist_ok=True)
    with pdfium.PdfDocument(doc["path"]) as pdf:
        for number in window["context_pages"]:
            image_path = page_root / f"page-{number:04d}-{dpi}dpi.png"
            text_path = image_path.with_suffix(".json")
            if image_path.exists() and text_path.exists():
                metadata = read_json(text_path)
                if metadata.get("source_sha256") != doc["sha256"] or metadata.get("image_sha256") != file_hash(image_path):
                    raise ValueError("PAGE_CACHE_INVALID")
            else:
                page = pdf[number - 1]
                try:
                    text_page = page.get_textpage()
                    try:
                        text = text_page.get_text_range()
                    finally:
                        text_page.close()
                    width, height = page.get_size()
                    bitmap = page.render(scale=dpi / 72)
                    try:
                        bitmap.to_pil().save(image_path)
                    finally:
                        bitmap.close()
                    metadata = {"source_sha256": doc["sha256"], "page_number": number, "native_text_lossy": text,
                                "width": width, "height": height, "dpi": dpi, "image_sha256": file_hash(image_path),
                                "native_route": "IMAGE_ONLY" if not text.strip() else "NATIVE_WITH_VISUAL_CHECK"}
                    write_json(text_path, metadata)
                finally:
                    page.close()
            evidence_id = f"page:{number}"
            references.append({"evidence_id": evidence_id, "page_number": number, "part": "full_page",
                "asset_path": image_path.relative_to(output).as_posix(), "sha256": metadata["image_sha256"]})
            native.append({"evidence_id": evidence_id, "text_lossy": metadata["native_text_lossy"][:25_000],
                           "native_text_truncated": len(metadata["native_text_lossy"]) > 25_000,
                           "native_route": metadata["native_route"]})
    return {"schema_version": "gemini-window-package/v1", "document_id": doc["document_id"],
            "document_label": doc["label"], "source_sha256": doc["sha256"], "core_pages": window["core_pages"],
            "context_pages": window["context_pages"], "native_text_candidates": native, "references": references}


def export_staging(output: Path, document_lookup: dict[str, dict], active_keys: set[str]) -> dict:
    records, units, queue, failures = [], [], [], []
    for state_path in sorted((output / "jobs").glob("*/state.json")):
        state = read_json(state_path)
        if state.get("job_key") not in active_keys:
            continue
        result_path = state_path.with_name("result.json")
        if state.get("status") != "COMPLETE" or not result_path.exists():
            failures.append(state)
            continue
        record = read_json(result_path)
        package = record["source_package"]
        if package.get("document_id") not in document_lookup:
            continue
        records.append(record)
        for index, unit in enumerate(record["result"]["units"], 1):
            unit_id = f"{package['document_id']}:p{unit['start_page']:04d}:{record['job_key'][:8]}:u{index}"
            refs = [r for r in package["references"] if r["evidence_id"] in unit["evidence_ids"]]
            structural_flags = []
            if not unit["complete"] or unit["continues_after_window"] or unit["continuation_from_previous"]:
                structural_flags.append("INCOMPLETE_BOUNDARY")
            if unit["kind"] == "QUESTION" and not unit["source_answer"].strip():
                structural_flags.append("MISSING_SOURCE_ANSWER")
            if unit["kind"] == "QUESTION" and not unit["source_number"].strip():
                structural_flags.append("MISSING_SOURCE_QUESTION_NUMBER")
            if unit["kind"] == "QUESTION" and not unit["steps"]:
                structural_flags.append("NO_SOURCE_SOLUTION_STEPS")
            if any(s["basis"] != "VISIBLE_SOURCE" or s["uncertain"] or any(c["basis"] != "VISIBLE_SOURCE" for c in s["conditions"]) for s in unit["steps"]):
                structural_flags.append("UNCERTAIN_OR_ADDED_STEPS")
            if unit["question_type"] in {"MULTIPLE_CHOICE", "TRUE_FALSE"}:
                structural_flags.append("OPTIONS_AND_ANSWER_LEAKAGE_REVIEW")
            if any(i["severity"] in {"WARNING", "ERROR"} for i in unit["issues"]):
                structural_flags.append("MODEL_REPORTED_ISSUES")
            if record["local_flags"] or record["result"]["window_issues"]:
                structural_flags.append("WINDOW_REVIEW_REQUIRED")
            staging = {"schema_version": "math-content-staging/v1", "unit_id": unit_id, "job_key": record["job_key"],
                "document_id": package["document_id"], "source_sha256": package["source_sha256"], "source_references": refs,
                "content": unit, "review_flags": structural_flags,
                "ai_review_status": "AI_FLAGGED" if structural_flags else "AI_REVIEWED",
                "academic_review": "PENDING", "grading_support": "NOT_ASSESSED", "publishable": False}
            units.append(staging)
            if structural_flags:
                queue.append({"unit_id": unit_id, "reasons": structural_flags, "issues": unit["issues"]})
    # Do not silently merge repeated numbered questions or similar math expressions.
    fingerprints = Counter(content_hash({"kind": u["content"]["kind"], "content": u["content"]["content_markdown"],
                                        "options": u["content"]["options"]}) for u in units)
    for unit in units:
        fingerprint = content_hash({"kind": unit["content"]["kind"], "content": unit["content"]["content_markdown"], "options": unit["content"]["options"]})
        unit["content_fingerprint"] = fingerprint
        if fingerprints[fingerprint] > 1:
            unit["review_flags"].append("POSSIBLE_DUPLICATE_CONTENT")
            unit["ai_review_status"] = "AI_FLAGGED"
            queue.append({"unit_id": unit["unit_id"], "reasons": ["POSSIBLE_DUPLICATE_CONTENT"]})
    validator = Draft202012Validator(STAGING_SCHEMA)
    for unit in units:
        validator.validate(unit)
    write_jsonl(output / "staging" / "content.jsonl", units)
    write_json(output / "staging" / "content.pretty.json", units)
    write_json(output / "staging" / "review-queue.json", queue + failures)
    write_json(output / "windows.reviewed.pretty.json", records)
    return {"records": records, "unit_count": len(units), "question_count": sum(u["content"]["kind"] == "QUESTION" for u in units),
            "knowledge_count": sum(u["content"]["kind"] == "KNOWLEDGE" for u in units),
            "unit_status_counts": dict(Counter(u["ai_review_status"] for u in units)), "pending_job_count": len(failures)}


def run(output: Path, *, env_file=DEFAULT_ENV, model=None, limit=1, max_calls=3, max_total_tokens=100_000,
        documents=None, job_ids=None, sample_per_document=False, retry_failed=False, revalidate=False,
        max_output_tokens=8192, request_interval=0, provider=None, local_url=None) -> dict:
    output = output.resolve()
    plan_data = read_json(output / "plan.json")
    lookup = {d["document_id"]: d for d in plan_data["documents"]}
    if documents and set(documents) - lookup.keys():
        raise ValueError("DOCUMENT_ID_NOT_FOUND_IN_PLAN")
    for doc in lookup.values():
        if file_hash(Path(doc["path"])) != doc["sha256"]:
            raise ValueError("SOURCE_CHANGED_REPLAN_REQUIRED")
    jobs = [j for j in plan_data["jobs"] if not documents or j["document_id"] in documents]
    if job_ids:
        if set(job_ids) - {j["job_id"] for j in jobs}:
            raise ValueError("JOB_ID_NOT_FOUND_IN_PLAN")
        jobs = [j for j in jobs if j["job_id"] in job_ids]
    if sample_per_document:
        grouped = [[j for j in jobs if j["document_id"] == d] for d in lookup]
        jobs = [group[i] for i in range(max(map(len, grouped), default=0)) for group in grouped if len(group) > i]
    provider = resolve_provider(provider, env_file)
    if provider == "local":
        client = create_client(provider, env_file, model, output / "usage.jsonl", local_url=local_url,
            max_calls=max_calls, max_total_tokens=max_total_tokens, max_output_tokens=max_output_tokens)
    else:
        client = GeminiClient(GeminiConfig.load(env_file, model, max_calls=max_calls, max_total_tokens=max_total_tokens,
                                              max_output_tokens=max_output_tokens), output / "usage.jsonl")
    started = time.perf_counter()
    try:
        with writer_lock(output):
            client.preflight(output / "preflight.json")
            generation = content_hash({"plan_jobs": plan_data["jobs"], "model": client.config.model,
                "schema": WINDOW_SCHEMA, "prompt": WINDOW_PROMPT, "max_output_tokens": client.config.max_output_tokens,
                "adapter": "generateContent-portable-schema/v2"})
            index_path = output / "active-jobs.json"
            job_index = read_json(index_path) if index_path.exists() else {}
            if job_index.get("generation") != generation:
                job_index = {"generation": generation, "jobs": {}}
            processed, hits, failures, completed = 0, 0, [], []
            # Scan cached jobs as needed so repeated bounded runs make forward progress.
            for job in jobs:
                if processed >= limit:
                    break
                package = render_window(lookup[job["document_id"]], job, output)
                try:
                    record, cached = execute_job(client, output, package, WINDOW_SCHEMA, WINDOW_PROMPT,
                        lambda result: validate_window(result, package["references"], package["core_pages"]), retry_failed=retry_failed,
                        revalidate=revalidate, normalizer=lambda result: filter_context_units(result, package["references"], package["core_pages"]))
                except GeminiError as error:
                    failures.append({"job_id": job["job_id"], "error_code": str(error)})
                    break
                hits += int(cached)
                job_index["jobs"][job["job_id"]] = {"job_key": record["job_key"], "status": record["status"]}
                write_json(index_path, job_index)
                if not cached:
                    processed += 1
                if record["status"] != "COMPLETE":
                    failures.append({"job_id": job["job_id"], **record})
                else:
                    completed.append({"job_id": job["job_id"], "job_key": record["job_key"], "cached": cached})
                print(f"Corpus {job['job_id']}: {record.get('ai_review_status',record['status'])}{' (cache)' if cached else ''}", flush=True)
                if not cached and request_interval and processed < limit:
                    time.sleep(min(55, request_interval))
            exported = export_staging(output, lookup, {j["job_key"] for j in job_index["jobs"].values()})
            report = {"schema_version": "pdf-corpus-run/v1", "model": client.config.model,
                      "provider": provider, "cloud_api_attempts_this_run": client.calls if provider == "gemini" else 0,
                      "planned_documents": len(lookup), "planned_pages": plan_data["page_count"],
                      "planned_windows": len(plan_data["jobs"]), "completed_windows_in_export": len(exported["records"]),
                      "processed_core_pages": sum(len(r["source_package"]["core_pages"]) for r in exported["records"]),
                      "source_image_pages": len({(r["source_package"]["document_id"], ref["page_number"]) for r in exported["records"] for ref in r["source_package"]["references"]}),
                      "excluded_context_units": sum(len(r.get("normalization_audit", [])) for r in exported["records"]),
                      "new_jobs_this_run": processed, "cache_hits_this_run": hits,
                      "api_attempts_this_run": client.calls, "tokens_this_run": client.tokens,
                      "unit_count": exported["unit_count"], "question_count": exported["question_count"],
                      "knowledge_count": exported["knowledge_count"], "unit_status_counts": exported["unit_status_counts"],
                      "failures_this_run": failures, "seconds": round(time.perf_counter()-started, 3),
                      "academic_approved_count": 0, "grading_ready_count": 0, "publishable_count": 0}
            write_json(output / "report.json", report)
            write_json(output / "runs" / f"{client.run_id}.json", report)
            from .gemini_view import build_view
            build_view(output, exported["records"], report)
            return report
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("plan")
    create.add_argument("--input", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--core-pages", type=int, default=2)
    create.add_argument("--overlap", type=int, default=1)
    execute = sub.add_parser("run")
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    execute.add_argument("--model")
    execute.add_argument("--provider", choices=["local", "gemini"])
    execute.add_argument("--local-url")
    execute.add_argument("--limit", type=int, default=1)
    execute.add_argument("--max-calls", type=int, default=3)
    execute.add_argument("--max-total-tokens", type=int, default=100_000)
    execute.add_argument("--max-output-tokens", type=int, default=8192)
    execute.add_argument("--request-interval", type=float, default=0)
    execute.add_argument("--documents", help="Comma-separated document IDs from plan.json")
    execute.add_argument("--jobs", help="Comma-separated job IDs from plan.json for representative tests")
    execute.add_argument("--sample-per-document", action="store_true")
    execute.add_argument("--retry-failed", action="store_true")
    execute.add_argument("--revalidate", action="store_true", help="Revalidate saved raw responses locally, without re-requesting inference")
    args = parser.parse_args()
    try:
        if args.action == "plan":
            report = plan(args.input, args.output, core_size=args.core_pages, overlap=args.overlap)
        else:
            if not 1 <= args.limit <= 10_000 or not 1 <= args.max_calls <= 10_000:
                parser.error("Use explicit positive item/call limits up to 10000")
            if not 1024 <= args.max_output_tokens <= 65536 or not 0 <= args.request_interval <= 55:
                parser.error("Output tokens must be 1024..65536 and request interval 0..55 seconds")
            report = run(args.output, env_file=args.env_file, model=args.model, limit=args.limit, max_calls=args.max_calls,
                max_total_tokens=args.max_total_tokens, documents=set(args.documents.split(",")) if args.documents else None,
                job_ids=set(args.jobs.split(",")) if args.jobs else None,
                revalidate=args.revalidate,
                max_output_tokens=args.max_output_tokens, request_interval=args.request_interval,
                provider=args.provider, local_url=args.local_url,
                sample_per_document=args.sample_per_document, retry_failed=args.retry_failed)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report.get("failures_this_run"):
            raise SystemExit(2)
    except (GeminiError, ValueError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
