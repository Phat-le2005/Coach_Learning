import difflib
import json
import sys

from app.api.export_contract import compute_compact_sha256
from app.api.v2.export_contract import (
    OPENAPI_V2_JSON_PATH,
    OPENAPI_V2_SHA256_PATH,
    get_v2_deterministic_schema,
)


def check_v2_contract() -> int:
    if not OPENAPI_V2_JSON_PATH.exists() or not OPENAPI_V2_SHA256_PATH.exists():
        print("API v2 contract snapshot is missing.", file=sys.stderr)
        return 1

    schema = get_v2_deterministic_schema()
    current = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    digest = compute_compact_sha256(schema)
    expected = OPENAPI_V2_JSON_PATH.read_text(encoding="utf-8")
    expected_digest = OPENAPI_V2_SHA256_PATH.read_text(encoding="utf-8").strip()
    failed = False
    if current != expected:
        failed = True
        print("API v2 contract schema mismatch detected:", file=sys.stderr)
        diff = list(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                current.splitlines(keepends=True),
                fromfile=str(OPENAPI_V2_JSON_PATH),
                tofile="current_openapi_v2",
                n=3,
            )
        )
        for line in diff[:50]:
            sys.stderr.write(line)
    if digest != expected_digest:
        failed = True
        print(
            f"API v2 contract SHA-256 mismatch!\nExpected: {expected_digest}\nActual:   {digest}",
            file=sys.stderr,
        )
    if failed:
        return 1
    print("API v2 contract verification PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(check_v2_contract())