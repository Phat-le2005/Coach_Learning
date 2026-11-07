"""Real persistence and authenticated WebSocket protocol (no mocked transport)."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.core.exceptions import ApplicationError
from app.math_ink.live import LiveOperation, apply_operation
from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ink.service import MathInkService
from app.users.models import User
from tests.math_solutions.test_ink_postgres_concurrency import _create_attempt, PASSWORD


def stroke():
    return InkStroke(id=uuid4(), tool="PEN", color="#112233", width=2,
        points=[InkPoint(x=.2, y=.3), InkPoint(x=.4, y=.5)])


def op(revision=0, add=None, remove=None):
    return LiveOperation(client_action_id=uuid4(), expected_document_revision=revision,
        add=add or [], remove=remove or [])


def test_duplicate_and_fixed_intent_rebase_preserve_both_devices(db_session):
    owner, attempt = _create_attempt(db_session)
    a, b = stroke(), stroke()
    first, second = op(add=[a]), op(add=[b])
    assert apply_operation(db_session, owner, attempt, 0, first).document_revision == 1
    assert apply_operation(db_session, owner, attempt, 0, first).document_revision == 1
    with pytest.raises(ApplicationError, match="Resync"):
        apply_operation(db_session, owner, attempt, 0, second)
    second.expected_document_revision = 1
    result = apply_operation(db_session, owner, attempt, 0, second)
    assert {s.id for s in result.strokes} == {a.id, b.id}
    # Duplicate delivery after another commit returns the CURRENT canonical page.
    assert len(apply_operation(db_session, owner, attempt, 0, first).strokes) == 2
    # A clear intent based on a visible page cannot delete a subsequently added ID.
    clear = op(2, remove=[a, b])
    c = stroke()
    apply_operation(db_session, owner, attempt, 0, op(2, add=[c]))
    with pytest.raises(ApplicationError):
        apply_operation(db_session, owner, attempt, 0, clear)
    clear.expected_document_revision = 3
    assert apply_operation(db_session, owner, attempt, 0, clear).strokes == [c]


def test_ownership_locked_attempt_and_conflicting_stroke_rejected(db_session):
    owner, attempt = _create_attempt(db_session)
    outsider, _ = _create_attempt(db_session)
    original = stroke()
    committed = op(add=[original])
    apply_operation(db_session, owner, attempt, 0, committed)
    with pytest.raises(ApplicationError) as denied:
        apply_operation(db_session, outsider, attempt, 0, op(1, add=[stroke()]))
    assert denied.value.status_code == 404
    modified = original.model_copy(update={"width": 5})
    with pytest.raises(ApplicationError) as conflict:
        apply_operation(db_session, owner, attempt, 0, op(1, remove=[modified]))
    assert conflict.value.code == "INK_STROKE_CONFLICT"
    assert MathInkService(db_session).get_page(owner, attempt, 0).strokes == [original]
    instance = MathInkService(db_session)._attempt(owner, attempt)
    instance.status = "SUBMITTED"
    db_session.commit()
    # A lost ACK can still be recovered after lock; no new write is performed.
    assert apply_operation(db_session, owner, attempt, 0, committed).strokes == [original]
    with pytest.raises(ApplicationError) as locked:
        apply_operation(db_session, owner, attempt, 0, op(1, add=[stroke()]))
    assert locked.value.code == "INK_LOCKED"


def test_live_auth_origin_ticket_scope_and_single_use(db_session, db_client, settings):
    owner, attempt = _create_attempt(db_session)
    other, other_attempt = _create_attempt(db_session)
    email = db_session.get(User, owner).email
    token = AuthService(db_session, settings).login(LoginRequest(email=email, password=PASSWORD)).access_token
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v2/math-solutions/attempts/{attempt}/ink"
    assert db_client.post(f"{url}/live-ticket", json={"page_index": 0, "origin": settings.frontend_origin}).status_code == 401
    assert db_client.post(f"/api/v2/math-solutions/attempts/{other_attempt}/ink/live-ticket", headers=headers,
        json={"page_index": 0, "origin": settings.frontend_origin}).status_code == 404
    assert db_client.post(f"{url}/live-ticket", headers=headers,
        json={"page_index": 0, "origin": "https://evil.invalid"}).status_code == 403
    with pytest.raises(WebSocketDisconnect):
        with db_client.websocket_connect(f"{url}/live", headers={"origin": "https://evil.invalid"}):
            pass
    with db_client.websocket_connect(f"{url}/live", headers={"origin": settings.frontend_origin}) as ws:
        ws.send_json({"ticket": "invalid"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    ticket = db_client.post(f"{url}/live-ticket", headers=headers,
        json={"page_index": 0, "origin": settings.frontend_origin}).json()["ticket"]
    with db_client.websocket_connect(f"{url}/live", headers={"origin": settings.frontend_origin}) as ws:
        ws.send_json({"ticket": ticket})
        assert ws.receive_json()["type"] == "PAGE_SNAPSHOT"
        ws.receive_json()  # presence
        with db_client.websocket_connect(f"{url}/live", headers={"origin": settings.frontend_origin}) as replay:
            replay.send_json({"ticket": ticket})
            with pytest.raises(WebSocketDisconnect):
                replay.receive_json()


def test_stream_before_commit_and_reconnect_canonical_snapshot(db_session, db_client, settings):
    owner, attempt = _create_attempt(db_session)
    token = AuthService(db_session, settings).login(LoginRequest(email=db_session.get(User, owner).email, password=PASSWORD)).access_token
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v2/math-solutions/attempts/{attempt}/ink"
    def grant():
        return db_client.post(f"{url}/live-ticket", headers=headers,
            json={"page_index": 0, "origin": settings.frontend_origin}).json()["ticket"]
    a, b = grant(), grant()
    with db_client.websocket_connect(f"{url}/live", headers={"origin": settings.frontend_origin}) as desktop:
        desktop.send_json({"ticket": a}); desktop.receive_json(); desktop.receive_json()
        with db_client.websocket_connect(f"{url}/live", headers={"origin": settings.frontend_origin}) as mobile:
            mobile.send_json({"ticket": b}); mobile.receive_json(); mobile.receive_json(); desktop.receive_json()
            ink = stroke()
            mobile.send_json({"type": "STROKE_BEGIN", "seq": 1, "stroke": ink.model_dump(mode="json")})
            assert desktop.receive_json()["stroke"]["id"] == str(ink.id)
            for sequence in [2, 1, 2, 3]:
                mobile.send_json({"type": "STROKE_POINTS", "seq": sequence, "stroke": ink.model_dump(mode="json")})
            assert desktop.receive_json()["seq"] == 2
            assert desktop.receive_json()["seq"] == 3  # Duplicates/out-of-order frames were discarded.
            assert db_client.get(f"{url}/pages/0", headers=headers).json()["strokes"] == []
            operation = op(add=[ink]).model_dump(mode="json")
            saved = db_client.post(f"{url}/pages/0/operations", headers=headers, json=operation)
            assert saved.status_code == 200
            assert desktop.receive_json()["type"] == "STROKE_COMMITTED"
    with db_client.websocket_connect(f"{url}/live", headers={"origin": settings.frontend_origin}) as reconnect:
        reconnect.send_json({"ticket": grant()})
        assert len(reconnect.receive_json()["strokes"]) == 1


def test_real_postgres_two_simultaneous_devices(postgres_engine):
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    with factory() as db:
        owner, attempt = _create_attempt(db)
    barrier = Barrier(2)
    a, b = stroke(), stroke()
    def append(ink):
        intent = op(add=[ink])
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                return apply_operation(db, owner, attempt, 0, intent)
            except ApplicationError as error:
                assert error.code == "INK_REVISION_CONFLICT"
                intent.expected_document_revision = MathInkService(db).get_page(owner, attempt, 0).document_revision
                return apply_operation(db, owner, attempt, 0, intent)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(append, [a, b]))
    with factory() as db:
        result = MathInkService(db).get_page(owner, attempt, 0)
        assert result.document_revision == 2
        assert {s.id for s in result.strokes} == {a.id, b.id}
