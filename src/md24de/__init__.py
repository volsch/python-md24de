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
"""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

from md24de._client import Md24deClient  # noqa: E402
from md24de._exceptions import (  # noqa: E402
    LoginError,
    Md24deError,
    ParseError,
)
from md24de._models import (  # noqa: E402
    AvailableMonth,
    Comparison,
    ConsumptionReport,
    MeterReading,
    MeterReport,
    ObjectInfo,
)

__all__ = [
    # Client
    "Md24deClient",
    # Models
    "AvailableMonth",
    "Comparison",
    "ConsumptionReport",
    "MeterReading",
    "MeterReport",
    "ObjectInfo",
    # Exceptions
    "Md24deError",
    "LoginError",
    "ParseError",
]
