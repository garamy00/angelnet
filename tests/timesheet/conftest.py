"""공통 pytest 픽스처."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from angeldash.timesheet import db as db_module
from angeldash.timesheet.models import User


@pytest.fixture
def conn() -> Generator[sqlite3.Connection, None, None]:
    """인메모리 SQLite 연결 + 스키마 초기화.

    운영 connect() 와 동일하게 foreign_keys PRAGMA 를 활성화하여
    테스트가 실제 운영 환경의 제약을 그대로 시뮬레이션하도록 한다.
    """
    # check_same_thread=False: async 핸들러가 다른 스레드에서 connection 을 사용할 수 있도록 허용
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    db_module.init_schema(c)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def mock_client() -> AsyncMock:
    """TimesheetClient mock — login 만 stub. user_id 속성 미리 지정."""
    m = AsyncMock()
    m.user_id = "alice"
    m.login.return_value = User(user_id="alice", name="앨리스")
    return m


@pytest.fixture
def test_app(conn: sqlite3.Connection, mock_client: AsyncMock):
    """build_app 으로 만든 통합 FastAPI 앱 + 타임시트 의존성 override.

    회의실(get_client/get_password in angeldash.server) 도 같은 mock_client 로 override
    해두면 /api/me (회의실측 핸들러) 도 테스트 가능. mock_client.login 이 양쪽 호환.
    """
    from angeldash.rooms.routes import get_client as rooms_get_client
    from angeldash.rooms.routes import get_password as shared_get_password
    from angeldash.server import build_app
    from angeldash.timesheet.routes import (
        get_client as ts_get_client,
        get_conn as ts_get_conn,
        get_password as ts_get_password,
    )

    app = build_app(user_id="alice", skip_lifespan_login=True)
    app.dependency_overrides[ts_get_conn] = lambda: conn
    app.dependency_overrides[ts_get_client] = lambda: mock_client
    app.dependency_overrides[ts_get_password] = lambda: "secret"
    app.dependency_overrides[rooms_get_client] = lambda: mock_client
    app.dependency_overrides[shared_get_password] = lambda: "secret"
    return app


@pytest.fixture
def api(test_app):
    return TestClient(test_app)
