"""Tests for the Md24deClient."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import httpx
import pytest

from md24de import (
    AvailableMonth,
    Comparison,
    ConsumptionReport,
    Md24deClient,
    Md24deError,
    MeterReading,
    MeterReport,
    ObjectInfo,
)


@pytest.fixture
def sample_report() -> ConsumptionReport:
    """A fully populated ConsumptionReport for May 2026."""
    return ConsumptionReport(
        object_info=ObjectInfo(
            object_number="000-000000",
            address="Musterstraße 1, 12345 Musterstadt",
        ),
        heating=MeterReport(
            current_kwh=0.0,
            average_kwh=134.0,
            vs_average=Comparison.LESS,
            vs_previous_month=None,
            vs_previous_year=Comparison.LESS,
            history=(
                MeterReading(year=2026, month=5, your_kwh=0.0, average_kwh=134.0),
                MeterReading(year=2026, month=4, your_kwh=132.0, average_kwh=269.0),
                MeterReading(year=2025, month=5, your_kwh=128.0, average_kwh=134.0),
            ),
        ),
        hot_water=MeterReport(
            current_kwh=82.0,
            average_kwh=94.0,
            vs_average=Comparison.LESS,
            vs_previous_month=Comparison.LESS,
            vs_previous_year=Comparison.LESS,
            history=(
                MeterReading(year=2026, month=5, your_kwh=82.0, average_kwh=94.0),
                MeterReading(year=2026, month=4, your_kwh=103.0, average_kwh=91.0),
                MeterReading(year=2025, month=5, your_kwh=115.0, average_kwh=94.0),
            ),
        ),
    )


@pytest.fixture
def client(sample_report: ConsumptionReport) -> Generator[Md24deClient]:
    """A Md24deClient with all HTTP layer calls mocked out."""
    available = AvailableMonth(year=2026, month=5)
    with (
        patch("md24de._client.login"),
        patch("md24de._client.logout"),
        patch("md24de._client.parse_available_month", return_value=available),
        patch("md24de._client.parse_consumption_html", return_value=sample_report),
        patch.object(Md24deClient, "_fetch_consumption_html", return_value="<stub>"),
    ):
        c = Md24deClient(tenant="xy", username="user", password="pass")  # noqa: S106  # NOSONAR
        yield c
        c.close()


class TestGetLastAvailableMonth:
    def test_returns_available_month(self, client: Md24deClient) -> None:
        month = client.get_last_available_month()
        assert isinstance(month, AvailableMonth)

    def test_correct_month_and_year(self, client: Md24deClient) -> None:
        month = client.get_last_available_month()
        assert month.month == 5
        assert month.year == 2026


class TestGetConsumptionReport:
    def test_returns_report(self, client: Md24deClient, sample_report: ConsumptionReport) -> None:
        report = client.get_consumption_report()
        assert report is sample_report

    def test_report_object_info(self, client: Md24deClient) -> None:
        report = client.get_consumption_report()
        assert report.object_info.object_number == "000-000000"

    def test_report_heating(self, client: Md24deClient) -> None:
        report = client.get_consumption_report()
        assert report.heating.current_kwh == pytest.approx(0.0)
        assert report.heating.average_kwh == pytest.approx(134.0)
        assert report.heating.vs_average is Comparison.LESS
        assert report.heating.vs_previous_month is None
        assert report.heating.vs_previous_year is Comparison.LESS

    def test_report_hot_water(self, client: Md24deClient) -> None:
        report = client.get_consumption_report()
        assert report.hot_water.current_kwh == pytest.approx(82.0)
        assert report.hot_water.vs_previous_month is Comparison.LESS


class TestGetPdf:
    def _make_stream_mock(self, content: bytes, status_code: int = 200) -> MagicMock:
        """Return a mock context-manager response that streams *content* in one chunk."""
        mock_resp: MagicMock = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_bytes.return_value = iter([content])
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        if status_code != 200:
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "", request=MagicMock(), response=MagicMock(status_code=status_code)
            )
        return mock_resp

    def test_returns_pdf_bytes(self, client: Md24deClient) -> None:
        mock_resp = self._make_stream_mock(b"%PDF-1.4 fake")
        with patch.object(client._http, "stream", return_value=mock_resp):  # pyright: ignore[reportPrivateUsage]
            pdf = client.get_pdf()
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF-")

    def test_raises_for_non_pdf_response(self, client: Md24deClient) -> None:
        from md24de import ParseError  # noqa: PLC0415

        mock_resp = self._make_stream_mock(b"<html>Not a PDF</html>")
        with (
            patch.object(client._http, "stream", return_value=mock_resp),  # pyright: ignore[reportPrivateUsage]
            pytest.raises(ParseError),
        ):
            client.get_pdf()

    def test_raises_when_pdf_exceeds_size_limit(self, client: Md24deClient) -> None:
        from md24de._client import _MAX_RESPONSE_BYTES  # pyright: ignore[reportPrivateUsage]

        oversized = b"%PDF-" + b"x" * _MAX_RESPONSE_BYTES
        mock_resp = self._make_stream_mock(oversized)
        with (
            patch.object(client._http, "stream", return_value=mock_resp),  # pyright: ignore[reportPrivateUsage]
            pytest.raises(Md24deError, match="2 MB limit"),
        ):
            client.get_pdf()


class TestContextManager:
    def test_enter_returns_client(self, sample_report: ConsumptionReport) -> None:
        available = AvailableMonth(year=2026, month=5)
        with (
            patch("md24de._client.login"),
            patch("md24de._client.logout"),
            patch("md24de._client.parse_available_month", return_value=available),
            patch("md24de._client.parse_consumption_html", return_value=sample_report),
            patch.object(Md24deClient, "_fetch_consumption_html", return_value="<stub>"),
            Md24deClient(tenant="xy", username="u", password="p") as c,  # noqa: S106  # NOSONAR
        ):
            assert isinstance(c, Md24deClient)

    def test_logout_called_on_exit(self, sample_report: ConsumptionReport) -> None:
        available = AvailableMonth(year=2026, month=5)
        mock_logout = MagicMock()
        with (
            patch("md24de._client.login"),
            patch("md24de._client.logout", mock_logout),
            patch("md24de._client.parse_available_month", return_value=available),
            patch("md24de._client.parse_consumption_html", return_value=sample_report),
            patch.object(Md24deClient, "_fetch_consumption_html", return_value="<stub>"),
            Md24deClient(tenant="xy", username="u", password="p"),  # noqa: S106  # NOSONAR
        ):
            pass  # logout fires on __exit__, after this block

        mock_logout.assert_called_once()


class TestHttpErrorPaths:
    """Test HTTP error handling in _fetch_consumption_html and get_pdf using MockTransport."""

    def _make_client_with_transport(
        self, transport: httpx.MockTransport, sample_report: ConsumptionReport
    ) -> Md24deClient:
        """Build a client where the internal _http session uses a custom transport."""
        available = AvailableMonth(year=2026, month=5)
        with (
            patch("md24de._client.login"),
            patch("md24de._client.logout"),
            patch("md24de._client.parse_available_month", return_value=available),
            patch("md24de._client.parse_consumption_html", return_value=sample_report),
            patch.object(Md24deClient, "_fetch_consumption_html", return_value="<stub>"),
        ):
            c = Md24deClient(tenant="xy", username="u", password="p")  # noqa: S106  # NOSONAR
        # Replace the real HTTP client with one backed by the test transport.
        c._http.close()  # pyright: ignore[reportPrivateUsage]
        c._http = httpx.Client(transport=transport, base_url="https://messdienst24.de")  # pyright: ignore[reportPrivateUsage]
        return c

    # --- _fetch_consumption_html ------------------------------------------

    def test_fetch_html_http_status_error_raises_md24deerror(
        self, sample_report: ConsumptionReport
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, request=request)

        c = self._make_client_with_transport(httpx.MockTransport(handler), sample_report)
        with pytest.raises(Md24deError, match="Consumption page request failed with HTTP 503"):
            c._fetch_consumption_html()  # pyright: ignore[reportPrivateUsage]

    def test_fetch_html_network_error_raises_md24deerror(
        self, sample_report: ConsumptionReport
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        c = self._make_client_with_transport(httpx.MockTransport(handler), sample_report)
        with pytest.raises(Md24deError, match="Consumption page request failed"):
            c._fetch_consumption_html()  # pyright: ignore[reportPrivateUsage]

    # --- get_pdf -------------------------------------------------------------

    def test_get_pdf_http_status_error_raises_md24deerror(
        self, sample_report: ConsumptionReport
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, request=request)

        c = self._make_client_with_transport(httpx.MockTransport(handler), sample_report)
        with pytest.raises(Md24deError, match="PDF download failed with HTTP 404"):
            c.get_pdf()

    def test_get_pdf_network_error_raises_md24deerror(
        self, sample_report: ConsumptionReport
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        c = self._make_client_with_transport(httpx.MockTransport(handler), sample_report)
        with pytest.raises(Md24deError, match="PDF download failed"):
            c.get_pdf()

    def test_get_pdf_non_pdf_content_raises_parse_error(
        self, sample_report: ConsumptionReport
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>not a pdf</html>", request=request)

        from md24de._exceptions import ParseError

        c = self._make_client_with_transport(httpx.MockTransport(handler), sample_report)
        with pytest.raises(ParseError, match="not a valid PDF"):
            c.get_pdf()

    def test_init_closes_http_on_login_error(self) -> None:
        """If __init__ fails, the internal HTTP client is closed."""
        from md24de._exceptions import LoginError

        with (
            pytest.raises(LoginError),
            patch("md24de._client.login", side_effect=LoginError("bad")),
        ):
            Md24deClient(tenant="xy", username="u", password="p")  # noqa: S106  # NOSONAR


class TestResponseSizeLimit:
    """Verify _read_limited rejects responses that exceed _MAX_RESPONSE_BYTES."""

    def _make_client_with_transport(
        self, transport: httpx.MockTransport, sample_report: ConsumptionReport
    ) -> Md24deClient:
        available = AvailableMonth(year=2026, month=5)
        with (
            patch("md24de._client.login"),
            patch("md24de._client.logout"),
            patch("md24de._client.parse_available_month", return_value=available),
            patch("md24de._client.parse_consumption_html", return_value=sample_report),
            patch.object(Md24deClient, "_fetch_consumption_html", return_value="<stub>"),
        ):
            c = Md24deClient(tenant="xy", username="u", password="p")  # noqa: S106  # NOSONAR
        c._http.close()  # pyright: ignore[reportPrivateUsage]
        c._http = httpx.Client(transport=transport, base_url="https://messdienst24.de")  # pyright: ignore[reportPrivateUsage]
        return c

    def test_pdf_over_limit_raises(self, sample_report: ConsumptionReport) -> None:
        from md24de._client import _MAX_RESPONSE_BYTES  # pyright: ignore[reportPrivateUsage]

        oversized = b"%PDF-" + b"x" * _MAX_RESPONSE_BYTES

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=oversized, request=request)

        c = self._make_client_with_transport(httpx.MockTransport(handler), sample_report)
        with pytest.raises(Md24deError, match="2 MB limit"):
            c.get_pdf()

    def test_html_over_limit_raises(self, sample_report: ConsumptionReport) -> None:
        from md24de._client import _MAX_RESPONSE_BYTES  # pyright: ignore[reportPrivateUsage]

        oversized = b"<html>" + b"x" * _MAX_RESPONSE_BYTES

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=oversized, request=request)

        c = self._make_client_with_transport(httpx.MockTransport(handler), sample_report)
        with pytest.raises(Md24deError, match="2 MB limit"):
            c._fetch_consumption_html()  # pyright: ignore[reportPrivateUsage]
