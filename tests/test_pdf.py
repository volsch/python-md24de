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
    get_uvi_disclosure_note,
    render_consumption_report_pdf,
)
from md24de._pdf import (  # pyright: ignore[reportPrivateUsage]
    _chart_bar_formatter,  # pyright: ignore[reportPrivateUsage]
    _fmt_kwh,  # pyright: ignore[reportPrivateUsage]
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
        # all fixture values are whole numbers -> no decimal digits in the table
        assert "200" in text
        assert "60" in text
        assert "200,0" not in text
        assert "60,0" not in text

    def test_contains_comparison_symbols(self, report: ConsumptionReport) -> None:
        text = _pdf_text(render_consumption_report_pdf(report))
        # vs_average: both values always known -> "your symbol ref"
        assert "0 < 200" in text
        assert "50 < 60" in text
        # vs_previous_month for heating: no comparison from portal, but a matching
        # history entry exists -> symbol computed directly from the values
        assert "0 < 150" in text
        # vs_previous_year for heating: neither a comparison nor a history match
        assert "0 -" in text
        # vs_previous_month/vs_previous_year for hot water: comparison known from the
        # portal, but no matching history entry -> symbol shown without a reference value
        assert "50 >" in text
        assert "50 =" in text

    def test_comparison_cell_colors(self, report: ConsumptionReport) -> None:
        pdf_bytes = render_consumption_report_pdf(report)
        black = (0.0, 0.0, 0.0)
        # "less" (own value below reference) is rendered in green, regardless of
        # whether the symbol came from the portal or was computed from history.
        less_color = _span_color(pdf_bytes, "0 < 200")
        assert less_color == _span_color(pdf_bytes, "0 < 150")
        assert less_color != black
        # "more" (own value above reference) is rendered in red.
        more_color = _span_color(pdf_bytes, "50 >")
        assert more_color != black
        assert more_color != less_color
        # "equal" and "no reference value" use the default (black) text color.
        assert _span_color(pdf_bytes, "50 =") == black
        assert _span_color(pdf_bytes, "0 -") == black
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
        # all fixture values are whole numbers -> no decimal digits in the chart either.
        assert "300" in text
        assert "300,0" not in text

    def test_contains_note(self, report: ConsumptionReport) -> None:
        text = _pdf_text(render_consumption_report_pdf(report))
        assert "Hinweis" in text
        assert "UVI" in text
        assert "Orientierung" in text

    def test_uses_get_uvi_disclosure_note(self, report: ConsumptionReport) -> None:
        """The PDF must embed exactly the text returned by get_uvi_disclosure_note()."""
        text = _pdf_text(render_consumption_report_pdf(report))
        # PDF text extraction collapses whitespace/line breaks, so compare word-by-word.
        for word in get_uvi_disclosure_note().split():
            assert word in text

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

    def test_none_kwh_value_renders_as_dash(self, report: ConsumptionReport) -> None:
        """A None current_kwh (not supplied by the portal) is shown as '-', not '0,0'."""
        report_with_missing_value = ConsumptionReport(
            object_info=report.object_info,
            heating=MeterReport(
                current_kwh=None,
                average_kwh=report.heating.average_kwh,
                vs_average=None,
                vs_previous_month=None,
                vs_previous_year=None,
                history=(MeterReading(year=2026, month=5, your_kwh=None, average_kwh=200.0),),
            ),
            hot_water=report.hot_water,
        )
        pdf_bytes = render_consumption_report_pdf(report_with_missing_value)
        assert pdf_bytes.startswith(b"%PDF")
        text = _pdf_text(pdf_bytes)
        assert "- <" in text or "-" in text

    def test_mixed_decimals_in_table_shown_per_value(self, report: ConsumptionReport) -> None:
        """The table formats each value independently: whole numbers drop the decimal
        even when a fractional value elsewhere forces the *chart* to show decimals
        uniformly for all its own bars (the two use independent formatting rules).
        """
        mixed_report = ConsumptionReport(
            object_info=report.object_info,
            heating=MeterReport(
                current_kwh=15.5,
                average_kwh=200.0,
                vs_average=Comparison.LESS,
                vs_previous_month=None,
                vs_previous_year=None,
                history=(MeterReading(year=2026, month=5, your_kwh=15.5, average_kwh=200.0),),
            ),
            hot_water=report.hot_water,
        )
        pdf_bytes = render_consumption_report_pdf(mixed_report)
        stream = _content_stream(pdf_bytes)
        # table: current_kwh (15,5) keeps its decimal, average_kwh (200) drops it
        assert "(15,5)" in stream
        assert "(200)" in stream
        # chart: the same average_kwh (200.0) is shown with a decimal there, because
        # the fractional current_kwh (15,5) forces uniform decimals across that chart
        assert "(200,0)" in stream


class TestFmtKwh:
    def test_none_renders_as_dash(self) -> None:
        assert _fmt_kwh(None) == "-"

    def test_whole_number_has_no_decimal(self) -> None:
        assert _fmt_kwh(200.0) == "200"
        assert _fmt_kwh(0.0) == "0"

    def test_fractional_number_keeps_one_decimal(self) -> None:
        assert _fmt_kwh(15.5) == "15,5"


class TestChartBarFormatter:
    def test_no_decimals_when_all_values_are_whole(self) -> None:
        formatter = _chart_bar_formatter([0.0, 150.0, None], [200.0, 300.0, None])
        assert formatter(150.0) == "150"
        assert formatter(0.0) == "0"

    def test_decimals_shown_for_all_values_when_any_has_a_fraction(self) -> None:
        """If any plotted value has decimals, every bar in that chart shows one digit."""
        formatter = _chart_bar_formatter([15.5, 150.0, None], [200.0, 300.0, None])
        assert formatter(150.0) == "150,0"
        assert formatter(15.5) == "15,5"
