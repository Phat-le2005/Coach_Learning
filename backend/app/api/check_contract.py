import difflib
import json
import sys
from pathlib import Path

from app.api.export_contract import (
    OPENAPI_JSON_PATH,
    OPENAPI_SHA256_PATH,
    compute_compact_sha256,
    get_deterministic_schema,
)


def check_contract() -> int:
    if not OPENAPI_JSON_PATH.exists():
        print(f"Error: Contract file not found at {OPENAPI_JSON_PATH}", file=sys.stderr)
        return 1

    if not OPENAPI_SHA256_PATH.exists():
        print(f"Error: SHA-256 file not found at {OPENAPI_SHA256_PATH}", file=sys.stderr)
        return 1

    current_schema = get_deterministic_schema()
    current_serialized = (
        json.dumps(
            current_schema,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )
    current_digest = compute_compact_sha256(current_schema)

    expected_serialized = OPENAPI_JSON_PATH.read_text(encoding="utf-8")
    expected_digest = OPENAPI_SHA256_PATH.read_text(encoding="utf-8").strip()

    has_error = False

    if current_serialized != expected_serialized:
        has_error = True
        print("Contract schema mismatch detected:", file=sys.stderr)
        diff = list(
            difflib.unified_diff(
                expected_serialized.splitlines(keepends=True),
                current_serialized.splitlines(keepends=True),
                fromfile=str(OPENAPI_JSON_PATH),
                tofile="current_openapi",
                n=3,
            )
        )
        # Limit output if diff is very large
        max_diff_lines = 50
        for line in diff[:max_diff_lines]:
            sys.stderr.write(line)
        if len(diff) > max_diff_lines:
            print(f"... and {len(diff) - max_diff_lines} more lines ...", file=sys.stderr)

    if current_digest != expected_digest:
        has_error = True
        print(
            f"Contract SHA-256 mismatch!\nExpected: {expected_digest}\nActual:   {current_digest}",
            file=sys.stderr,
        )

    if has_error:
        print("\nRun `python -m app.api.export_contract` to re-freeze contract if intentional.", file=sys.stderr)
        return 1

    print("API v1 contract verification PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(check_contract())
