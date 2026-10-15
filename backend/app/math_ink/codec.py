"""Size-limited JSON encoding for one page; never unpickle untrusted bytes."""
import hashlib
import json
import zlib
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkStroke

MAX_RAW_BYTES = 256 * 1024
MAX_COMPRESSED_BYTES = 160 * 1024


def encode_strokes(strokes: list[InkStroke]) -> tuple[bytes, str, int]:
    raw = json.dumps(
        [stroke.model_dump(mode="json") for stroke in strokes],
        ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False,
    ).encode("utf-8")
    if len(raw) > MAX_RAW_BYTES:
        raise ApplicationError(413, "INK_PAGE_TOO_LARGE", "Ink page exceeds its storage budget.")
    compressed = zlib.compress(raw, level=6)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise ApplicationError(413, "INK_PAGE_TOO_LARGE", "Ink page exceeds its compressed storage budget.")
    return compressed, hashlib.sha256(raw).hexdigest(), sum(len(s.points) for s in strokes)


def decode_strokes(blob: bytes) -> list[InkStroke]:
    # Cap decompression even if the database blob becomes corrupted.
    obj = zlib.decompressobj()
    try:
        raw = obj.decompress(blob, MAX_RAW_BYTES + 1)
    except zlib.error as exc:
        raise ApplicationError(409, "INK_PAGE_INVALID", "Stored ink page is not valid.") from exc
    if len(raw) > MAX_RAW_BYTES or obj.unconsumed_tail or not obj.eof:
        raise ApplicationError(409, "INK_PAGE_INVALID", "Stored ink page is not valid.")
    try:
        values = json.loads(raw.decode("utf-8"))
        if not isinstance(values, list):
            raise ValueError("Not a page")
        return [InkStroke.model_validate(item) for item in values]
    except (ValueError, TypeError) as exc:
        raise ApplicationError(409, "INK_PAGE_INVALID", "Stored ink page is not valid.") from exc
