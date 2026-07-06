"""Md24deClient — the main entry point for the md24de library."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from types import TracebackType

import httpx

from md24de._auth import login, logout
from md24de._exceptions import Md24deError, ParseError
from md24de._http_trace import HttpTraceCallback, build_request_trace, build_response_trace
from md24de._models import (
    AvailableMonth,
    ConsumptionReport,
)
from md24de._parser import parse_available_month, parse_consumption_html

_BASE_URL = "https://legacy.messdienst24.de"

# Hard cap on how many bytes any single response may contain.
# Protects against a slow-drip server holding the connection open indefinitely
# by returning data in tiny chunks — each within the per-read socket timeout —
# while never finishing the response body.  2 MB is well above the largest
# expected HTML page or PDF document from this portal.
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB

_log = logging.getLogger(__name__)

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
    "Cache-Control": "no-cache, no-store",
}


@dataclass(frozen=True)
class ClientOptions:
    """Optional settings for :class:`Md24deClient`, grouped to leave room for
    future additions without growing the constructor's parameter list."""

    timeout: float = 30.0
    """HTTP request timeout in seconds."""

    http_trace_callback: HttpTraceCallback | None = None
    """Optional callback invoked for every non-authentication HTTP request/response
    pair (see :data:`~md24de.HttpTraceCallback`). Called exactly once per request,
    even if it fails. Never called for the login/logout requests, so credentials
    are never exposed through it. Use :class:`~md24de.FileHttpTraceLogger` for a
    ready-to-use implementation that appends a timestamped trace to a file."""


