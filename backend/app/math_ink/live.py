"""Single-worker live relay. Only acknowledged MathInk transactions are durable.

Transient strokes are deliberately not persisted. Reconnect always reads the DB.
Tickets are single-use, 30 seconds, scoped to actor/attempt/page/origin, never URLs.
"""
import asyncio
import json
import secrets
import time
from dataclasses import dataclass, field
from threading import RLock
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import require_role
from app.auth.service import AuthService
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.math_ink.codec import encode_strokes, decode_strokes
from app.math_ink.models import MathInkDocument, MathInkOperation, MathInkPage
from app.math_ink.schemas import InkStroke, InkPageRead, InkPageWrite
from app.math_ink.service import MathInkService
from app.users.models import Role, User

router = APIRouter(prefix="/math-solutions/attempts", tags=["Live Math Ink"])
Database = Annotated[Session, Depends(get_db)]
Student = Annotated[User, Depends(require_role(Role.STUDENT))]


class LiveOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_action_id: UUID
    expected_document_revision: int = Field(ge=0)
    # Fixed intent: only these IDs may be added/deleted. Never a page replacement.
    add: list[InkStroke] = Field(default_factory=list, max_length=400)
    remove: list[InkStroke] = Field(default_factory=list, max_length=400)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [s.id for s in self.add + self.remove]
        if len(ids) != len(set(ids)):
            raise ValueError("Operation IDs must be distinct")
        if sum(len(s.points) for s in self.add + self.remove) > 30000:
            raise ValueError("Operation exceeds point budget")
        return self


def apply_operation(db: Session, actor: UUID, attempt_id: UUID, page_index: int, op: LiveOperation) -> InkPageRead:
    if not 0 <= page_index < 30:
        raise ApplicationError(422, "INK_PAGE_INVALID", "Invalid page")
    service = MathInkService(db)
    fingerprint = sha256(json.dumps({"live": 1, "page": page_index,
        "add": [s.model_dump(mode="json") for s in op.add],
        "remove": [s.model_dump(mode="json") for s in op.remove]}, sort_keys=True).encode()).hexdigest()
    try:
        # Same lock as legacy PUT; protects first document creation too.
        attempt = service._attempt(actor, attempt_id, lock=True)
        doc = db.scalar(select(MathInkDocument).where(MathInkDocument.attempt_id == attempt_id).with_for_update())
        prior = db.scalar(select(MathInkOperation).where(MathInkOperation.document_id == doc.id,
            MathInkOperation.client_action_id == op.client_action_id)) if doc else None
        if prior:
            if prior.actor_user_id != actor or prior.request_hash != fingerprint:
                raise ApplicationError(409, "INK_ACTION_REUSED", "Operation ID reused with different intent")
            result = service.get_page(actor, attempt_id, page_index)
            db.commit()
            return result
        service._editable(attempt)
        revision = doc.revision if doc else 0
        if revision != op.expected_document_revision:
            raise ApplicationError(409, "INK_REVISION_CONFLICT", "Resync before retrying the same intent")
        page = db.scalar(select(MathInkPage).where(MathInkPage.document_id == doc.id,
            MathInkPage.page_index == page_index)) if doc else None
        strokes = decode_strokes(page.compressed_strokes) if page else []
        canonical = {s.id: s for s in strokes}
        for removed in op.remove:
            if removed.id in canonical and canonical[removed.id] != removed:
                raise ApplicationError(409, "INK_STROKE_CONFLICT", "Stroke changed; deletion needs review")
            canonical.pop(removed.id, None)
        for added in op.add:
            if added.id in canonical and canonical[added.id] != added:
                raise ApplicationError(409, "INK_STROKE_CONFLICT", "Stroke IDs are immutable")
            canonical[added.id] = added
        validated = InkPageWrite(expected_document_revision=revision,
            client_action_id=op.client_action_id, strokes=list(canonical.values()))
        compressed, digest, point_count = encode_strokes(validated.strokes)
        changed = page is None or page.sha256 != digest
        if doc is None:
            doc = MathInkDocument(attempt_id=attempt_id, revision=1)
            db.add(doc)
            db.flush()
        elif changed:
            doc.revision += 1
        if page is None:
            page = MathInkPage(document_id=doc.id, page_index=page_index)
            db.add(page)
        page.compressed_strokes, page.sha256 = compressed, digest
        page.stroke_count, page.point_count = len(validated.strokes), point_count
        db.add(MathInkOperation(document_id=doc.id, actor_user_id=actor,
            client_action_id=op.client_action_id, request_hash=fingerprint,
            page_index=page_index, result_revision=doc.revision))
        result = InkPageRead(document_revision=doc.revision, page_index=page_index, strokes=validated.strokes)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@dataclass(eq=False)
