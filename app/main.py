from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from config import get_settings

from .container import ApplicationContainer, build_container
from .domain.funnel import quick_replies
from .domain.models import ChatSession, FunnelState, PageContext
from .metrics import (
    BOOKING_REDIRECTS,
    CHAT_ERRORS,
    CHAT_MESSAGES,
    CHAT_SESSIONS,
    CHAT_STREAM_SECONDS,
    DEPENDENCY_READY,
    HTTP_LATENCY,
    HTTP_REQUESTS,
)
from .orchestrator import DependencyUnavailable, MessageRejected
from .ports import MedAngelUnavailable
from .schemas import (
    BookingLinkRequest,
    BookingLinkResponse,
    ClientEventRequest,
    CreateSessionRequest,
    MessageRequest,
    PageContextRequest,
    SessionResponse,
)
from .security import InvalidActionToken

logger = logging.getLogger("vodc_chat")
BASE_DIR = Path(__file__).resolve().parents[1]
WELCOME = (
    "Здравствуйте! Я информационный помощник ВОККДЦ. "
    "Помогу найти услугу, врача, подготовку и перейти к записи. "
    "Я не ставлю диагнозы и не назначаю лечение."
)
LOCAL_PAGE_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _safe_page_context(
    payload: PageContextRequest,
    trusted_hosts: tuple[str, ...],
) -> PageContext:
    parsed = urlparse(str(payload.url))
    host = (parsed.hostname or "").lower()
    if (
        host not in trusted_hosts
        or parsed.username
        or parsed.password
        or (host not in LOCAL_PAGE_HOSTS and parsed.scheme != "https")
        or (host not in LOCAL_PAGE_HOSTS and parsed.port not in {None, 443})
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "untrusted_page_context",
                "message": "Контекст страницы не относится к доверенному сайту",
            },
        )
    safe_page_url = urlunparse(parsed._replace(query="", fragment=""))
    return PageContext(
        url=safe_page_url,
        title=payload.title,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    settings = container.settings if container else get_settings()
    application_container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await application_container.close()

    app = FastAPI(
        title="VODC AI Navigator API",
        version="1.0.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.container = application_container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def hardening_and_metrics(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        content_length = request.headers.get("content-length")
        try:
            request_size = int(content_length) if content_length else 0
        except ValueError:
            request_size = settings.max_request_bytes + 1
        if request_size > settings.max_request_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "request_too_large",
                        "message": "Размер запроса превышает допустимый лимит",
                    },
                    "request_id": request_id,
                },
            )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled request error", extra={"request_id": request_id}
            )
            raise
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(
            request.method, route_path, str(response.status_code)
        ).inc()
        HTTP_LATENCY.labels(request.method, route_path).observe(
            time.perf_counter() - started
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.get("/", include_in_schema=False)
    async def widget_index():
        return FileResponse(BASE_DIR / "widget" / "index.html")

    app.mount(
        "/static",
        StaticFiles(directory=BASE_DIR / "widget"),
        name="static",
    )

    @app.post(
        "/api/v1/sessions",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(payload: CreateSessionRequest, request: Request):
        page_context = _safe_page_context(
            payload.page_context,
            settings.trusted_page_hosts,
        )
        client_ip = request.client.host if request.client else "unknown"
        allowed = await application_container.sessions.allow_request(
            f"session:{client_ip}",
            settings.rate_limit_requests,
            settings.rate_limit_window_seconds,
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "rate_limit_exceeded",
                    "message": "Слишком много запросов",
                },
            )
        session = ChatSession(
            id=str(uuid.uuid4()),
            page_context=page_context,
        )
        await application_container.sessions.create(session)
        CHAT_SESSIONS.inc()
        await application_container.events.record_event(
            session.id,
            "chat_started",
            {
                "page_url": session.page_context.url,
                "privacy_notice_version": payload.client.privacy_notice_version,
            },
        )
        return SessionResponse(
            session_id=session.id,
            expires_in=settings.session_ttl_seconds,
            state=session.state.value,
            welcome=WELCOME,
            quick_replies=quick_replies(session.state),
        )

    @app.post("/api/v1/sessions/{session_id}/messages/stream")
    async def stream_message(
        session_id: uuid.UUID, payload: MessageRequest, request: Request
    ):
        session = await application_container.sessions.get(str(session_id))
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "session_not_found",
                    "message": "Сессия истекла или не существует",
                },
            )
        if payload.input.text and len(payload.input.text) > settings.max_message_length:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "message_too_long",
                    "message": "Сообщение превышает допустимую длину",
                },
            )
        client_ip = request.client.host if request.client else "unknown"
        allowed = await application_container.sessions.allow_request(
            f"message:{client_ip}:{session_id}",
            settings.rate_limit_requests,
            settings.rate_limit_window_seconds,
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "rate_limit_exceeded",
                    "message": "Слишком много запросов",
                },
            )
        if payload.client_message_id in session.processed_client_message_ids:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_message",
                    "message": "Сообщение с таким client_message_id уже обработано",
                },
            )
        if payload.page_context is not None:
            session.update_page_context(
                _safe_page_context(
                    payload.page_context,
                    settings.trusted_page_hosts,
                )
            )
        session.processed_client_message_ids.append(payload.client_message_id)
        session.processed_client_message_ids = session.processed_client_message_ids[
            -100:
        ]
        await application_container.sessions.save(session)
        CHAT_MESSAGES.labels(payload.input.type.value).inc()

        async def events() -> AsyncIterator[str]:
            stream_started = time.perf_counter()
            try:
                async for event in application_container.orchestrator.stream(
                    session,
                    payload.input.type,
                    text=payload.input.text,
                    token=payload.input.token,
                ):
                    yield _sse(event["event"], event["data"])
            except MessageRejected as exc:
                CHAT_ERRORS.labels("invalid_action").inc()
                yield _sse(
                    "error",
                    {
                        "code": "invalid_action",
                        "message": str(exc),
                        "retryable": False,
                    },
                )
                yield _sse("done", {"failed": True})
            except DependencyUnavailable as exc:
                CHAT_ERRORS.labels("mis_unavailable").inc()
                yield _sse(
                    "error",
                    {
                        "code": "mis_unavailable",
                        "message": str(exc),
                        "retryable": True,
                    },
                )
                yield _sse("done", {"failed": True})
            finally:
                CHAT_STREAM_SECONDS.labels(payload.input.type.value).observe(
                    time.perf_counter() - stream_started
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post(
        "/api/v1/sessions/{session_id}/booking-link",
        response_model=BookingLinkResponse,
    )
    async def booking_link(session_id: uuid.UUID, payload: BookingLinkRequest):
        session = await application_container.sessions.get(str(session_id))
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "session_not_found"})
        try:
            token = application_container.orchestrator.signer.verify(
                payload.slot_token,
                session_id=session.id,
                action="select_slot",
            )
            service_id = session.selection.service_id
            if not service_id:
                raise InvalidActionToken("Сначала выберите услугу")
            if (
                session.state is not FunnelState.SLOT_SELECTED
                or session.selection.slot_id != token.entity_id
            ):
                raise InvalidActionToken("Сначала заново выберите доступное время")
            slot = await application_container.medangel.validate_slot(
                token.entity_id,
                service_id,
                session.selection.doctor_id,
                session.selection.branch_id,
            )
            if not slot:
                raise InvalidActionToken("Слот уже недоступен")
            if (
                slot.service_id != service_id
                or (
                    session.selection.doctor_id
                    and slot.doctor_id != session.selection.doctor_id
                )
                or (
                    session.selection.branch_id
                    and slot.branch_id != session.selection.branch_id
                )
            ):
                raise InvalidActionToken("Слот не соответствует текущему выбору")
        except InvalidActionToken as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "slot_unavailable", "message": str(exc)},
            ) from exc
        except MedAngelUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "mis_unavailable", "message": str(exc)},
            ) from exc
        session.selection.slot_id = slot.id
        session.selection.doctor_id = slot.doctor_id
        session.selection.branch_id = slot.branch_id
        session.state = FunnelState.BOOKING_REDIRECT
        await application_container.sessions.save(session)
        url = application_container.medangel.booking_url(session)
        await application_container.events.record_event(
            session.id,
            "booking_redirect",
            {
                "service_id": service_id,
                "doctor_id": session.selection.doctor_id,
                "branch_id": session.selection.branch_id,
            },
        )
        BOOKING_REDIRECTS.inc()
        return BookingLinkResponse(url=url)

    @app.post(
        "/api/v1/sessions/{session_id}/events",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def client_event(session_id: uuid.UUID, payload: ClientEventRequest):
        session = await application_container.sessions.get(str(session_id))
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "session_not_found"})
        await application_container.events.record_event(
            session.id, payload.type, payload.properties
        )
        return {"accepted": True}

    @app.get("/health/live")
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready")
    async def ready():
        checks = await asyncio.gather(
            application_container.sessions.ping(),
            application_container.events.ping(),
            application_container.knowledge.ping(),
            application_container.model.ping(),
            application_container.medangel.ping(),
            return_exceptions=True,
        )
        names = ("redis", "postgres", "knowledge", "model", "mis")
        dependencies = {name: result is True for name, result in zip(names, checks)}
        for name, value in dependencies.items():
            DEPENDENCY_READY.labels(name, str(value).lower()).inc()
        required_names = names if settings.persistence_required else ("knowledge",)
        is_ready = all(dependencies[name] for name in required_names)
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={
                "status": "ready" if is_ready else "not_ready",
                "dependencies": dependencies,
            },
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
