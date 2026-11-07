from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
import time

import pytest
from app.auth.models import AuthSession
from app.auth.schemas import LoginRequest
from app.auth.security import utc_now
from app.auth.service import AuthService
from app.core.exceptions import ApplicationError
from app.math_ink.pairing import PairingStore
from app.math_ink.schemas import InkStroke, InkPoint
from app.users.models import User
from tests.math_solutions.test_ink_postgres_concurrency import _create_attempt, PASSWORD


def owner(db, settings):
    user, attempt = _create_attempt(db)
    auth = AuthService(db, settings)
    token = auth.login(LoginRequest(email=db.get(User, user).email, password=PASSWORD)).access_token
    return user, attempt, token


def test_qr_requires_owner_approval_then_only_grants_ink_and_can_be_revoked(db_session, db_client, settings):
    _, attempt, token = owner(db_session, settings)
    base = f"/api/v2/math-solutions/attempts/{attempt}/ink/pairings"
    auth = {"Authorization": "Bearer " + token}
    assert db_client.post(base, json={"page_index": 0, "origin": settings.frontend_origin}).status_code == 401
    invite = db_client.post(base, headers=auth, json={"page_index": 0, "origin": settings.frontend_origin}).json()
    claim = db_client.post("/api/v2/math-ink-device/claim", json={"code": invite["code"], "origin": settings.frontend_origin, "device_name": "iPad"})
    assert claim.status_code == 200
    grant = claim.json()
    device = {"X-Ink-Device": grant["device_token"], "Origin": settings.frontend_origin}
    assert grant["status"] == "PENDING"
    assert db_client.get("/api/v2/math-ink-device/ink/pages/0", headers=device).status_code == 403
    assert db_client.post("/api/v2/math-ink-device/claim", json={"code": invite["code"], "origin": settings.frontend_origin}).status_code == 410
    assert "device_token" not in db_client.get(base + "/" + invite["id"], headers=auth).json()
    _, _, outsider = owner(db_session, settings)
    assert db_client.post(base + "/" + invite["id"] + "/approve", headers={"Authorization": "Bearer " + outsider}).status_code == 404
    assert db_client.post(base + "/" + invite["id"] + "/approve", headers=auth).json()["status"] == "ACTIVE"
    assert db_client.get("/api/v2/math-ink-device/ink/pages/0", headers=device).status_code == 200
    # Delegation is NOT a full student login, even after desktop approval.
    assert db_client.get(f"/api/v2/math-solutions/attempts/{attempt}", headers=device).status_code == 401
    assert db_client.get("/auth/me", headers=device).status_code == 401
    assert db_client.get("/api/v2/math-ink-device/ink/pages/0", headers={**device, "Origin": "https://evil.invalid"}).status_code == 403
    ink = InkStroke(id=uuid4(), tool="PEN", color="#233c30", width=2, points=[InkPoint(x=.2, y=.3)])
    operation = {"client_action_id": str(uuid4()), "expected_document_revision": 0, "add": [ink.model_dump(mode="json")], "remove": []}
    saved = db_client.post("/api/v2/math-ink-device/ink/pages/0/operations", headers=device, json=operation)
    assert saved.status_code == 200 and saved.json()["strokes"][0]["id"] == str(ink.id)
    db_client.post(base + "/" + invite["id"] + "/revoke", headers=auth)
    assert db_client.get("/api/v2/math-ink-device/ink/pages/0", headers=device).status_code == 401
    assert db_client.post("/api/v2/math-ink-device/ink/pages/0/operations", headers=device, json=operation).status_code == 401


def test_parent_logout_invalidates_approved_writing_device(db_session, db_client, settings):
    _, attempt, token = owner(db_session, settings)
    auth = {"Authorization": "Bearer " + token}
    base = f"/api/v2/math-solutions/attempts/{attempt}/ink/pairings"
    invite = db_client.post(base, headers=auth, json={"page_index": 0, "origin": settings.frontend_origin}).json()
    grant = db_client.post("/api/v2/math-ink-device/claim", json={"code": invite["code"], "origin": settings.frontend_origin}).json()
    db_client.post(base + "/" + invite["id"] + "/approve", headers=auth)
    claims = AuthService(db_session, settings).tokens.decode_access_token(token)
    parent = db_session.get(AuthSession, claims.sid)
    parent.revoked_at = utc_now()
    db_session.commit()
    assert db_client.get("/api/v2/math-ink-device/session", headers={"X-Ink-Device": grant["device_token"]}).status_code == 401


def test_invitation_expires_and_concurrent_claim_is_single_use():
    store = PairingStore()
    actor, attempt, sid = uuid4(), uuid4(), uuid4()
    item, code = store.create(actor, attempt, 0, "http://localhost:3000", sid)
    def claim():
        try:
            store.claim(code, item.origin, "Phone")
            return "claimed"
        except ApplicationError:
            return "rejected"
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(lambda _: claim(), range(2))) == ["claimed", "rejected"]
    expired, old_code = store.create(actor, attempt, 0, item.origin, sid)
    expired.deadline = time.monotonic() - 1
    with pytest.raises(ApplicationError) as error:
        store.claim(old_code, item.origin, "Phone")
    assert error.value.status_code == 410
