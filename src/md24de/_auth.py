"""Authentication helpers for the messdienst24.de portal."""

from __future__ import annotations

import base64
import contextlib
import logging
from typing import cast

import httpx

from md24de._exceptions import LoginError

_BASE_URL = "https://messdienst24.de"

_log = logging.getLogger(__name__)


def login(
    client: httpx.Client,
    tenant: str,
    username: str,
    user_password: str,
) -> None:
    """Authenticate against the portal.

    Performs a two-step login:

    1. GET ``/?md={tenant}`` — establishes the tenant session (sets the ``md`` cookie).
    2. POST ``/getlogintoken`` with an HTTP ``Basic`` ``Authorization`` header — validates
       credentials and, on success, returns ``{"message": "ok"}`` and sets the ``lt``
       session-token cookie.

    On success, the session cookies are stored in *client* and used automatically
    for all subsequent requests.

    Args:
        client: An :class:`httpx.Client` instance whose cookie jar will be populated.
        tenant: Portal tenant identifier (e.g. ``"xy"``).
        username: Portal username.
        user_password: Portal user_password.

    Raises:
        LoginError: If either request fails or the login response does not confirm
            success.
    """
    # Step 1: tenant page — establishes the tenant ("md") cookie required by
    # the subsequent login request.
    _log.debug("Fetching tenant page (tenant=%r)", tenant)
    try:
        r1 = client.get(f"{_BASE_URL}/", params={"md": tenant})
        r1.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LoginError(f"Tenant request failed with HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise LoginError(f"Tenant request failed: {exc}") from exc
    _log.debug("Tenant page fetched (HTTP %s)", r1.status_code)

    # Step 2: login — HTTP Basic credentials, exactly as the portal's own login
    # page submits them via fetch(). NOTE: never log the Authorization header value.
    credentials = base64.b64encode(f"{username}:{user_password}".encode()).decode("ascii")
    _log.debug("Sending login request (tenant=%r)", tenant)
    try:
        r2 = client.post(
            f"{_BASE_URL}/getlogintoken",
            headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
        )
        r2.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LoginError(
            f"Login failed with HTTP {exc.response.status_code}: credentials may be invalid "
            "or the portal returned an unexpected response."
        ) from exc
    except httpx.HTTPError as exc:
        raise LoginError(f"Login request failed: {exc}") from exc
    try:
        data: object = r2.json()
    except ValueError as exc:
        raise LoginError("Login failed: portal response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise LoginError(
            "Login failed: credentials may be invalid or the portal returned "
            "an unexpected response."
        )
    data_dict = cast(dict[str, object], data)
    if data_dict.get("message") != "ok":
        raise LoginError(
            "Login failed: credentials may be invalid or the portal returned "
            "an unexpected response."
        )
    _log.debug("Login successful (tenant=%r)", tenant)


def logout(client: httpx.Client, tenant: str) -> None:  # noqa: ARG001
    """Log out from the portal.

    Errors are silently suppressed — logout is best-effort only.

    Args:
        client: An authenticated :class:`httpx.Client` instance.
        tenant: Portal tenant identifier (unused — kept for API stability; the portal's
            logout endpoint is tenant-independent and clears the session from the ``lt``
            cookie alone).
    """
    _log.debug("Logging out (tenant=%r)", tenant)
    with contextlib.suppress(httpx.HTTPError):
        client.get(f"{_BASE_URL}/logout")
    _log.debug("Logout complete (tenant=%r)", tenant)