class Md24deClient:
    """Client for the messdienst24.de utility-consumption portal.

    On construction the client logs in, fetches the consumption page, and
    extracts the available month from plain text — no Chart.js processing.
    The full :class:`ConsumptionReport` is parsed lazily on the first call to
    :meth:`get_consumption_report`.

    Use as a context manager to ensure the session is always closed::

        with Md24deClient(tenant="xy", username="…", password="…") as client:
            report = client.get_consumption_report()

    .. warning::
        The portal may terminate the session after a fixed period regardless
        of recent activity (server-side absolute timeout).  Any method call
        after the session has expired will raise :class:`Md24deError` or
        return an unexpected response.  For long-running processes, create a
        new client instance for each retrieval.

    Args:
        tenant: Portal tenant identifier (e.g. ``"xy"``).
        username: Portal username.
        password: Portal password.
        options: Optional settings (timeout, HTTP trace callback, …). See
            :class:`ClientOptions`. Defaults to ``ClientOptions()`` if omitted.

    Raises:
        LoginError: If authentication fails.
        ParseError: If the available month cannot be determined from the page.
    """

    def __init__(
        self,
        *,
        tenant: str,
        username: str,
        password: str,
        options: ClientOptions | None = None,
    ) -> None:
        options = options if options is not None else ClientOptions()
        self._tenant = tenant
        self._http_trace_callback = options.http_trace_callback
        self._http = httpx.Client(
            headers=_DEFAULT_HEADERS,
            timeout=options.timeout,
            follow_redirects=True,
        )
        # Populated lazily on the first get_consumption_report() call.
        self._report: ConsumptionReport | None = None
        try:
            login(self._http, tenant, username, password)
            self._consumption_html = self._fetch_consumption_html()
            self._available_month = parse_available_month(self._consumption_html)
        except Exception:
            self._http.close()
            raise
        _log.debug(
            "Client ready — available month: %04d-%02d",
            self._available_month.year,
            self._available_month.month,
        )

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> Md24deClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Log out and close the underlying HTTP connection."""
        _log.debug("Closing client (tenant=%r)", self._tenant)
        try:
            logout(self._http, self._tenant)
        finally:
            self._http.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_last_available_month(self) -> AvailableMonth:
        """Return the most recent month for which consumption data is available.

        This information is available immediately after construction with no
        additional parsing cost.

        Returns:
            The single :class:`AvailableMonth` the portal currently provides.
        """
        return self._available_month

    def get_consumption_report(self) -> ConsumptionReport:
        """Return the structured consumption report for the available month.

        The first call parses the Chart.js data from the cached consumption page
        HTML and stores the result.  Subsequent calls return the cached report
        with no additional work.

        Returns:
            A :class:`ConsumptionReport` for the currently available month.

        Raises:
            ParseError: If the consumption page cannot be fully parsed.
        """
        if self._report is None:
            _log.debug("Parsing consumption report")
            self._report = parse_consumption_html(self._consumption_html)
        else:
            _log.debug("Returning cached consumption report")
        return self._report

    def get_pdf(self) -> bytes:
        """Download and return the raw PDF bytes for the available month.

        Each call makes a fresh HTTP request to the portal.

        Returns:
            Raw PDF binary content.

        Raises:
            Md24deError: If the HTTP request fails or the response is not a valid PDF.
        """

        _log.debug(
            "Downloading PDF (%04d-%02d)",
            self._available_month.year,
            self._available_month.month,
        )
        referer = f"{_BASE_URL}/?md={self._tenant}"
        try:
            content = self._traced_stream_request(
                "GET",
                f"{_BASE_URL}/",
                params={"format": "pdf"},
                headers={"Referer": referer},
                label="PDF",
            )
        except httpx.HTTPStatusError as exc:
            raise Md24deError(f"PDF download failed with HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise Md24deError(f"PDF download failed: {exc}") from exc

        if not content.startswith(b"%PDF-"):
            raise ParseError("Portal response is not a valid PDF")

        _log.debug("PDF downloaded (%d bytes)", len(content))
        return content

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_consumption_html(self) -> str:
        """POST to the consumption endpoint and return the response HTML."""
        _log.debug("Fetching consumption HTML")
        referer = f"{_BASE_URL}/?md={self._tenant}"
        try:
            raw = self._traced_stream_request(
                "POST",
                f"{_BASE_URL}/",
                data={"action": "objverbmiet", "node": "content"},
                headers={"Referer": referer},
                label="Consumption page",
            )
        except httpx.HTTPStatusError as exc:
            raise Md24deError(
                f"Consumption page request failed with HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise Md24deError(f"Consumption page request failed: {exc}") from exc
        _log.debug("Consumption HTML fetched (%d bytes)", len(raw))
        return raw.decode(errors="replace")

    def _traced_stream_request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        label: str,
    ) -> bytes:
        """Send a streamed, size-limited HTTP request and return its raw body.

        If an ``http_trace_callback`` was configured, it is invoked exactly once
        with a snapshot of the request and (if any) response — regardless of
        whether the request succeeded or failed. Must never be used for the
        login/logout requests.
        """
        request = self._http.build_request(method, url, params=params, data=data, headers=headers)
        req_trace = (
            build_request_trace(request) if self._http_trace_callback is not None else None
        )
        resp: httpx.Response | None = None
        body: bytes | None = None
        try:
            resp = self._http.send(request, stream=True)
            try:
                resp.raise_for_status()
                body = self._read_limited(resp, label)
            finally:
                resp.close()
            return body
        finally:
            if req_trace is not None and self._http_trace_callback is not None:
                resp_trace = build_response_trace(resp, body) if resp is not None else None
                self._http_trace_callback(req_trace, resp_trace)

    @staticmethod
    def _read_limited(resp: httpx.Response, label: str) -> bytes:
        """Read *resp* body up to _MAX_RESPONSE_BYTES; raise Md24deError if exceeded."""
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_bytes():
            total += len(chunk)
            if total > _MAX_RESPONSE_BYTES:
                raise Md24deError(
                    f"{label} response exceeds {_MAX_RESPONSE_BYTES // (1024 * 1024)} MB limit"
                )
            chunks.append(chunk)
        return b"".join(chunks)
