"""One-use QR invitation + explicit owner approval, ink-only delegated access.

No student login cookie or bearer is issued to the writing device. In-memory like
LiveHub: single worker, expires on restart. Parent logout/revocation revokes access.
"""
import secrets
import time
from threading import RLock
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.auth.models import AuthSession
from app.auth.security import as_utc, utc_now
from app.auth.service import AuthService
from app.core.exceptions import ApplicationError
from app.math_ink.live import Database, Student, LiveOperation, apply_operation, hub, origins
from app.math_ink.service import MathInkService
from app.users.models import User, Role

owner_router = APIRouter(prefix="/math-solutions/attempts", tags=["Writing devices"])
device_router = APIRouter(prefix="/math-ink-device", tags=["Writing devices"])


@dataclass
class Pairing:
    id: UUID
    actor: UUID
    attempt: UUID
    page: int
    origin: str
    parent_session: UUID
    deadline: float
    code_hash: str
    status: str = "WAITING"
    device_hash: str = ""
    label: str = "Điện thoại"
    confirmation: str = ""


class PairingStore:
    def __init__(self):
        self.items: dict[UUID, Pairing] = {}
        self.lock = RLock()

    def prune(self):
        now = time.monotonic()
        self.items = {key: value for key, value in self.items.items() if value.deadline > now and value.status != "REVOKED"}

    def create(self, actor, attempt, page, origin, parent_session):
        with self.lock:
            return self._create(actor, attempt, page, origin, parent_session)

    def _create(self, actor, attempt, page, origin, parent_session):
        self.prune()
        if len(self.items) >= 1024 or sum(item.actor == actor for item in self.items.values()) >= 8:
            raise ApplicationError(429, "PAIRING_LIMIT", "Hãy kết thúc kết nối cũ trước khi tạo mã mới.")
        code = secrets.token_urlsafe(32)
        item = Pairing(uuid4(), actor, attempt, page, origin, parent_session,
            time.monotonic() + 120, sha256(code.encode()).hexdigest())
        self.items[item.id] = item
        return item, code

    def claim(self, code, origin, label):
        with self.lock:
            return self._claim(code, origin, label)

    def _claim(self, code, origin, label):
        self.prune()
        digest = sha256(code.encode()).hexdigest()
        item = next((value for value in self.items.values() if value.code_hash == digest), None)
        if item is None or item.status != "WAITING" or item.origin != origin:
            raise ApplicationError(410, "PAIRING_EXPIRED", "Mã đã hết hạn hoặc đã được sử dụng. Hãy quét mã mới.")
        token = secrets.token_urlsafe(32)
        item.code_hash = ""  # A QR can be claimed only once, even while approval is pending.
        item.device_hash = sha256(token.encode()).hexdigest()
        item.confirmation = f"{secrets.randbelow(1000000):06d}"
        item.label = label
        item.status = "PENDING"
        return item, token


def store(scope):
    relay = hub(scope)
    if not hasattr(relay, "pairings"):
        relay.pairings = PairingStore()
    return relay.pairings


def public(item):
    status = "EXPIRED" if item.deadline <= time.monotonic() else item.status
    return {"id": str(item.id), "status": status, "device_name": item.label,
        "confirmation": item.confirmation, "page_index": item.page,
        "attempt_id": str(item.attempt), "origin": item.origin,
        "expires_in": max(0, int(item.deadline - time.monotonic()))}


def validate_parent(db, item):
    parent = db.get(AuthSession, item.parent_session)
    user = db.get(User, item.actor)
    if (not parent or parent.user_id != item.actor or parent.revoked_at is not None
            or as_utc(parent.expires_at) <= utc_now() or not user or not user.is_active or user.role != Role.STUDENT):
        raise ApplicationError(401, "DEVICE_REVOKED", "Kết nối đã kết thúc. Hãy kết nối lại từ máy tính.")
    service = MathInkService(db)
    service._editable(service._attempt(item.actor, item.attempt))


def resolve_device(scope, db, token, require_active=True):
    if not token or len(token) > 128:
        raise ApplicationError(401, "DEVICE_REQUIRED", "Hãy quét mã trên máy tính để kết nối.")
    digest = sha256(token.encode()).hexdigest()
    item = next((value for value in store(scope).items.values() if value.device_hash == digest), None)
    if not item or item.deadline <= time.monotonic() or item.status == "REVOKED":
        raise ApplicationError(401, "DEVICE_REVOKED", "Kết nối đã kết thúc. Hãy quét mã mới trên máy tính.")
    if scope.headers.get("origin") and scope.headers["origin"] != item.origin:
        raise ApplicationError(403, "DEVICE_ORIGIN_DENIED", "Nguồn kết nối không hợp lệ.")
    validate_parent(db, item)
    if require_active and item.status != "ACTIVE":
        raise ApplicationError(403, "DEVICE_AWAITING_APPROVAL", "Đang chờ máy tính cho phép viết.")
    return item


class InviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_index: int = Field(ge=0, lt=30)
    origin: str = Field(max_length=250)


