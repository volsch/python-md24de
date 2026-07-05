"""Data models for the md24de client library."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Comparison(Enum):
    """Indicates whether consumption is lower, equal to, or higher than a reference value."""

    LESS = "less"
    MORE = "more"
    EQUAL = "equal"


@dataclass(frozen=True)
class AvailableMonth:
    """A year/month combination for which consumption data is available."""

    year: int
    """Four-digit year."""

    month: int
    """Month number (1 = January … 12 = December)."""


@dataclass(frozen=True)
class MeterReading:
    """Consumption reading for a specific month including the comparable-household average."""

    year: int
    """Four-digit year."""

    month: int
    """Month number (1–12)."""

    your_kwh: float | None
    """Your own consumption in kWh äq. ``None`` if the portal did not supply a value
    for this month (distinct from an actual reading of 0 kWh)."""

    average_kwh: float | None
    """Average consumption of comparable households in kWh äq. ``None`` if the
    portal did not supply a value for this month (distinct from an actual value
    of 0 kWh)."""


@dataclass(frozen=True)
class MeterReport:
    """Full consumption report for one meter type (heating or hot water)."""

    current_kwh: float | None
    """Your consumption for the current month in kWh äq. ``None`` if the portal
    did not supply a value (distinct from an actual reading of 0 kWh)."""

    average_kwh: float | None
    """Average consumption of comparable households for the current month in kWh äq.
    ``None`` if the portal did not supply a value (distinct from an actual value of 0 kWh)."""

    vs_average: Comparison | None
    """How your consumption compares to comparable households this month.
    ``None`` if the portal does not provide this comparison."""

    vs_previous_month: Comparison | None
    """How your consumption compares to the previous month.
    ``None`` if the portal does not provide this comparison."""

    vs_previous_year: Comparison | None
    """How your consumption compares to the same month of the previous year.
    ``None`` if the portal does not provide this comparison."""

    history: tuple[MeterReading, ...]
    """Historical readings shown in the bar chart, newest first."""


@dataclass(frozen=True)
class ObjectInfo:
    """Information about the metered object (apartment / building)."""

    object_number: str
    """Object number assigned by the service provider."""

    address: str
    """Street address of the metered object."""


@dataclass(frozen=True)
class HttpRequestTrace:
    """Snapshot of an outgoing HTTP request, passed to an ``HttpTraceCallback``.

    Never produced for the login/logout requests, so credentials are never exposed
    through this type.
    """

    method: str
    """HTTP method, e.g. ``"GET"`` or ``"POST"``."""

    url: str
    """Complete request URL, including any query parameters."""

    headers: tuple[tuple[str, str], ...]
    """Request headers as ``(name, value)`` pairs, unmasked. A header name may appear
    more than once if it was sent multiple times. Callers that persist or display
    these headers should mask the ``Cookie`` value themselves; the default
    ``format_http_trace``/``FileHttpTraceLogger`` implementation does this."""

    body: str | None
    """Textual request body, or ``None`` if the request has no body, or the body is
    not textual."""


@dataclass(frozen=True)
class HttpResponseTrace:
    """Snapshot of an HTTP response, passed to an ``HttpTraceCallback``."""

    status_code: int
    """HTTP status code."""

    headers: tuple[tuple[str, str], ...]
    """Response headers as ``(name, value)`` pairs, unmasked. A header name may
    appear more than once if it was sent multiple times (e.g. ``Set-Cookie``).
    Callers that persist or display these headers should mask the ``Set-Cookie``
    value themselves; the default ``format_http_trace``/``FileHttpTraceLogger``
    implementation does this."""

    body: str | None
    """Textual response body, or ``None`` if the body is not textual or was not
    (fully) read, e.g. because the request failed."""

    tls_version: str | None
    """Negotiated TLS protocol version (e.g. ``"TLSv1.3"``), or ``None`` if the
    connection was not encrypted or the version could not be determined."""


@dataclass(frozen=True)
class ConsumptionReport:
    """Full consumption report as returned by the portal.

    The report does not carry a top-level ``year`` or ``month`` field.  The
    covered period is available per-reading in :attr:`MeterReport.history`
    (``history[0]`` is the last available month at the time the report was
    fetched).  Use :meth:`~md24de.Md24deClient.get_last_available_month` if
    you need the month without parsing the full report — note that it reflects
    the state at login time.
    """

    object_info: ObjectInfo
    """Information about the metered object."""

    heating: MeterReport
    """Heating consumption data."""

    hot_water: MeterReport
    """Hot-water consumption data."""
