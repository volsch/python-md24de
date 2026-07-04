"""Session-independent PDF rendering for a parsed ConsumptionReport (UVI)."""

from __future__ import annotations

import io
import logging
from collections.abc import Callable

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from md24de._exceptions import Md24deError
from md24de._models import Comparison, ConsumptionReport, MeterReading, MeterReport
from md24de._parser import GERMAN_MONTH_NAMES

_log = logging.getLogger(__name__)

_MARGIN = 50.0

_FONT = "Helvetica"
_HEADER_FONT_SIZE = 18.0
_TABLE_TITLE_FONT_SIZE = 11.0
_TABLE_FONT_SIZE = 10.0
_NOTE_FONT_SIZE = 8.5

_TEXT_COLOR = colors.black
_LINE_COLOR = colors.Color(0.6, 0.6, 0.6)
_LESS_COLOR = colors.HexColor("#007300")  # green: your value is lower than the reference
_MORE_COLOR = colors.HexColor("#bf0000")  # red: your value is higher than the reference

# Bar chart geometry: two charts side by side, reusing the same content width as
# the tables below (col widths sum to 483.28, matching the frame's available width).
_CHART_DRAWING_WIDTH = 234.0
_CHART_DRAWING_HEIGHT = 160.0
_CHART_FONT_SIZE = 7.0

_COMPARISON_SYMBOLS: dict[Comparison, str] = {
    Comparison.LESS: "<",
    Comparison.MORE: ">",
    Comparison.EQUAL: "=",
}

# Condensed version of the mandatory § 6a HeizkostenV disclosure text.
_NOTE_TITLE = "Hinweis:"
_NOTE_TEXT = (
    'Die Heizungs- und Warmwasserverbräuche wurden mit den zum Ablesezeitpunkt empfangenen '
    "Werten berechnet und gemäß § 6a Heizkostenverordnung in kWh angegeben. Die unterjährige "
    'Verbrauchsinformation ("UVI") ersetzt keine Abrechnung und ist für die monatliche '
    "Abrechnung nicht geeignet; auf ihrer Grundlage können Heizkostenvorschüsse weder angehoben "
    "noch gekürzt werden. Die Jahresendabrechnung kann aufgrund von Umlageschlüsseln und "
    "Korrekturwerten von den hier dargestellten Werten abweichen; ihre formelle und materielle "
    "Wirksamkeit bleibt von eventuellen Fehlern in der UVI unberührt. Die Aufsummierung der UVI "
    "über das Jahr ergibt weder den Jahresverbrauch noch einen Hinweis auf die Kostenentwicklung."
)


def render_consumption_report_pdf(report: ConsumptionReport) -> bytes:
    """Render a simplified UVI (Unterjährige Verbrauchsinformation) PDF for *report*.

    The rendered document contains neither the address nor the object number
    of the metered object — only the period, the required consumption
    values, the comparison results and the mandatory § 6a HeizkostenV notice.
    This function does not require an active session — it only operates on
    an already-parsed :class:`ConsumptionReport`.

    Args:
        report: The consumption report to render.

    Returns:
        Raw PDF binary content.

    Raises:
        Md24deError: If *report* has no history entries to determine the
            covered period from.
    """
    year, month = _current_period(report)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=f"UVI {GERMAN_MONTH_NAMES[month]} {year:04d}",
    )
    story: list[Flowable] = [
        *_build_header(year, month),
        *_build_charts(report, year, month),
        *_build_values_table(report),
        *_build_comparison_table(report, year, month),
        *_build_note(),
    ]
    doc.build(story)  # pyright: ignore[reportUnknownMemberType]

    pdf_bytes = buffer.getvalue()
    _log.debug("Rendered UVI PDF for %04d-%02d (%d bytes)", year, month, len(pdf_bytes))
    return pdf_bytes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _current_period(report: ConsumptionReport) -> tuple[int, int]:
    """Return the (year, month) covered by *report*, from the newest history entry."""
    for meter in (report.heating, report.hot_water):
        if meter.history:
            return meter.history[0].year, meter.history[0].month
    raise Md24deError("Consumption report has no history entries to determine the period from")


def _build_header(year: int, month: int) -> list[Flowable]:
    title = f"UVI {GERMAN_MONTH_NAMES[month]} {year:04d}"
    style = ParagraphStyle(
        name="Header",
        fontName=_FONT,
        fontSize=_HEADER_FONT_SIZE,
        leading=_HEADER_FONT_SIZE * 1.2,
    )
    return [Paragraph(title, style), Spacer(1, 24.0)]


