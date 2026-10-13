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