def owned(request, db, student, attempt_id, pairing_id):
    item = store(request).items.get(pairing_id)
    if not item or item.actor != student.id or item.attempt != attempt_id:
        raise ApplicationError(404, "PAIRING_NOT_FOUND", "Không tìm thấy kết nối.")
    validate_parent(db, item)
    return item


@owner_router.post("/{attempt_id}/ink/pairings")
def create(attempt_id: UUID, payload: InviteRequest, request: Request, student: Student, db: Database):
    if payload.origin not in origins(request):
        raise ApplicationError(403, "LIVE_ORIGIN_DENIED", "Địa chỉ kết nối chưa được cấu hình.")
    service = MathInkService(db)
    service._editable(service._attempt(student.id, attempt_id))
    token = request.headers.get("authorization", "").partition(" ")[2]
    claims = AuthService(db, request.app.state.settings).tokens.decode_access_token(token)
    item, code = store(request).create(student.id, attempt_id, payload.page_index, payload.origin, claims.sid)
    return {**public(item), "code": code}


@owner_router.get("/{attempt_id}/ink/pairings/{pairing_id}")
def status(attempt_id: UUID, pairing_id: UUID, request: Request, student: Student, db: Database):
    return public(owned(request, db, student, attempt_id, pairing_id))


@owner_router.post("/{attempt_id}/ink/pairings/{pairing_id}/approve")
def approve(attempt_id: UUID, pairing_id: UUID, request: Request, student: Student, db: Database):
    item = owned(request, db, student, attempt_id, pairing_id)
    with store(request).lock:
        if item.status != "PENDING" or item.deadline <= time.monotonic():
            raise ApplicationError(409, "PAIRING_NOT_PENDING", "Yêu cầu kết nối không còn hiệu lực.")
        item.status = "ACTIVE"
        item.deadline = time.monotonic() + 7200
    return public(item)


@owner_router.post("/{attempt_id}/ink/pairings/{pairing_id}/revoke")
def revoke(attempt_id: UUID, pairing_id: UUID, request: Request, student: Student, db: Database):
    item = owned(request, db, student, attempt_id, pairing_id)
    with store(request).lock:
        item.status, item.code_hash = "REVOKED", ""
    return public(item)


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=40, max_length=80)
    origin: str = Field(max_length=250)
    device_name: str = Field(default="Điện thoại", min_length=1, max_length=40)


@device_router.post("/claim")
def claim(payload: ClaimRequest, request: Request, db: Database):
    item, token = store(request).claim(payload.code, payload.origin, payload.device_name)
    validate_parent(db, item)
    # Consumed by Next BFF into an HttpOnly, ink-only cookie. Never a login token.
    return {**public(item), "device_token": token}


@device_router.get("/session")
def session(request: Request, db: Database):
    item = resolve_device(request, db, request.headers.get("x-ink-device", ""), require_active=False)
    result = public(item)
    if item.status == "ACTIVE":
        document = MathInkService(db).get_document(item.actor, item.attempt)
        result["page_count"] = max(1, *(page.page_index + 1 for page in document.pages)) if document.pages else 1
    return result


@device_router.get("/ink/pages/{page_index}")
def read(page_index: int, request: Request, db: Database):
    item = resolve_device(request, db, request.headers.get("x-ink-device", ""))
    if not 0 <= page_index < 30:
        raise ApplicationError(422, "INK_PAGE_INVALID", "Trang không hợp lệ.")
    return MathInkService(db).get_page(item.actor, item.attempt, page_index)


@device_router.post("/ink/pages/{page_index}/operations")
async def write(page_index: int, payload: LiveOperation, request: Request, db: Database):
    def persist():
        item = resolve_device(request, db, request.headers.get("x-ink-device", ""))
        hub(request).allow_write(item.actor)
        return item, apply_operation(db, item.actor, item.attempt, page_index, payload)
    item, result = await run_in_threadpool(persist)
    await hub(request).publish((item.attempt, page_index), {"type": "STROKE_COMMITTED",
        "action_id": str(payload.client_action_id), **result.model_dump(mode="json")})
    for room in list(hub(request).rooms):
        if room[0] == item.attempt and room[1] != page_index:
            await hub(request).publish(room, {"type": "PAGE_AVAILABLE", "page_index": page_index,
                "document_revision": result.document_revision})
    return result


@device_router.post("/ink/live-ticket")
def ticket(payload: InviteRequest, request: Request, db: Database):
    item = resolve_device(request, db, request.headers.get("x-ink-device", ""))
    if payload.origin != item.origin:
        raise ApplicationError(403, "DEVICE_ORIGIN_DENIED", "Nguồn kết nối không hợp lệ.")
    token = request.headers["x-ink-device"]
    return {"ticket": hub(request).issue(item.actor, item.attempt, payload.page_index,
        item.origin, "device:" + token), "attempt_id": str(item.attempt), "expires_in": 30}


@device_router.post("/disconnect")
def disconnect(request: Request, db: Database):
    item = resolve_device(request, db, request.headers.get("x-ink-device", ""), require_active=False)
    with store(request).lock:
        item.status = "REVOKED"
    return {"status": "DISCONNECTED"}
