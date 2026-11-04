"""Review existing local metadata with original source crops, one question per job."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import time

from PIL import Image

from .gemini_client import DEFAULT_ENV, GeminiClient, GeminiConfig, GeminiError, content_hash
from .gemini_contracts import REVIEW_PROMPT, REVIEW_SCHEMA, validate_question_package
from .gemini_jobs import execute_job, writer_lock
from .local_client import create_client, resolve_provider
from .storage import file_hash, read_json, write_json, write_jsonl
from .text_cleanup import normalize_block


def prepare_question(pilot: Path, source: dict, proposal: dict | None, output: Path) -> dict:
    manifest = read_json(pilot / "manifest.json")
    if source["source_sha256"] != manifest["source_sha256"]:
        raise ValueError("SOURCE_HASH_MISMATCH")
    refs, native = [], []
    for part in ("stem", "answer", "solution"):
        for i, span in enumerate(source[part]["source_spans"], 1):
            page = read_json(pilot / "pages" / f"page-{span['page_number']:03}.json")
            if page["source_sha256"] != manifest["source_sha256"]:
                raise ValueError("PAGE_HASH_MISMATCH")
            image = pilot / page["image_path"]
            if not image.resolve().is_relative_to(pilot.resolve()):
                raise ValueError("SOURCE_IMAGE_OUTSIDE_PILOT")
            box = span["bbox"]
            if not 0 <= box[0] < box[2] <= page["width"] or not 0 <= box[1] < box[3] <= page["height"]:
                raise ValueError("SOURCE_CROP_OUTSIDE_PAGE")
            crop_id = content_hash({"page_image": file_hash(image), "bbox": box})
            target = output / "assets" / f"{crop_id}.png"
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(image) as img:
                    sx, sy = img.width / page["width"], img.height / page["height"]
                    img.crop((int(box[0]*sx), int(box[1]*sy), round(box[2]*sx), round(box[3]*sy))).save(target)
            identifier = f"{part}:p{span['page_number']}:{i}"
            refs.append({"evidence_id": identifier, "page_number": span["page_number"], "part": part,
                         "bbox_pdf_points": box, "asset_path": str(target.relative_to(output)).replace("\\", "/"), "sha256": file_hash(target)})
            ids = set(span["block_ids"])
            native.append({"evidence_id": identifier, "text_lossy": "\n".join(normalize_block(b)[0] for b in page["blocks"] if b["block_id"] in ids)})
    if not {"stem", "solution"}.issubset({r["part"] for r in refs}):
        raise ValueError("QUESTION_MISSING_STEM_OR_SOLUTION_SOURCE")
    curation_path = pilot / "curation.json"
    curation = read_json(curation_path) if curation_path.exists() else {}
    prior_issues = next((i.get("issues", []) for i in curation.get("items", []) if i["number"] == source["source_number"]), []) if curation.get("source_sha256") == source["source_sha256"] else []
    return {"schema_version": "gemini-question-package/v1", "question_id": source["question_id"],
            "source_number": source["source_number"], "source_sha256": source["source_sha256"],
            "local_source_candidate": {"native_lossy": native, "source_answer_raw": source["answer"]["text_raw"]},
            "local_step_proposals": [{k: s[k] for k in ("kind_candidate", "text_candidate", "latex_candidates", "conditions_candidate")}
                                     for s in (proposal or {}).get("steps", [])],
            "prior_source_issues": prior_issues, "references": refs}


def run(pilot: Path, *, env_file=DEFAULT_ENV, model=None, numbers=None, limit=3, max_calls=5,
        max_total_tokens=100_000, retry_failed=False, preflight_only=False, provider=None,
        local_url=None, max_output_tokens=8192) -> dict:
    provider = resolve_provider(provider, env_file)
    output = pilot / ("local-review" if provider == "local" else "gemini")
    client = create_client(provider, env_file, model, output / "usage.jsonl", local_url=local_url,
        max_calls=max_calls, max_total_tokens=max_total_tokens, max_output_tokens=max_output_tokens)
    try:
        with writer_lock(output):
            preflight = client.preflight(output / "preflight.json")
            if preflight_only:
                return preflight
            candidates = pilot / "questions.enriched.candidates.jsonl"
            sources = [json.loads(line) for line in candidates.read_text(encoding="utf-8").splitlines() if line.strip()]
            proposal_file = pilot / "steps" / "questions.steps.jsonl"
            proposals = {r["question_id"]: r for r in (json.loads(line) for line in proposal_file.read_text(encoding="utf-8").splitlines())} if proposal_file.exists() else {}
            generation = file_hash(candidates)
            proposals = {k: v for k, v in proposals.items() if v.get("candidate_generation") == generation}
            selected = [s for s in sources if numbers is None or s["source_number"] in numbers][:limit]
            if not selected or (numbers and set(numbers) - {s["source_number"] for s in sources}):
                raise ValueError("REQUESTED_QUESTION_NOT_FOUND")
            records, cache_hits, failures = [], 0, []
            started = time.perf_counter()
            for source in selected:
                package = prepare_question(pilot, source, proposals.get(source["question_id"]), output)
                try:
                    record, cached = execute_job(client, output, package, REVIEW_SCHEMA, REVIEW_PROMPT,
                        lambda result: validate_question_package(result, package), retry_failed=retry_failed)
                except GeminiError as error:
                    failures.append({"question_id": source["question_id"], "error_code": str(error)})
                    break
                cache_hits += int(cached)
                if record["status"] == "COMPLETE":
                    records.append(record)
                else:
                    failures.append({"question_id": source["question_id"], **record})
                print(f"{provider} q{source['source_number']}: {record.get('ai_review_status',record['status'])}{' (cache)' if cached else ''}", flush=True)
            # Export only this selected run, while immutable jobs retain every older run.
            write_jsonl(output / "questions.reviewed.jsonl", records)
            write_json(output / "questions.reviewed.pretty.json", records)
            queue = [{"question_id": r["source_package"]["question_id"], "job_key": r["job_key"],
                      "reasons": r["local_flags"], "issues": r["result"]["issues"]} for r in records if r["local_flags"]] + failures
            write_json(output / "review-queue.json", queue)
            report = {"schema_version": "gemini-review-report/v1", "model": client.config.model,
                "provider": provider, "cloud_api_attempts_this_run": client.calls if provider == "gemini" else 0,
                "requested_count": len(selected), "completed_count": len(records), "failed_count": len(failures),
                "cache_hits": cache_hits, "api_attempts_this_run": client.calls, "tokens_this_run": client.tokens,
                "seconds": round(time.perf_counter()-started, 3),
                "status_counts": dict(Counter(r["ai_review_status"] for r in records)),
                "academic_approved_count": 0, "grading_ready_count": 0, "publishable_count": 0}
            write_json(output / "report.json", report)
            write_json(output / "runs" / f"{client.run_id}.json", report)
            from .gemini_view import build_view
            build_view(output, records, report)
            return report
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--model")
    parser.add_argument("--provider", choices=["local", "gemini"])
    parser.add_argument("--local-url")
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--questions", help="Comma-separated source numbers; unique question IDs remain the actual keys")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-calls", type=int, default=5)
    parser.add_argument("--max-total-tokens", type=int, default=100_000)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 10_000 or not 1 <= args.max_calls <= 10_000:
        parser.error("Use explicit positive item/call limits up to 10000")
    try:
        report = run(args.pilot, env_file=args.env_file, model=args.model,
            numbers={int(n) for n in re.split(r"[,\s]+", args.questions.strip())} if args.questions else None,
            limit=args.limit, max_calls=args.max_calls, max_total_tokens=args.max_total_tokens,
            retry_failed=args.retry_failed, preflight_only=args.preflight, provider=args.provider,
            local_url=args.local_url, max_output_tokens=args.max_output_tokens)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report.get("failed_count") or report.get("completed_count", 0) < report.get("requested_count", 0):
            raise SystemExit(2)
    except (GeminiError, ValueError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
