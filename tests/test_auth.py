"""Tests for authentication helpers using httpx.MockTransport."""

from __future__ import annotations

import base64

import httpx
import pytest

from md24de._auth import login, logout
from md24de._exceptions import LoginError

_OK_JSON = '{"message": "ok"}'


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
            httpx.Response(200, text=_OK_JSON, headers={"Content-Type": "application/json"}),
        )
        login(client, "xy", "user", "pass")  # must not raise

    def test_tenant_request_http_error_raises_login_error(self) -> None:
        client = _make_client(httpx.Response(503))
        with pytest.raises(LoginError, match="Tenant request failed with HTTP 503"):
            login(client, "xy", "user", "pass")

    def test_login_request_http_status_error_raises_login_error(self) -> None:
        client = _make_client(
            httpx.Response(200, text="<html>tenant page</html>"),
            httpx.Response(500, text="Fehler"),
        )
        with pytest.raises(LoginError, match="Login failed with HTTP 500"):
            login(client, "xy", "user", "pass")

    def test_non_json_response_raises_login_error(self) -> None:
        client = _make_client(
            httpx.Response(200, text="<html>tenant page</html>"),
            httpx.Response(200, text="not json"),
        )
        with pytest.raises(LoginError, match="not valid JSON"):
            login(client, "xy", "user", "pass")

    def test_missing_ok_message_raises_login_error(self) -> None:
        client = _make_client(
            httpx.Response(200, text="<html>tenant page</html>"),
            httpx.Response(200, text='{"message": "nope"}'),
        )
        with pytest.raises(LoginError, match="credentials may be invalid"):
            login(client, "xy", "user", "pass")

    def test_non_dict_json_response_raises_login_error(self) -> None:
        """Valid JSON that isn't an object (e.g. a bare array) must still raise LoginError."""
        client = _make_client(
            httpx.Response(200, text="<html>tenant page</html>"),
            httpx.Response(200, text="[1, 2, 3]"),
        )
        with pytest.raises(LoginError, match="credentials may be invalid"):
            login(client, "xy", "user", "pass")

    def test_credentials_sent_as_basic_auth_header(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            if request.url.path == "/getlogintoken":
                return httpx.Response(200, text=_OK_JSON)
            return httpx.Response(200, text="<html>tenant page</html>")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        login(client, "xy", "user@example.com", "p@ss&word")

        login_req = captured[1]
        expected = base64.b64encode(b"user@example.com:p@ss&word").decode("ascii")
        assert login_req.headers["Authorization"] == f"Basic {expected}"
        # Credentials must never appear in the URL.
        assert "user@example.com" not in str(login_req.url)
        assert "p@ss&word" not in str(login_req.url)

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

    def test_requests_logout_endpoint(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text="ok")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        logout(client, "xy")

        assert len(captured) == 1
        assert captured[0].method == "GET"
        assert captured[0].url.path == "/logout"
