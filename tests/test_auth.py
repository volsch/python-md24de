"""Tests for authentication helpers using httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from md24de._auth import login, logout
from md24de._exceptions import LoginError

_SUCCESS_TEXT = "<html>Verbrauchsinformation</html>"
_FAIL_TEXT = "<html>Login fehlgeschlagen</html>"


def _make_client(*responses: httpx.Response) -> httpx.Client:
    """Return an httpx.Client backed by a MockTransport that returns *responses* in order."""
    it = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return next(it)

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestLogin:
    def test_success(self) -> None:
        client = _make_client(
            httpx.Response(200, text="<html>tenant page</html>"),
            httpx.Response(200, text=_SUCCESS_TEXT),
        )
        login(client, "xy", "user", "pass")  # must not raise

    def test_tenant_request_http_error_raises_login_error(self) -> None:
        client = _make_client(httpx.Response(503))
        with pytest.raises(LoginError, match="Tenant request failed with HTTP 503"):
            login(client, "xy", "user", "pass")

    def test_login_request_http_error_raises_login_error(self) -> None:
        client = _make_client(
            httpx.Response(200, text="<html>tenant page</html>"),
            httpx.Response(401),
        )
        with pytest.raises(LoginError, match="Login request failed with HTTP 401"):
            login(client, "xy", "user", "pass")

    def test_missing_confirmation_text_raises_login_error(self) -> None:
        client = _make_client(
            httpx.Response(200, text="<html>tenant page</html>"),
            httpx.Response(200, text=_FAIL_TEXT),
        )
        with pytest.raises(LoginError, match="credentials may be invalid"):
            login(client, "xy", "user", "pass")

    def test_credentials_url_encoded(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text=_SUCCESS_TEXT)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        login(client, "xy", "user@example.com", "p@ss&word")

        login_req = captured[1]
        assert "user%40example.com" in str(login_req.url)
        assert "p%40ss%26word" in str(login_req.url)

    def test_tenant_network_error_raises_login_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(LoginError, match="Tenant request failed"):
            login(client, "xy", "user", "pass")

    def test_login_network_error_raises_login_error(self) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, text="<html>tenant</html>")
            raise httpx.ConnectError("connection refused")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(LoginError, match="Login request failed"):
            login(client, "xy", "user", "pass")


class TestLogout:
    def test_success(self) -> None:
        client = _make_client(httpx.Response(200, text="ok"))
        logout(client, "xy")  # must not raise

    def test_network_error_suppressed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        logout(client, "xy")  # must not raise — errors are suppressed

    def test_http_error_suppressed(self) -> None:
        client = _make_client(httpx.Response(500))
        logout(client, "xy")  # must not raise
