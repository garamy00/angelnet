"""FastAPI app: REST 라우터, 정적 파일 서빙, 의존성 주입."""

from __future__ import annotations

import datetime
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import KeychainStore
from .client import AngelNetClient
from .errors import AngelNetError, ApiError, AuthError, BotBlockedError
from .models import Reservation, ReservationCreate, User
from .rooms import ROOMS, list_rooms_on_floor

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def get_client() -> AngelNetClient:
    """의존성 주입 placeholder. lifespan 또는 테스트가 dependency_overrides 로 교체."""
    raise RuntimeError("client not initialized")


def get_password() -> str:
    """의존성 주입 placeholder. lifespan 또는 테스트가 dependency_overrides 로 교체."""
    raise RuntimeError("password not initialized")


def build_app(user_id: str) -> FastAPI:
    """FastAPI 앱을 생성한다. lifespan 안에서 client·password dependency 를 주입."""
    keychain = KeychainStore(account=user_id)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        password = os.environ.get("ANGELNET_PWD") or keychain.get()
        if not password:
            raise RuntimeError(
                "Password not found. Set ANGELNET_PWD or run 'angeldash init' first."
            )
        client = AngelNetClient(user_id=user_id)
        await client.login(password)

        app.dependency_overrides[get_client] = lambda: client
        app.dependency_overrides[get_password] = lambda: password
        try:
            yield
        finally:
            await client.close()

    app = FastAPI(title="AngelNet 회의실 대시보드", lifespan=lifespan)

    # lifespan 에서 이미 login 호출됨. 여기서는 Spring 세션 캐시 히트로
    # 실제 네트워크 호출 없이 User 정보만 반환된다.
    @app.get("/api/me", response_model=User)
    async def me(
        client: AngelNetClient = Depends(get_client),
        password: str = Depends(get_password),
    ) -> User:
        return await client.login(password)

    @app.get("/api/rooms")
    async def rooms(floor: int | None = Query(default=None)) -> list[dict]:
        if floor is not None:
            items = list_rooms_on_floor(floor)
        else:
            # ID 숫자 기준으로 정렬해 응답 순서를 결정적으로 유지
            items = sorted(ROOMS.values(), key=lambda r: int(r.id))
        return [{"id": r.id, "name": r.name, "floor": r.floor} for r in items]

    @app.get("/api/reservations", response_model=list[Reservation])
    async def get_reservations(
        start: str = Query(..., description="YYYY-MM-DD"),
        end: str = Query(..., description="YYYY-MM-DD"),
        room_id: str | None = Query(default=None),
        client: AngelNetClient = Depends(get_client),
    ) -> list[Reservation]:
        return await client.list_reservations(start, end, room_id=room_id)

    @app.post("/api/reservations", status_code=201)
    async def create_reservation(
        payload: ReservationCreate,
        client: AngelNetClient = Depends(get_client),
        password: str = Depends(get_password),
    ) -> dict:
        event_id = await client.create_reservation(password, payload)
        return {"id": event_id}

    @app.delete("/api/reservations/{event_id}", status_code=204)
    async def delete_reservation(
        event_id: int,
        event_date: str = Query(..., description="원본 예약일 YYYY-MM-DD"),
        client: AngelNetClient = Depends(get_client),
        password: str = Depends(get_password),
    ) -> None:
        # 라우터 경계에서 외부 입력 형식 검증
        try:
            datetime.date.fromisoformat(event_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="event_date must be YYYY-MM-DD"
            ) from exc

        await client.delete_reservation(
            password, event_id=event_id, event_date=event_date
        )

    # 1인 도구 + 정적 파일이 자주 변경 → 항상 fresh 받도록 캐시 무력화
    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers=_NO_CACHE)

    if STATIC_DIR.exists():

        class NoCacheStatic(StaticFiles):
            async def get_response(self, path: str, scope):
                resp = await super().get_response(path, scope)
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                return resp

        app.mount("/static", NoCacheStatic(directory=STATIC_DIR), name="static")

    @app.exception_handler(BotBlockedError)
    async def _bot_blocked(_, exc: BotBlockedError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "error": "bot_blocked",
                "message": str(exc),
                "retry_after_min": 5,
            },
        )

    @app.exception_handler(AuthError)
    async def _auth(_, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={
                "error": "auth",
                "message": str(exc),
                "hint": "Keychain 패스워드를 재설정한 뒤 angeldash 를 다시 실행하세요.",
            },
        )

    @app.exception_handler(ApiError)
    async def _api(_, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code or 502,
            content={
                "error": "api",
                "message": str(exc),
                "payload": exc.payload,
            },
        )

    @app.exception_handler(AngelNetError)
    async def _generic(_, exc: AngelNetError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "angelnet", "message": str(exc)},
        )

    return app
