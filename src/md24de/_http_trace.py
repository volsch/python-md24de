"""HTTP request/response tracing support for :class:`~md24de.Md24deClient`.

Defines the :data:`HttpTraceCallback` type used to observe every non-authentication
HTTP request/response pair made by the client, plus a ready-to-use
:class:`FileHttpTraceLogger` default implementation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from md24de._models import HttpRequestTrace, HttpResponseTrace

_log = logging.getLogger(__name__)

_MASKED_HEADER_VALUE = "***"
_MASKED_HEADER_NAMES = frozenset({"cookie", "set-cookie"})

# Substrings of a Content-Type main-type considered textual; anything else (e.g.
# application/pdf, image/*) is treated as binary and its body is omitted from the
# trace.
_TEXTUAL_CONTENT_TYPE_MARKERS = ("text/", "json", "xml", "javascript", "urlencoded")

HttpTraceCallback = Callable[[HttpRequestTrace, "HttpResponseTrace | None"], None]
"""Callback invoked for every non-authentication HTTP request made by
:class:`~md24de.Md24deClient`.

Called exactly once per request, whether it succeeded or failed, with plain,
library-owned data — never an external HTTP-library object. Never called for the
login/logout requests, so credentials are never exposed through this callback.

Args:
    request: Snapshot of the outgoing request.
    response: Snapshot of the response, or ``None`` if no response was received at
        all (e.g. a connection error occurred before any response was received).
"""


def _headers_as_pairs(headers: httpx.Headers) -> tuple[tuple[str, str], ...]:
    """Return *headers* as multi-valued ``(name, value)`` pairs, unmasked."""
    return tuple(headers.multi_items())


def _mask_headers(
    headers: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """Return *headers* with cookie-related values masked, for display/storage."""
    return tuple(
        (name, _MASKED_HEADER_VALUE if name.lower() in _MASKED_HEADER_NAMES else value)
        for name, value in headers
    )


def _is_textual_content_type(content_type: str) -> bool:
    """Return whether *content_type* denotes textual (as opposed to binary) content."""
    main_type = content_type.split(";", 1)[0].strip().lower()
    return any(marker in main_type for marker in _TEXTUAL_CONTENT_TYPE_MARKERS)


def _decode_body(raw: bytes | None, content_type: str | None) -> str | None:
    """Decode *raw* to text if it looks textual, else return ``None``."""
    if not raw:
        return None
    if content_type is not None and not _is_textual_content_type(content_type):
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def build_request_trace(request: httpx.Request) -> HttpRequestTrace:
    """Build an :class:`HttpRequestTrace` snapshot from an :class:`httpx.Request`."""
    body = _decode_body(request.content, request.headers.get("content-type"))
    return HttpRequestTrace(
        method=request.method,
        url=str(request.url),
        headers=_headers_as_pairs(request.headers),
        body=body,
    )


def _tls_version(response: httpx.Response) -> str | None:
    """Best-effort extraction of the negotiated TLS version from *response*."""
    network_stream = response.extensions.get("network_stream")
    if network_stream is None:
        return None
    ssl_object = network_stream.get_extra_info("ssl_object")
    if ssl_object is None:
        return None
    version: str | None = ssl_object.version()
    return version


def build_response_trace(response: httpx.Response, body: bytes | None) -> HttpResponseTrace:
    """Build an :class:`HttpResponseTrace` snapshot from an :class:`httpx.Response`.

    Args:
        response: The received response; headers and status code are always
            available at this point.
        body: Raw response body bytes already read by the caller, or ``None`` if the
            body was not (fully) read, e.g. because the request failed before the
            body could be retrieved.
    """
    return HttpResponseTrace(
        status_code=response.status_code,
        headers=_headers_as_pairs(response.headers),
        body=_decode_body(body, response.headers.get("content-type")),
        tls_version=_tls_version(response),
    )


def format_http_trace(
    request: HttpRequestTrace,
    response: HttpResponseTrace | None,
    sequence: int | None = None,
) -> str:
    """Render *request*/*response* as a human-readable, timestamped text block.

    ``Cookie`` and ``Set-Cookie`` header values are masked in the rendered text
    (the trace objects themselves carry the unmasked values). Used by
    :class:`FileHttpTraceLogger`; also usable directly by callers who want to
    forward the formatted text to a different sink.

    Args:
        request: Snapshot of the outgoing request.
        response: Snapshot of the response, or ``None`` if no response was received.
        sequence: Optional 1-based request number, rendered in the block header
            (e.g. ``=== 2 === 2026-...``) to make consecutive traces easy to tell
            apart and reference.
    """
    number_prefix = f"{sequence} === " if sequence is not None else ""
    lines = [
        f"=== {number_prefix}{datetime.now(UTC).isoformat()} ===",
        f"> {request.method} {request.url}",
    ]
    lines.extend(f"> {name}: {value}" for name, value in _mask_headers(request.headers))
    if request.body is not None:
        lines.append(">")
        lines.append(request.body)
    lines.append("")
    if response is None:
        lines.append("< (no response received — request failed)")
    else:
        tls_suffix = f" [{response.tls_version}]" if response.tls_version else ""
        lines.append(f"< {response.status_code}{tls_suffix}")
        lines.extend(f"< {name}: {value}" for name, value in _mask_headers(response.headers))
        if response.body is not None:
            lines.append("<")
            lines.append(response.body)
    lines.append("")
    return "\n".join(lines)


class FileHttpTraceLogger:
    """Default :data:`HttpTraceCallback` implementation.

    Appends a timestamped, numbered, human-readable text block for every
    request/response pair to a file — e.g. for later audit or troubleshooting.
    ``Cookie`` and ``Set-Cookie`` header values are always masked (see
    :func:`format_http_trace`). Requests are numbered sequentially per
    :class:`FileHttpTraceLogger` instance, starting at 1.

    Example::

        client = Md24deClient(
            tenant="xy",
            username="…",
            ******
            options=ClientOptions(
                http_trace_callback=FileHttpTraceLogger("md24de-http-trace.log"),
            ),
        )
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._sequence = 0

    def __call__(self, request: HttpRequestTrace, response: HttpResponseTrace | None) -> None:
        self._sequence += 1
        text = format_http_trace(request, response, sequence=self._sequence)
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            _log.exception("Failed to write http trace to %s", self._path)
