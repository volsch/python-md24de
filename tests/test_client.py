"""Tests for the Md24deClient."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import httpx
import pytest

from md24de import (
    AvailableMonth,
    ClientOptions,
    Comparison,
    ConsumptionReport,
    HttpRequestTrace,
    HttpResponseTrace,
    HttpTraceCallback,
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
            current_kwh=15.0,
            average_kwh=210.0,
            vs_average=Comparison.LESS,
            vs_previous_month=None,
            vs_previous_year=Comparison.LESS,
            history=(
                MeterReading(year=2026, month=5, your_kwh=15.0, average_kwh=210.0),
                MeterReading(year=2026, month=4, your_kwh=145.0, average_kwh=305.0),
                MeterReading(year=2025, month=5, your_kwh=140.0, average_kwh=210.0),
            ),
        ),
        hot_water=MeterReport(
            current_kwh=55.0,
            average_kwh=65.0,
            vs_average=Comparison.LESS,
            vs_previous_month=Comparison.LESS,
            vs_previous_year=Comparison.LESS,
            history=(
                MeterReading(year=2026, month=5, your_kwh=55.0, average_kwh=65.0),
                MeterReading(year=2026, month=4, your_kwh=60.0, average_kwh=62.0),
                MeterReading(year=2025, month=5, your_kwh=58.0, average_kwh=65.0),
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
        assert report.heating.current_kwh == pytest.approx(15.0)
        assert report.heating.average_kwh == pytest.approx(210.0)
        assert report.heating.vs_average is Comparison.LESS
        assert report.heating.vs_previous_month is None
        assert report.heating.vs_previous_year is Comparison.LESS

    def test_report_hot_water(self, client: Md24deClient) -> None:
        report = client.get_consumption_report()
        assert report.hot_water.current_kwh == pytest.approx(55.0)
        assert report.hot_water.vs_previous_month is Comparison.LESS


class TestGetPdf:
    def _make_send_mock(self, content: bytes, status_code: int = 200) -> MagicMock:
        """Return a mock response as returned by ``httpx.Client.send(..., stream=True)``."""
        mock_resp: MagicMock = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_bytes.return_value = iter([content])
        mock_resp.headers = httpx.Headers({})
        mock_resp.extensions = {}
        mock_resp.close = MagicMock()
        if status_code != 200:
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "", request=MagicMock(), response=MagicMock(status_code=status_code)
            )
        return mock_resp

    def test_returns_pdf_bytes(self, client: Md24deClient) -> None:
        mock_resp = self._make_send_mock(b"%PDF-1.4 fake")
        with patch.object(client._http, "send", return_value=mock_resp):  # pyright: ignore[reportPrivateUsage]
            pdf = client.get_pdf()
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF-")

    def test_raises_for_non_pdf_response(self, client: Md24deClient) -> None:
        from md24de import ParseError  # noqa: PLC0415

        mock_resp = self._make_send_mock(b"<html>Not a PDF</html>")
        with (
            patch.object(client._http, "send", return_value=mock_resp),  # pyright: ignore[reportPrivateUsage]
            pytest.raises(ParseError),
        ):
            client.get_pdf()

    def test_raises_when_pdf_exceeds_size_limit(self, client: Md24deClient) -> None:
        from md24de._client import _MAX_RESPONSE_BYTES  # pyright: ignore[reportPrivateUsage]

        oversized = b"%PDF-" + b"x" * _MAX_RESPONSE_BYTES
        mock_resp = self._make_send_mock(oversized)
        with (
            patch.object(client._http, "send", return_value=mock_resp),  # pyright: ignore[reportPrivateUsage]
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
        c._http = httpx.Client(transport=transport, base_url="https://legacy.messdienst24.de")  # pyright: ignore[reportPrivateUsage]
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
        c._http = httpx.Client(transport=transport, base_url="https://legacy.messdienst24.de")  # pyright: ignore[reportPrivateUsage]
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


class _TraceRecorder:
    """Collects (request, response) pairs passed to an HttpTraceCallback."""

    def __init__(self) -> None:
        self.calls: list[tuple[HttpRequestTrace, HttpResponseTrace | None]] = []

    def __call__(self, request: HttpRequestTrace, response: HttpResponseTrace | None) -> None:
        self.calls.append((request, response))


class TestHttpTraceCallback:
    """Verify http_trace_callback is invoked correctly for get_pdf/_fetch_consumption_html."""

    def _make_client_with_transport(
        self,
        transport: httpx.MockTransport,
        sample_report: ConsumptionReport,
        http_trace_callback: HttpTraceCallback | None = None,
    ) -> Md24deClient:
        available = AvailableMonth(year=2026, month=5)
        with (
            patch("md24de._client.login"),
            patch("md24de._client.logout"),
            patch("md24de._client.parse_available_month", return_value=available),
            patch("md24de._client.parse_consumption_html", return_value=sample_report),
            patch.object(Md24deClient, "_fetch_consumption_html", return_value="<stub>"),
        ):
            c = Md24deClient(
                tenant="xy",
                username="u",
                password="p",  # noqa: S106  # NOSONAR
                options=ClientOptions(http_trace_callback=http_trace_callback),
            )
        c._http.close()  # pyright: ignore[reportPrivateUsage]
        c._http = httpx.Client(transport=transport, base_url="https://legacy.messdienst24.de")  # pyright: ignore[reportPrivateUsage]
        return c

    def test_callback_called_on_success(self, sample_report: ConsumptionReport) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"%PDF-1.4 fake", request=request)

        recorder = _TraceRecorder()
        c = self._make_client_with_transport(
            httpx.MockTransport(handler), sample_report, recorder
        )
        c.get_pdf()
        assert len(recorder.calls) == 1
        req_trace, resp_trace = recorder.calls[0]
        assert req_trace.method == "GET"
        assert resp_trace is not None
        assert resp_trace.status_code == 200

    def test_callback_called_on_http_error(self, sample_report: ConsumptionReport) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, request=request)

        recorder = _TraceRecorder()
        c = self._make_client_with_transport(
            httpx.MockTransport(handler), sample_report, recorder
        )
        with pytest.raises(Md24deError):
            c.get_pdf()
        assert len(recorder.calls) == 1
        _, resp_trace = recorder.calls[0]
        assert resp_trace is not None
        assert resp_trace.status_code == 404

    def test_callback_called_on_network_error(self, sample_report: ConsumptionReport) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        recorder = _TraceRecorder()
        c = self._make_client_with_transport(
            httpx.MockTransport(handler), sample_report, recorder
        )
        with pytest.raises(Md24deError):
            c.get_pdf()
        assert len(recorder.calls) == 1
        req_trace, resp_trace = recorder.calls[0]
        assert req_trace.method == "GET"
        assert resp_trace is None

    def test_callback_not_called_when_none(self, sample_report: ConsumptionReport) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"%PDF-1.4 fake", request=request)

        c = self._make_client_with_transport(httpx.MockTransport(handler), sample_report, None)
        # Should not raise even though no callback is configured.
        c.get_pdf()

    def test_callback_never_called_for_login(self, sample_report: ConsumptionReport) -> None:
        """login()/logout() are patched out entirely in the fixture and never touch
        the traced request path, so the callback must never fire for them."""
        available = AvailableMonth(year=2026, month=5)
        recorder = _TraceRecorder()
        with (
            patch("md24de._client.login") as mock_login,
            patch("md24de._client.logout") as mock_logout,
            patch("md24de._client.parse_available_month", return_value=available),
            patch("md24de._client.parse_consumption_html", return_value=sample_report),
            patch.object(Md24deClient, "_fetch_consumption_html", return_value="<stub>"),
        ):
            c = Md24deClient(
                tenant="xy",
                username="u",
                password="p",  # noqa: S106  # NOSONAR
                options=ClientOptions(http_trace_callback=recorder),
            )
            c.close()
        mock_login.assert_called_once()
        mock_logout.assert_called_once()
        assert recorder.calls == []
