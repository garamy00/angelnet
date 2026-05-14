"""회의실 도메인 FastAPI routes.

server.py 가 lifespan 안에서 app.dependency_overrides 로 get_client/get_password
실제 구현을 주입한다. timesheet/routes.py 와 동일한 register_routes(app) 패턴.
"""

from __future__ import annotations

import datetime
import logging

from fastapi import Depends, FastAPI, HTTPException, Query

from .._common.errors import ApiError, AuthError
from .._common.models import User
from .client import AngelNetClient
from .models import Reservation, ReservationCreate
from .registry import ROOMS, list_rooms_on_floor

_route_logger = logging.getLogger(__name__)

# ─── 의존성 placeholder ────────────────────────────────


def get_client() -> AngelNetClient:
    """lifespan 또는 테스트가 dependency_overrides 로 교체."""
    raise RuntimeError("client not initialized")


def get_password() -> str:
    """lifespan 또는 테스트가 dependency_overrides 로 교체."""
    raise RuntimeError("password not initialized")


# ─── 라우트 등록 함수 ──────────────────────────────────


def register_routes(app: FastAPI) -> None:
    """회의실 도메인의 5개 API 라우트를 app 에 등록한다."""

    async def _with_session_retry(client: AngelNetClient, coro_fn):
        """회사 API 호출을 1회 재시도 — AutoReloginHttp 가 못 잡은 만료 응답
        (예: 200 + 빈 데이터, 200 + JSON error) 을 라우트 레벨에서 catch.
        """
        try:
            return await coro_fn()
        except (ApiError, AuthError) as exc:
            _route_logger.info("Rooms API failed, forcing relogin: %s", exc)
            try:
                await client.force_relogin()
            except Exception as relog_exc:
                _route_logger.warning("force_relogin failed: %s", relog_exc)
                raise exc from None
            return await coro_fn()

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
        return await _with_session_retry(
            client,
            lambda: client.list_reservations(start, end, room_id=room_id),
        )

    @app.post("/api/reservations", status_code=201)
    async def create_reservation(
        payload: ReservationCreate,
        client: AngelNetClient = Depends(get_client),
        password: str = Depends(get_password),
    ) -> dict:
        event_id = await client.create_reservation(password, payload)
        return {"id": event_id}

    @app.delete(
        "/api/reservations/{event_id}",
        status_code=204,
        response_model=None,
    )
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