def _build_charts(report: ConsumptionReport, year: int, month: int) -> list[Flowable]:
    """Build the Heizung/Warmwasser bar charts, placed side by side.

    Each chart compares "Ihr Verbrauch" against "Vergleichshaushalte" for the
    current period, the previous month and the same month of the previous
    year. Bars for periods without a value (no matching history entry) are
    simply omitted.
    """
    heating_chart = _build_meter_chart("Heizung (kWh äq)", report.heating, year, month)
    hot_water_chart = _build_meter_chart("Warmwasser (kWh äq)", report.hot_water, year, month)
    charts_table = Table(
        [[heating_chart, hot_water_chart]],
        colWidths=[_CHART_DRAWING_WIDTH + 8.0, _CHART_DRAWING_WIDTH + 8.0],
        style=TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        ),  # pyright: ignore[reportArgumentType]
        hAlign="LEFT",
    )
    return [charts_table, Spacer(1, 28.0)]


def _build_meter_chart(title: str, meter: MeterReport, year: int, month: int) -> list[Flowable]:
    """Build one meter's titled chart: title, grouped bar chart and a small legend."""
    labels = _chart_period_labels(year, month)
    your_values, ref_values = _chart_values(meter, year, month)

    drawing = Drawing(_CHART_DRAWING_WIDTH, _CHART_DRAWING_HEIGHT)
    chart = VerticalBarChart()
    chart.x = 30
    chart.y = 20
    chart.width = int(_CHART_DRAWING_WIDTH - 40)
    chart.height = int(_CHART_DRAWING_HEIGHT - 46)
    chart.data = [your_values, ref_values]
    chart.categoryAxis.categoryNames = list(labels)
    chart.categoryAxis.labels.fontName = _FONT
    chart.categoryAxis.labels.fontSize = _CHART_FONT_SIZE
    chart.valueAxis.labels.fontName = _FONT
    chart.valueAxis.labels.fontSize = _CHART_FONT_SIZE
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = _TEXT_COLOR
    chart.bars[1].fillColor = _LINE_COLOR
    chart.barLabelFormat = _fmt_kwh
    chart.barLabels.fontName = _FONT
    chart.barLabels.fontSize = _CHART_FONT_SIZE
    chart.barLabels.nudge = 6
    chart.groupSpacing = 10
    drawing.add(chart)

    title_style = ParagraphStyle(name="ChartTitle", fontName=_FONT, fontSize=_TABLE_TITLE_FONT_SIZE)
    legend_style = ParagraphStyle(name="ChartLegend", fontName=_FONT, fontSize=_NOTE_FONT_SIZE)
    gap = "&nbsp;" * 4
    legend_text = (
        f'<font color="{_to_hex(_TEXT_COLOR)}">\u25a0 Ihr Verbrauch</font>'
        f"{gap}"
        f'<font color="{_to_hex(_LINE_COLOR)}">\u25a0 Vergleichshaushalte</font>'
    )
    return [
        Paragraph(title, title_style),
        Spacer(1, 6.0),
        drawing,
        Spacer(1, 4.0),
        Paragraph(legend_text, legend_style),
    ]


def _period_label(year: int, month: int) -> str:
    return f"{GERMAN_MONTH_NAMES[month]} {year:04d}"


def _chart_period_labels(year: int, month: int) -> tuple[str, str, str]:
    """Return the (current, previous month, same month previous year) chart labels."""
    prev_month_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    return (
        _period_label(year, month),
        _period_label(prev_month_year, prev_month),
        _period_label(year - 1, month),
    )


def _chart_values(
    meter: MeterReport, year: int, month: int
) -> tuple[list[float | None], list[float | None]]:
    """Return the (your values, reference values) series for the three chart categories."""
    prev_month_reading = _history_reading(meter, _is_previous_month(year, month))
    prev_year_reading = _history_reading(meter, _is_same_month_previous_year(year, month))
    your_values = [
        meter.current_kwh,
        prev_month_reading.your_kwh if prev_month_reading is not None else None,
        prev_year_reading.your_kwh if prev_year_reading is not None else None,
    ]
    ref_values = [
        meter.average_kwh,
        prev_month_reading.average_kwh if prev_month_reading is not None else None,
        prev_year_reading.average_kwh if prev_year_reading is not None else None,
    ]
    return your_values, ref_values


