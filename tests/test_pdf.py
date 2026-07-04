"""Tests for UVI PDF rendering."""

from __future__ import annotations

import io
import re

import pytest
from pypdf import PdfReader

from md24de import (
    Comparison,
    ConsumptionReport,
    Md24deError,
    MeterReading,
    MeterReport,
    ObjectInfo,
    render_consumption_report_pdf,
)

_RG_RE = re.compile(r"([0-9.]+) ([0-9.]+) ([0-9.]+) rg")


@pytest.fixture
def report() -> ConsumptionReport:
    return ConsumptionReport(
        object_info=ObjectInfo(
            object_number="999-000001",
            address="Musterstraße 1, 12345 Musterstadt",
        ),
        heating=MeterReport(
            current_kwh=0.0,
            average_kwh=200.0,
            vs_average=Comparison.LESS,
            vs_previous_month=None,  # portal gave no comparison, but history has the value
            vs_previous_year=None,  # neither a comparison nor a matching history entry
            history=(
                MeterReading(year=2026, month=5, your_kwh=0.0, average_kwh=200.0),
                MeterReading(year=2026, month=4, your_kwh=150.0, average_kwh=300.0),
            ),
        ),
        hot_water=MeterReport(
            current_kwh=50.0,
            average_kwh=60.0,
            vs_average=Comparison.LESS,
            # comparison known from portal, but no matching history entry to show a value
            vs_previous_month=Comparison.MORE,
            vs_previous_year=Comparison.EQUAL,
            history=(MeterReading(year=2026, month=5, your_kwh=50.0, average_kwh=60.0),),
        ),
    )


def _content_stream(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    data: bytes = reader.pages[0].get_contents().get_data()
    return data.decode("latin-1")


def _span_color(pdf_bytes: bytes, contains: str) -> tuple[float, float, float]:
    """Return the fill color (r, g, b) in effect for the text containing *contains*.

    Defaults to black if no ``rg`` fill-color operator precedes it, matching
    the PDF spec's default fill color.
    """
    stream = _content_stream(pdf_bytes)
    idx = stream.find(f"({contains}")
    if idx == -1:
        raise AssertionError(f"no text containing {contains!r} found in content stream")
    preceding_matches = list(_RG_RE.finditer(stream[:idx]))
    if not preceding_matches:
        return (0.0, 0.0, 0.0)
    red, green, blue = preceding_matches[-1].groups()
    return (round(float(red), 3), round(float(green), 3), round(float(blue), 3))


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


class TestRenderConsumptionReportPdf:
    def test_is_valid_pdf(self, report: ConsumptionReport) -> None:
        pdf_bytes = render_consumption_report_pdf(report)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_header_contains_uvi_month_and_year(self, report: ConsumptionReport) -> None:
        text = _pdf_text(render_consumption_report_pdf(report))
        assert "UVI Mai 2026" in text

    def test_no_address_or_object_number(self, report: ConsumptionReport) -> None:
        text = _pdf_text(render_consumption_report_pdf(report))
        assert report.object_info.address not in text
        assert report.object_info.object_number not in text

    def test_contains_consumption_values(self, report: ConsumptionReport) -> None:
        text = _pdf_text(render_consumption_report_pdf(report))
        assert "Heizung" in text
        assert "Warmwasser" in text
        assert "0,0" in text
        assert "200,0" in text
        assert "50,0" in text
        assert "60,0" in text

    def test_contains_comparison_symbols(self, report: ConsumptionReport) -> None:
        text = _pdf_text(render_consumption_report_pdf(report))
        # vs_average: both values always known -> "your symbol ref"
        assert "0,0 < 200,0" in text
        assert "50,0 < 60,0" in text
        # vs_previous_month for heating: no comparison from portal, but a matching
        # history entry exists -> symbol computed directly from the values
        assert "0,0 < 150,0" in text
        # vs_previous_year for heating: neither a comparison nor a history match
        assert "0,0  -" in text
        # vs_previous_month/vs_previous_year for hot water: comparison known from the
        # portal, but no matching history entry -> symbol shown without a reference value
        assert "50,0 >" in text
        assert "50,0 =" in text

    def test_comparison_cell_colors(self, report: ConsumptionReport) -> None:
        pdf_bytes = render_consumption_report_pdf(report)
        black = (0.0, 0.0, 0.0)
        # "less" (own value below reference) is rendered in green, regardless of
        # whether the symbol came from the portal or was computed from history.
        less_color = _span_color(pdf_bytes, "0,0 < 200,0")
        assert less_color == _span_color(pdf_bytes, "0,0 < 150,0")
        assert less_color != black
        # "more" (own value above reference) is rendered in red.
        more_color = _span_color(pdf_bytes, "50,0 >")
        assert more_color != black
        assert more_color != less_color
        # "equal" and "no reference value" use the default (black) text color.
        assert _span_color(pdf_bytes, "50,0 =") == black
        assert _span_color(pdf_bytes, "0,0  -") == black
        # the legend itself uses the same colors for its "<"/">" segments.
        assert _span_color(pdf_bytes, "< weniger") == less_color
        assert _span_color(pdf_bytes, "> mehr") == more_color

    def test_contains_bar_charts(self, report: ConsumptionReport) -> None:
        text = _pdf_text(render_consumption_report_pdf(report))
        # both meter charts are present with the expected period labels …
        assert "Mai 2026" in text
        assert "April 2026" in text
        assert "Mai 2025" in text
        # … and the legend below each chart.
        assert "Ihr Verbrauch" in text
        assert "Vergleichshaushalte" in text
        # the previous month's reference (average) value for heating is only
        # ever shown in the chart, not in any table -> proves the chart data
        # (not just its axis labels) made it into the rendered page.
        assert "300,0" in text

    def test_contains_note(self, report: ConsumptionReport) -> None:
        text = _pdf_text(render_consumption_report_pdf(report))
        assert "Hinweis" in text
        assert "Heizkostenverordnung" in text
        assert "UVI" in text

    def test_no_history_raises_md24de_error(self) -> None:
        empty_meter = MeterReport(
            current_kwh=0.0,
            average_kwh=0.0,
            vs_average=None,
            vs_previous_month=None,
            vs_previous_year=None,
            history=(),
        )
        report = ConsumptionReport(
            object_info=ObjectInfo(object_number="", address=""),
            heating=empty_meter,
            hot_water=empty_meter,
        )
        with pytest.raises(Md24deError):
            render_consumption_report_pdf(report)
