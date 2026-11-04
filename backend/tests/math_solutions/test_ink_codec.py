from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.math_ink.codec import encode_strokes, decode_strokes
from app.math_ink.schemas import InkPageWrite, InkPoint, InkStroke


def sample_stroke():
    return InkStroke(id=uuid4(), tool="PEN", color="#163d2c", width=2,
                     points=[InkPoint(x=0.1, y=0.2), InkPoint(x=0.2, y=0.3)])


def test_page_round_trip_and_deterministic_hash():
    stroke = sample_stroke()
    compressed, digest, count = encode_strokes([stroke])
    assert count == 2
    assert len(digest) == 64
    assert len(compressed) < 200
    assert decode_strokes(compressed) == [stroke]
    assert encode_strokes([stroke])[1] == digest


def test_duplicate_stroke_ids_rejected():
    stroke = sample_stroke()
    with pytest.raises(ValidationError):
        InkPageWrite(expected_document_revision=0, client_action_id=uuid4(),
                     strokes=[stroke, stroke])


def test_out_of_bounds_coordinates_rejected():
    with pytest.raises(ValidationError):
        InkPoint(x=-0.1, y=0.5)
    with pytest.raises(ValidationError):
        InkPoint(x=float("inf"), y=0.5)


def test_corrupt_stored_payload_is_rejected():
    from app.core.exceptions import ApplicationError
    with pytest.raises(ApplicationError):
        decode_strokes(b"not-zlib")


def test_dense_page_above_old_budget_round_trips_without_dropping_points():
    import json
    strokes = [InkStroke(id=uuid4(), tool="PEN", color="#163d2c", width=2,
                         points=[InkPoint(x=(i + 1) / 3001, y=(3000 - i) / 3001)
                                 for i in range(3000)]) for _ in range(2)]
    raw = json.dumps([s.model_dump(mode="json") for s in strokes],
                     separators=(",", ":"), sort_keys=True).encode()
    assert 256 * 1024 < len(raw) < 512 * 1024
    compressed, _, count = encode_strokes(strokes)
    assert count == 6000
    assert decode_strokes(compressed) == strokes


def test_encode_and_decompression_remain_bounded():
    import zlib
    from app.core.exceptions import ApplicationError
    from app.math_ink.codec import MAX_RAW_BYTES
    from app.math_ink.schemas import InkPoint
    large = sample_stroke()
    large.points = [InkPoint(x=0.123456789012345, y=0.987654321098765)] * 15000
    with pytest.raises(ApplicationError) as encoded:
        encode_strokes([large])
    assert encoded.value.code == "INK_PAGE_TOO_LARGE"
    with pytest.raises(ApplicationError) as decoded:
        decode_strokes(zlib.compress(b" " * (MAX_RAW_BYTES + 1)))
    assert decoded.value.code == "INK_PAGE_INVALID"
