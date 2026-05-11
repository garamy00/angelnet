"""공통 pytest fixture."""

import pytest
import pytest_asyncio
import respx

from angeldash.client import AngelNetClient


@pytest.fixture
def mock_router():
    """respx mock router 컨텍스트."""
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest_asyncio.fixture
async def client():
    """AngelNetClient 인스턴스 (테스트 종료 시 자동 close)."""
    c = AngelNetClient(user_id="testuser")
    try:
        yield c
    finally:
        await c.close()