def _build_values_table(report: ConsumptionReport) -> list[Flowable]:
    """Build the table with the values required by the German UVI (§ 6a HeizkostenV)."""
    headers = ("", "Ihr Verbrauch (kWh äq)", "Vergleichshaushalte (kWh äq)")
    col_widths = (130.0, 175.0, 175.0)
    rows = [
        ("Heizung", _fmt_kwh(report.heating.current_kwh), _fmt_kwh(report.heating.average_kwh)),
        (
            "Warmwasser",
            _fmt_kwh(report.hot_water.current_kwh),
            _fmt_kwh(report.hot_water.average_kwh),
        ),
    ]
    return _build_table("Verbrauchswerte", headers, rows, col_widths)


def _build_comparison_table(report: ConsumptionReport, year: int, month: int) -> list[Flowable]:
    """Build the table with the vs.-average/previous-month/previous-year comparisons.

    Each cell shows your value on the left and the reference value on the
    right, separated by a ``<``/``>``/``=`` relation symbol, e.g. ``15,0 < 210,0``.
    If no reference value is available at all, only your value is shown
    followed by ``-``. The whole cell is colored green when your value is
    lower than the reference and red when it is higher; equal values and
    cells without a reference value use the default text color.
    """
    headers = ("", "ggü. Vergleichshaushalten", "ggü. Vormonat", "ggü. Vorjahresmonat")
    col_widths = (85.0, 138.0, 112.0, 132.0)
    heating_cells = _comparison_cells(report.heating, year, month)
    hot_water_cells = _comparison_cells(report.hot_water, year, month)
    rows = [
        ("Heizung", *(text for text, _ in heating_cells)),
        ("Warmwasser", *(text for text, _ in hot_water_cells)),
    ]
    cell_colors = [
        (_TEXT_COLOR, *(color for _, color in heating_cells)),
        (_TEXT_COLOR, *(color for _, color in hot_water_cells)),
    ]
    return [
        *_build_table(
            "Vergleich", headers, rows, col_widths, cell_colors=cell_colors, trailing_space=6.0
        ),
        _build_legend(),
    ]


def _build_legend() -> Flowable:
    """Build the comparison-symbol legend, coloring the ``<``/``>`` segments."""
    style = ParagraphStyle(name="Legend", fontName=_FONT, fontSize=_NOTE_FONT_SIZE)
    gap = "&nbsp;" * 4
    text = (
        f'<font color="{_to_hex(_LESS_COLOR)}">&lt; weniger</font>'
        f"{gap}"
        f'<font color="{_to_hex(_MORE_COLOR)}">&gt; mehr</font>'
        f"{gap}= gleich viel{gap}- kein Vergleichswert vorhanden"
    )
    return Paragraph(text, style)


def _to_hex(color: colors.Color) -> str:
    red = round(color.red * 255)
    green = round(color.green * 255)
    blue = round(color.blue * 255)
    return f"#{red:02x}{green:02x}{blue:02x}"


_ComparisonCell = tuple[str, colors.Color]


def _comparison_cells(
    meter: MeterReport, year: int, month: int
) -> tuple[_ComparisonCell, _ComparisonCell, _ComparisonCell]:
    prev_month_value = _history_value(meter, _is_previous_month(year, month))
    prev_year_value = _history_value(meter, _is_same_month_previous_year(year, month))
    return (
        _comparison_cell(meter.current_kwh, meter.average_kwh, meter.vs_average),
        _comparison_cell(meter.current_kwh, prev_month_value, meter.vs_previous_month),
        _comparison_cell(meter.current_kwh, prev_year_value, meter.vs_previous_year),
    )


def _comparison_cell(
    your_kwh: float,
    ref_value: float | None,
    comparison: Comparison | None,
) -> _ComparisonCell:
    """Format a comparison cell as ``"<your> <symbol> <ref>"``, values always visible.

    If the reference value could not be determined but the portal did supply
    a comparison direction, that direction is still shown (without the
    reference number). Falls back to a symbol computed directly from the two
    values when the portal did not supply a comparison, but the reference
    value is known. Shows only your value followed by ``-`` when neither is
    available. Returns the cell text together with the color it should be
    drawn in (green if your value is lower, red if higher, default otherwise).
    """
    your_str = _fmt_kwh(your_kwh)
    if comparison is not None:
        symbol = _COMPARISON_SYMBOLS[comparison]
        color = _symbol_color(symbol)
        if ref_value is None:
            return f"{your_str} {symbol}", color
        return f"{your_str} {symbol} {_fmt_kwh(ref_value)}", color
    if ref_value is not None:
        symbol = _compute_symbol(your_kwh, ref_value)
        return f"{your_str} {symbol} {_fmt_kwh(ref_value)}", _symbol_color(symbol)
    return f"{your_str}  -", _TEXT_COLOR


