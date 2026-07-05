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

logging.getLogger(__name__).addHandler(logging.NullHandler())

from md24de._client import Md24deClient  # noqa: E402
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
from md24de._pdf import render_consumption_report_pdf  # noqa: E402
from md24de._serialization import (  # noqa: E402
    dump_consumption_report,
    load_consumption_report,
)

__all__ = [
    # Client
    "Md24deClient",
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
