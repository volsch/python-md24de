"""HTML parser for messdienst24.de portal responses."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, cast

import json5
from bs4 import BeautifulSoup, Tag

from md24de._exceptions import ParseError
from md24de._models import (
    AvailableMonth,
    Comparison,
    ConsumptionReport,
    MeterReading,
    MeterReport,
    ObjectInfo,
)

# Mapping of German month names to month numbers (1–12).
GERMAN_MONTHS: dict[str, int] = {
    "Januar": 1,
    "Februar": 2,
    "März": 3,
    "April": 4,
    "Mai": 5,
    "Juni": 6,
    "Juli": 7,
    "August": 8,
    "September": 9,
    "Oktober": 10,
    "November": 11,
    "Dezember": 12,
}


# Substrings that uniquely identify each dataset by its visible label text.
# These are the strings shown in the chart legend — far more stable than colors.
_YOUR_CONSUMPTION_MARKER = "Ihr Verbrauch"
_AVERAGE_MARKER = "vergleichbare Haushalte"

# Regex for the current-month sentence present on every consumption page.
# Example: "Sie haben im Mai 2026 weniger als ..."
_CURRENT_MONTH_RE = re.compile(r"Sie haben im (\w+) (\d{4})")

# Regex for the "als im <Month> <Year> verbraucht" comparison sentence.
_ALS_IM_RE = re.compile(r"als im (\w+) (\d{4}) verbraucht")

_log = logging.getLogger(__name__)

# Custom TRACE level — more verbose than DEBUG (10), used to dump raw HTML/JS on parse failure.
# We intentionally do NOT call logging.addLevelName() — that would mutate global state, which
# is inappropriate for a library. Use logging.addLevelName(5, "TRACE") in your application if
# you want the level to appear as "TRACE" rather than "Level 5" in your log output.
_TRACE = 5

_MAX_TRACE_CHARS = 256 * 1024  # 256 KB


def _truncated(text: str) -> str:
    """Return *text* truncated to _MAX_TRACE_CHARS with a note if cut."""
    if len(text) > _MAX_TRACE_CHARS:
        return text[:_MAX_TRACE_CHARS] + f"\n… [truncated — {len(text)} total chars]"
    return text


@dataclass
class _ChartData:
    """Parsed data from a single Chart.js script block."""

    month: int
    """Current month number (1–12), taken from the first chart label."""
    year: int
    """Current year, taken from the first chart label."""
    readings: list[MeterReading]
    """All readings in chart order (newest first)."""


def parse_available_month(html: str) -> AvailableMonth:
    """Extract the available month from the consumption page HTML.

    This is a cheap parse that reads only the first comparison sentence
    (``"Sie haben im Mai 2026 …"``), requiring no Chart.js processing.
    It is called on client initialisation so that the available month
    is known before the full Chart.js report is parsed.

    Args:
        html: Raw HTML string returned by the portal's consumption endpoint.

    Returns:
        The single :class:`AvailableMonth` the portal currently provides.

    Raises:
        ParseError: If the month sentence cannot be found.
    """
    match = _CURRENT_MONTH_RE.search(html)
    if not match:
        _log.log(_TRACE, "HTML where month sentence was not found:\n%s", _truncated(html))
        raise ParseError(
            "Could not find current-month sentence "
            '("Sie haben im <Month> <Year>") in consumption page HTML'
        )
    month_num = GERMAN_MONTHS.get(match.group(1))
    if month_num is None:
        _log.log(_TRACE, "HTML with unknown month name %r:\n%s", match.group(1), _truncated(html))
        raise ParseError(f"Unknown German month name: {match.group(1)!r}")
    available = AvailableMonth(year=int(match.group(2)), month=month_num)
    _log.debug("Available month: %04d-%02d", available.year, available.month)
    return available


def parse_consumption_html(html: str) -> ConsumptionReport:
    """Parse the consumption page HTML fragment into a :class:`ConsumptionReport`.

    Args:
        html: Raw HTML string returned by the portal's consumption endpoint.

    Returns:
        A fully populated :class:`ConsumptionReport`.

    Raises:
        ParseError: If required data cannot be extracted from the HTML.
    """
    _log.debug("Parsing consumption HTML (%d bytes)", len(html))
    soup = BeautifulSoup(html, "lxml")

    heating: MeterReport | None = None
    hot_water: MeterReport | None = None

    for h1 in soup.find_all("h1"):
        result = _process_meter_h1(h1)
        if result is None:
            continue
        is_heating, chart = result

        meter = _build_meter_report(h1, chart)
        if is_heating:
            heating = meter
        else:
            hot_water = meter

    if heating is None:
        _log.log(_TRACE, "HTML where heating meter was not found:\n%s", _truncated(html))
        raise ParseError("Heating meter data not found in HTML")
    if hot_water is None:
        _log.log(_TRACE, "HTML where hot-water meter was not found:\n%s", _truncated(html))
        raise ParseError("Hot-water meter data not found in HTML")

    object_info = _parse_object_info(soup)
    _log.debug("Consumption report parsed: object=%r", object_info.object_number)
    return ConsumptionReport(
        object_info=object_info,
        heating=heating,
        hot_water=hot_water,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_chart_script(script: str, canvas_id: str) -> _ChartData:
    """Parse a Chart.js constructor call using json5.

    Extracts the config object with balanced-brace matching (handles any level of
    nesting), then parses it with :func:`json5.loads` to get a proper Python dict.
    Datasets are identified by their ``label`` text — semantic, not positional.
    """
    config_block = _extract_chart_config(script, canvas_id)
    _log.log(_TRACE, "Chart config block for '%s':\n%s", canvas_id, _truncated(config_block))
    try:
        parsed: Any = json5.loads(config_block)  # pyright: ignore[reportUnknownVariableType]
    except Exception as exc:
        raise ParseError(f"Failed to parse Chart.js config for '{canvas_id}': {exc}") from exc
    if not isinstance(parsed, dict):
        raise ParseError(f"Chart config for '{canvas_id}' is not a JSON object")
    config = cast(dict[str, Any], parsed)

    try:
        labels: list[Any] = config["data"]["labels"]
        datasets: list[Any] = config["data"]["datasets"]
    except (KeyError, TypeError) as exc:
        raise ParseError(f"Unexpected Chart.js config structure for '{canvas_id}': {exc}") from exc

    your_ds: dict[str, Any] | None = next(
        (d for d in datasets if _YOUR_CONSUMPTION_MARKER in str(d.get("label", ""))),
        None,
    )
    avg_ds: dict[str, Any] | None = next(
        (d for d in datasets if _AVERAGE_MARKER in str(d.get("label", ""))),
        None,
    )

    if your_ds is None:
        raise ParseError(
            f"User consumption dataset (label containing '{_YOUR_CONSUMPTION_MARKER}') "
            f"not found in chart for '{canvas_id}'"
        )
    if avg_ds is None:
        raise ParseError(
            f"Average households dataset (label containing '{_AVERAGE_MARKER}') "
            f"not found in chart for '{canvas_id}'"
        )

    try:
        your_values = [float(v) for v in your_ds["data"]]
        avg_values = [float(v) for v in avg_ds["data"]]
    except (ValueError, TypeError, KeyError) as exc:
        raise ParseError(
            f"Non-numeric or missing data value in chart for '{canvas_id}': {exc}"
        ) from exc

    readings: list[MeterReading] = []
    for i, raw_label in enumerate(labels):
        label = str(raw_label).strip()
        if not label:
            continue
        month_num, year = _parse_german_month_year(label, canvas_id)
        readings.append(
            MeterReading(
                month=month_num,
                year=year,
                your_kwh=your_values[i] if i < len(your_values) else 0.0,
                average_kwh=avg_values[i] if i < len(avg_values) else 0.0,
            )
        )

    if not readings:
        raise ParseError(f"No readings found in chart for '{canvas_id}'")

    return _ChartData(
        month=readings[0].month,
        year=readings[0].year,
        readings=readings,
    )


def _extract_chart_config(script: str, canvas_id: str) -> str:
    """Extract the JSON5 config block ``{...}`` from a ``new Chart(ctx, {...})`` call.

    Uses balanced-brace counting rather than a regex so it handles any level of
    nesting without fragile greedy matching.
    """
    _log.log(_TRACE, "Raw script for '%s':\n%s", canvas_id, _truncated(script))
    start = script.find("new Chart(")
    if start == -1:
        raise ParseError(f"new Chart( call not found in script for '{canvas_id}'")
    brace_start = script.find("{", start)
    if brace_start == -1:
        raise ParseError(f"Chart config object not found for '{canvas_id}'")
    depth = 0
    for i, ch in enumerate(script[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return script[brace_start : i + 1]
    raise ParseError(f"Unbalanced braces in Chart config for '{canvas_id}'")


def _parse_german_month_year(label: str, canvas_id: str) -> tuple[int, int]:
    """Parse a label like ``'Mai 2026'`` into ``(month_number, year)``."""
    parts = label.split()
    if len(parts) != 2:  # noqa: PLR2004
        raise ParseError(f"Unexpected chart label format: {label!r} for '{canvas_id}'")
    month_num = GERMAN_MONTHS.get(parts[0])
    if month_num is None:
        raise ParseError(f"Unknown German month name: {parts[0]!r} for '{canvas_id}'")
    return month_num, int(parts[1])


def _parse_comparisons(
    div: Tag,
    current_month: int,
    current_year: int,
) -> dict[str, Comparison]:
    """Parse comparison sentences from the div that follows an h1 heading.

    Returns a dict with keys ``vs_average``, ``vs_previous_month``,
    ``vs_previous_year`` mapped to :class:`Comparison` values.
    """
    results: dict[str, Comparison] = {}

    for child in cast(list[Tag], div.find_all("div", recursive=False)):
        text = child.get_text()
        if not text.strip():
            continue
        direction = _parse_direction(text)
        if direction is None:
            continue
        key = _classify_reference(text, current_month, current_year)
        if key is not None:
            results[key] = direction

    return results


def _process_meter_h1(h1: Tag | object) -> tuple[bool, _ChartData] | None:
    """Extract chart data from an h1 element, or return None if not a meter heading."""
    if not isinstance(h1, Tag):
        return None
    container = h1.parent
    if not isinstance(container, Tag):
        return None
    canvas = container.find("canvas")
    if not isinstance(canvas, Tag):
        return None
    canvas_id = str(canvas.get("id", ""))
    is_heating = _canvas_is_heating(canvas_id)
    if is_heating is None:
        return None
    chart_script = _find_chart_script_in(container)
    if chart_script is None or not chart_script.string:
        _log.log(
            _TRACE, "Container HTML where script was not found:\n%s", _truncated(str(container))
        )
        raise ParseError(f"Chart script not found for canvas '{canvas_id}'")
    return is_heating, _parse_chart_script(chart_script.string, canvas_id)


def _canvas_is_heating(canvas_id: str) -> bool | None:
    """Return True for heating canvas, False for hot-water, None for unknown."""
    if canvas_id.endswith("_hz"):
        return True
    if canvas_id.endswith("_ww"):
        return False
    return None


def _find_chart_script_in(container: Tag) -> Tag | None:
    """Return the first script tag in *container* that contains a Chart.js call."""
    for script in container.find_all("script"):
        if isinstance(script, Tag) and script.string and "Chart(" in script.string:
            return script
    return None


def _build_meter_report(h1: Tag, chart: _ChartData) -> MeterReport:
    """Build a :class:`MeterReport` from chart data and the adjacent comparison div."""
    comparison_div = h1.find_next_sibling("div")
    comparisons: dict[str, Comparison] = {}
    if isinstance(comparison_div, Tag):
        comparisons = _parse_comparisons(comparison_div, chart.month, chart.year)
    return MeterReport(
        current_kwh=chart.readings[0].your_kwh,
        average_kwh=chart.readings[0].average_kwh,
        vs_average=comparisons.get("vs_average"),
        vs_previous_month=comparisons.get("vs_previous_month"),
        vs_previous_year=comparisons.get("vs_previous_year"),
        history=tuple(chart.readings),
    )


def _parse_direction(text: str) -> Comparison | None:
    """Return LESS / MORE / EQUAL based on keywords in *text*, or None."""
    if "weniger" in text:
        return Comparison.LESS
    if "mehr" in text:
        return Comparison.MORE
    if "soviel" in text:
        return Comparison.EQUAL
    return None


def _classify_reference(
    text: str,
    current_month: int,
    current_year: int,
) -> str | None:
    """Return the comparison key for the sentence, or None if unrecognised."""
    if "vergleichbare Haushalte" in text:
        return "vs_average"
    if "als im" not in text:
        return None
    match = _ALS_IM_RE.search(text)
    if not match:
        return None
    ref_month = GERMAN_MONTHS.get(match.group(1))
    if ref_month is None:
        return None
    ref_year = int(match.group(2))
    if _is_previous_month(current_month, current_year, ref_month, ref_year):
        return "vs_previous_month"
    if _is_same_month_previous_year(current_month, current_year, ref_month, ref_year):
        return "vs_previous_year"
    return None


def _parse_object_info(soup: BeautifulSoup) -> ObjectInfo:
    """Extract object number and address from the sidebar."""
    object_number = ""
    address = ""

    for name_div in cast(list[Tag], soup.find_all("div", class_="name")):
        label = name_div.get_text(strip=True)
        value_div = name_div.find_next_sibling("div", class_="value")
        if not isinstance(value_div, Tag):
            continue

        # Use ", " as separator for <br> elements within the address.
        value = value_div.get_text(separator=", ", strip=True)
        # Remove non-breaking spaces.
        value = value.replace("\xa0", "").strip()

        if "Objektnummer" in label:
            object_number = value
        elif "Adresse" in label:
            address = value

    return ObjectInfo(object_number=object_number, address=address)


def _is_previous_month(
    current_month: int,
    current_year: int,
    ref_month: int,
    ref_year: int,
) -> bool:
    """Return True if (ref_month, ref_year) is the calendar month before current."""
    if current_month == 1:
        return ref_month == 12 and ref_year == current_year - 1
    return ref_month == current_month - 1 and ref_year == current_year


def _is_same_month_previous_year(
    current_month: int,
    current_year: int,
    ref_month: int,
    ref_year: int,
) -> bool:
    """Return True if (ref_month, ref_year) is the same month one year earlier."""
    return ref_month == current_month and ref_year == current_year - 1
