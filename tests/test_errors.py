"""에러 계층 테스트."""

from angeldash.errors import (
    AngelNetError,
    ApiError,
    AuthError,
    BotBlockedError,
    SchemaError,
)


def test_all_errors_inherit_from_angelnet_error():
    for cls in (AuthError, BotBlockedError, SchemaError, ApiError):
        assert issubclass(cls, AngelNetError)


def test_api_error_carries_status_and_payload():
    err = ApiError("upstream failed", status_code=502, payload={"x": 1})
    assert err.status_code == 502
    assert err.payload == {"x": 1}
    assert "upstream failed" in str(err)
