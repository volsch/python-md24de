"""md24de — unofficial Python client for the messdienst24.de portal.

Example usage::

    from md24de import Md24deClient, Comparison

    with Md24deClient(tenant="xy", username="…", password="…") as client:
        month = client.get_last_available_month()
        report = client.get_consumption_report()

        print(report.heating.current_kwh)   # e.g. 0.0
        print(report.hot_water.vs_average)  # e.g. Comparison.LESS

        pdf_bytes = client.get_pdf()
        Path("consumption.pdf").write_bytes(pdf_bytes)

Session-independent helpers -- operate on an already-parsed
:class:`ConsumptionReport`, no portal access required::

    from md24de import (
        dump_consumption_report,
        load_consumption_report,
        render_consumption_report_pdf,
    )

    json_text = dump_consumption_report(report)
    same_report = load_consumption_report(json_text)
    uvi_pdf_bytes = render_consumption_report_pdf(report)

:data:`GERMAN_MONTH_NAMES` maps month numbers (1-12) to their German names
(e.g. ``{5: "Mai"}``), for callers that need to render a German month name
without depending on the library's internal parsing logic.
"""

import logging
from typing import TYPE_CHECKING

logging.getLogger(__name__).addHandler(logging.NullHandler())

from md24de._client import ClientOptions, Md24deClient  # noqa: E402
from md24de._exceptions import (  # noqa: E402
    LoginError,
    Md24deError,
    ParseError,
)
from md24de._http_trace import (  # noqa: E402
    FileHttpTraceLogger,
    HttpTraceCallback,
    format_http_trace,
)
from md24de._models import (  # noqa: E402
    AvailableMonth,
    Comparison,
    ConsumptionReport,
    HttpRequestTrace,
    HttpResponseTrace,
    MeterReading,
    MeterReport,
    ObjectInfo,
)
from md24de._parser import GERMAN_MONTH_NAMES  # noqa: E402
from md24de._serialization import (  # noqa: E402
    dump_consumption_report,
    load_consumption_report,
)

if TYPE_CHECKING:
    # Only for static type checking — see the lazy __getattr__ below for why
    # this isn't a plain top-level import at runtime.
    from md24de._pdf import render_consumption_report_pdf


def __getattr__(name: str) -> object:
    """Lazily import :func:`render_consumption_report_pdf` on first access.

    ``reportlab`` (and its transitive ``Pillow`` dependency) is only needed
    for local PDF rendering. Loading it eagerly at ``import md24de`` time would
    force every caller to pay that cost — and bundle that native dependency —
    even if they never render a PDF (e.g. callers that only use
    :class:`Md24deClient` for HTML parsing or the JSON helpers).
    """
    if name == "render_consumption_report_pdf":
        from md24de._pdf import render_consumption_report_pdf as _render_consumption_report_pdf

        return _render_consumption_report_pdf
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Client
    "Md24deClient",
    "ClientOptions",
    # Models
    "AvailableMonth",
    "Comparison",
    "ConsumptionReport",
    "HttpRequestTrace",
    "HttpResponseTrace",
    "MeterReading",
    "MeterReport",
    "ObjectInfo",
    # Constants
    "GERMAN_MONTH_NAMES",
    # HTTP tracing
    "FileHttpTraceLogger",
    "HttpTraceCallback",
    "format_http_trace",
    # Session-independent helpers
    "dump_consumption_report",
    "load_consumption_report",
    "render_consumption_report_pdf",
    # Exceptions
    "Md24deError",
    "LoginError",
    "ParseError",
]