class Peer:
    socket: WebSocket
    id: str = field(default_factory=lambda: secrets.token_hex(8))
    label: str = "Thiết bị viết"
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, message):
        async with self.send_lock:
            await asyncio.wait_for(self.socket.send_json(message), 3)


class LiveHub:
    def __init__(self):
        from app.math_ink.pairing import PairingStore
        self.pairings = PairingStore()
        self.lock = RLock()
        self.tickets: dict[str, tuple] = {}
        self.rooms: dict[tuple, set[Peer]] = {}
        self.writes: dict[UUID, tuple[float, int]] = {}

    def allow_write(self, actor):
        with self.lock:
            self._allow_write(actor)

    def _allow_write(self, actor):
        now = time.monotonic()
        self.writes = {key: value for key, value in self.writes.items() if now - value[0] < 1}
        start, count = self.writes.get(actor, (now, 0))
        if count >= 20:
            raise ApplicationError(429, "LIVE_RATE_LIMIT", "Too many ink operations; retry shortly")
        self.writes[actor] = (start, count + 1)

    def issue(self, actor, attempt, page, origin, credential=""):
        with self.lock:
            return self._issue(actor, attempt, page, origin, credential)

    def consume(self, token):
        with self.lock:
            return self.tickets.pop(token, None)

    def _issue(self, actor, attempt, page, origin, credential=""):
        now = time.monotonic()
        self.tickets = {k: v for k, v in self.tickets.items() if v[-1] > now}
        if len(self.tickets) >= 2048 or sum(v[0] == actor for v in self.tickets.values()) >= 16:
            raise ApplicationError(429, "LIVE_BUSY", "Too many outstanding tickets")
        token = secrets.token_urlsafe(32)
        self.tickets[token] = (actor, attempt, page, origin, credential, now + 30)
        return token

    async def publish(self, room, event, exclude=None):
        peers = list(self.rooms.get(room, set()) - ({exclude} if exclude else set()))
        results = await asyncio.gather(*(p.send(event) for p in peers), return_exceptions=True)
        for peer, result in zip(peers, results):
            if isinstance(result, Exception):
                self.rooms.get(room, set()).discard(peer)
                try:
                    await peer.socket.close(code=1013)
                except Exception:
                    pass

    def presence(self, room):
        peers = self.rooms.get(room, set())
        return {"type": "PRESENCE", "devices": len(peers),
            "peers": [{"id": p.id, "label": p.label} for p in peers]}


def hub(scope) -> LiveHub:
    return scope.app.state.live_ink_hub


def origins(scope):
    from app.math_ink.lan import lan_origins
    settings = scope.app.state.settings
    if settings.lan_mode:
        return lan_origins(settings)
    return {settings.frontend_origin, *(s.strip().rstrip("/") for s in settings.live_ink_origins.split(",") if s.strip())}


class TicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_index: int = Field(ge=0, lt=30)
    origin: str = Field(max_length=250)


@router.post("/{attempt_id}/ink/live-ticket")
async def ticket(attempt_id: UUID, payload: TicketRequest, request: Request, student: Student, db: Database):
    if payload.origin not in origins(request):
        raise ApplicationError(403, "LIVE_ORIGIN_DENIED", "Frontend origin not configured")
    def check():
        service = MathInkService(db)
        service._editable(service._attempt(student.id, attempt_id))
    await run_in_threadpool(check)
    credential = request.headers.get("authorization", "").partition(" ")[2]
    return {"ticket": hub(request).issue(student.id, attempt_id, payload.page_index, payload.origin, credential), "expires_in": 30}


@router.post("/{attempt_id}/ink/pages/{page_index}/operations", response_model=InkPageRead)
async def operation(attempt_id: UUID, page_index: int, payload: LiveOperation, request: Request, student: Student, db: Database):
    hub(request).allow_write(student.id)
    result = await run_in_threadpool(apply_operation, db, student.id, attempt_id, page_index, payload)
    await hub(request).publish((attempt_id, page_index), {"type": "STROKE_COMMITTED",
        "action_id": str(payload.client_action_id), **result.model_dump(mode="json")})
    for room in list(hub(request).rooms):
        if room[0] == attempt_id and room[1] != page_index:
            await hub(request).publish(room, {"type": "PAGE_AVAILABLE", "page_index": page_index,
                "document_revision": result.document_revision})
    return result