def _symbol_color(symbol: str) -> colors.Color:
    if symbol == "<":
        return _LESS_COLOR
    if symbol == ">":
        return _MORE_COLOR
    return _TEXT_COLOR


def _compute_symbol(your_kwh: float, ref_value: float) -> str:
    """Derive a </>/= symbol directly from the two values (no portal comparison text)."""
    if abs(your_kwh - ref_value) < 1e-9:  # noqa: PLR2004
        return "="
    return "<" if your_kwh < ref_value else ">"


def _history_reading(
    meter: MeterReport,
    predicate: Callable[[int, int], bool],
) -> MeterReading | None:
    """Return the first history entry for which *predicate* matches."""
    for reading in meter.history:
        if predicate(reading.month, reading.year):
            return reading
    return None


def _history_value(
    meter: MeterReport,
    predicate: Callable[[int, int], bool],
) -> float | None:
    """Return the first history entry's ``your_kwh`` for which *predicate* matches."""
    reading = _history_reading(meter, predicate)
    return reading.your_kwh if reading is not None else None


def _is_previous_month(current_year: int, current_month: int) -> Callable[[int, int], bool]:
    """Return a predicate matching the calendar month before (current_month, current_year)."""

    def predicate(month: int, year: int) -> bool:
        if current_month == 1:
            return month == 12 and year == current_year - 1
        return month == current_month - 1 and year == current_year

    return predicate


def _is_same_month_previous_year(
    current_year: int, current_month: int
) -> Callable[[int, int], bool]:
    """Return a predicate matching the same month one year before *current_year*."""

    def predicate(month: int, year: int) -> bool:
        return month == current_month and year == current_year - 1

    return predicate


def _fmt_kwh(value: float) -> str:
    """Format *value* with one fractional digit using a German decimal comma."""
    return f"{value:.1f}".replace(".", ",")


def _build_table(
    title: str,
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
    col_widths: tuple[float, ...],
    cell_colors: list[tuple[colors.Color, ...]] | None = None,
    trailing_space: float = 20.0,
) -> list[Flowable]:
    """Build a titled table's flowables: a title paragraph and the table itself.

    *cell_colors*, if given, must have one entry per row in *rows* (not
    counting the header row), each a tuple of per-column colors overriding
    the default text color. *trailing_space* controls the gap left after the
    table, before whatever flowable follows it.
    """
    title_style = ParagraphStyle(name="TableTitle", fontName=_FONT, fontSize=_TABLE_TITLE_FONT_SIZE)
    all_rows = [headers, *rows]
    style_commands: list[tuple[object, ...]] = [
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("FONTSIZE", (0, 0), (-1, -1), _TABLE_FONT_SIZE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TEXTCOLOR", (0, 0), (-1, -1), _TEXT_COLOR),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, _LINE_COLOR),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if cell_colors is not None:
        for row_index, row_color in enumerate(cell_colors, start=1):
            for col_index, color in enumerate(row_color):
                style_commands.append(
                    ("TEXTCOLOR", (col_index, row_index), (col_index, row_index), color)
                )
    table = Table(
        list(all_rows),
        colWidths=list(col_widths),
        style=TableStyle(style_commands),  # pyright: ignore[reportArgumentType]
        hAlign="LEFT",
    )
    return [Paragraph(title, title_style), Spacer(1, 8.0), table, Spacer(1, trailing_space)]


def _build_note() -> list[Flowable]:
    title_style = ParagraphStyle(name="NoteTitle", fontName=_FONT, fontSize=_TABLE_TITLE_FONT_SIZE)
    note_style = ParagraphStyle(
        name="Note",
        fontName=_FONT,
        fontSize=_NOTE_FONT_SIZE,
        leading=_NOTE_FONT_SIZE * 1.35,
        alignment=TA_JUSTIFY,
    )
    return [
        Spacer(1, 16.0),
        Paragraph(_NOTE_TITLE, title_style),
        Spacer(1, 6.0),
        Paragraph(_NOTE_TEXT, note_style),
    ]
