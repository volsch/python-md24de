"""Authentication helpers for the messdienst24.de portal."""

from __future__ import annotations

import contextlib
import logging
import time
from urllib.parse import quote

import httpx

from md24de._exceptions import LoginError

_BASE_URL = "https://legacy.messdienst24.de"

_log = logging.getLogger(__name__)


def login(
    client: httpx.Client,
    tenant: str,
    username: str,
    password: str,
) -> None:
    """Authenticate against the portal.

    Performs a two-step login:

    1. GET ``/?md={tenant}`` — establishes the session (sets SESID, md, EXPI cookies).
    2. GET ``/index.htm?action=&node=page&username=…&password=…`` — validates credentials.

    On success, the session cookies are stored in *client* and used automatically
    for all subsequent requests.

    Args:
        client: An :class:`httpx.Client` instance whose cookie jar will be populated.
        tenant: Portal tenant identifier (e.g. ``"xy"``).
        username: Portal username.
        password: Portal password.

    Raises:
        LoginError: If either request fails or the login response does not contain
            the expected confirmation text.
    """
    referer = f"{_BASE_URL}/?md={tenant}"

    # Step 1: tenant page — establishes the session cookie.
    _log.debug("Fetching tenant page (tenant=%r)", tenant)
    try:
        r1 = client.get(f"{_BASE_URL}/", params={"md": tenant})
        r1.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LoginError(f"Tenant request failed with HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise LoginError(f"Tenant request failed: {exc}") from exc
    _log.debug("Tenant page fetched (HTTP %s)", r1.status_code)

    # Step 2: login — pass credentials via query string (portal convention).
    # NOTE: the login URL contains credentials — never log it.
    ts = int(time.time() * 1000)
    login_url = (
        f"{_BASE_URL}/index.htm"
        f"?action=&node=page"
        f"&username={quote(username, safe='')}"
        f"&password={quote(password, safe='')}"
        f"&_={ts}"
    )
    _log.debug("Sending login request (tenant=%r)", tenant)
    try:
        r2 = client.get(login_url, headers={"Referer": referer})
        r2.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LoginError(f"Login request failed with HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise LoginError(f"Login request failed: {exc}") from exc

    # The start page after a successful login contains this string.
    if "Verbrauchsinformation" not in r2.text:
        raise LoginError(
            "Login failed: credentials may be invalid or the portal returned "
            "an unexpected response."
        )
    _log.debug("Login successful (tenant=%r)", tenant)


def logout(client: httpx.Client, tenant: str) -> None:
    """Log out from the portal.

    Errors are silently suppressed — logout is best-effort only.

    Args:
        client: An authenticated :class:`httpx.Client` instance.
        tenant: Portal tenant identifier.
    """
    _log.debug("Logging out (tenant=%r)", tenant)
    referer = f"{_BASE_URL}/?md={tenant}"
    with contextlib.suppress(httpx.HTTPError):
        client.post(
            f"{_BASE_URL}/",
            data={"action": "logout", "node": "page"},
            headers={"Referer": referer},
        )
    _log.debug("Logout complete (tenant=%r)", tenant)