@router.websocket("/{attempt_id}/ink/live")
async def live(socket: WebSocket, attempt_id: UUID, db: Database):
    origin = socket.headers.get("origin", "")
    if origin not in origins(socket):
        await socket.close(code=4403)
        return
    relay = hub(socket)
    peer = Peer(socket)
    room = None
    await socket.accept()
    try:
        auth = await asyncio.wait_for(socket.receive_text(), 5)
        if len(auth) > 512:
            raise ValueError("Invalid authentication")
        auth_message = json.loads(auth)
        if not isinstance(auth_message, dict):
            raise ValueError("Invalid authentication")
        token = auth_message.get("ticket", "")
        if not isinstance(token, str) or len(token) > 128:
            raise ValueError("Invalid ticket")
        if isinstance(auth_message.get("label"), str):
            peer.label = auth_message["label"][:40]
        grant = relay.consume(token)
        if not grant or grant[1] != attempt_id or grant[3] != origin or grant[-1] < time.monotonic():
            await socket.close(code=4401)
            return
        actor, _, page, _, credential, _ = grant
        room = (attempt_id, page)
        if len(relay.rooms.get(room, set())) >= 8:
            await socket.close(code=4429)
            return
        service = MathInkService(db)

        def snapshot():
            db.rollback()  # Fresh DB view, including revocations/legacy PUTs.
            if credential.startswith("device:"):
                from app.math_ink.pairing import resolve_device
                grant = resolve_device(socket, db, credential[7:])
                if grant.actor != actor or grant.attempt != attempt_id:
                    raise ApplicationError(403, "FORBIDDEN", "Invalid writing scope")
                user = db.get(User, actor)
            else:
                user = AuthService(db, socket.app.state.settings).current_user(credential)
            if user is None or not user.is_active or user.role != Role.STUDENT:
                raise ApplicationError(403, "FORBIDDEN", "Session revoked")
            service._editable(service._attempt(actor, attempt_id))
            result = service.get_page(actor, attempt_id, page).model_dump(mode="json")
            db.rollback()
            return result

        initial = await run_in_threadpool(snapshot)
        members = relay.rooms.setdefault(room, set())
        # Recheck after DB await: simultaneous handshakes must not bypass the cap.
        if len(members) >= 8:
            await socket.close(code=4429)
            return
        members.add(peer)
        await peer.send({"type": "PAGE_SNAPSHOT", "peer_id": peer.id, **initial})
        await relay.publish(room, relay.presence(room))
        window, count, sequence = time.monotonic(), 0, -1
        active_id = None
        started = time.monotonic()
        while True:
            raw = await asyncio.wait_for(socket.receive_text(), 35)
            if time.monotonic() - started > 900:  # Re-ticket checks current HTTP session.
                await socket.close(code=4401)
                break
            if len(raw.encode()) > 300000:
                raise ValueError("Payload too large")
            if time.monotonic() - window > 1:
                window, count = time.monotonic(), 0
            count += 1
            if count > 35:
                raise ValueError("Rate limit")
            event = json.loads(raw)
            if not isinstance(event, dict):
                raise ValueError("Invalid event")
            if event.get("type") == "RESYNC":
                await peer.send({"type": "PAGE_SNAPSHOT", **await run_in_threadpool(snapshot)})
            elif event.get("type") in ("STROKE_BEGIN", "STROKE_POINTS", "STROKE_END"):
                seq = event.get("seq")
                if type(seq) is not int or seq <= sequence:
                    continue
                sequence = seq
                stroke = InkStroke.model_validate(event.get("stroke"))
                if event["type"] == "STROKE_BEGIN":
                    await run_in_threadpool(snapshot)  # Recheck editable/ownership.
                    active_id = stroke.id
                if active_id != stroke.id:
                    continue
                await relay.publish(room, {"type": event["type"], "peer_id": peer.id,
                    "seq": seq, "stroke": stroke.model_dump(mode="json")}, exclude=peer)
                if event["type"] == "STROKE_END":
                    active_id = None
            else:
                raise ValueError("Unsupported event")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except (ValueError, ValidationError, ApplicationError):
        await socket.close(code=4400)
    finally:
        db.rollback()
        if room:
            relay.rooms.get(room, set()).discard(peer)
            await relay.publish(room, {**relay.presence(room), "departed": peer.id})
            if not relay.rooms.get(room):
                relay.rooms.pop(room, None)
