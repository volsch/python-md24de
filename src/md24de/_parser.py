"""HTML parser for messdienst24.de portal responses."""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable
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

#: Mapping of month numbers (1–12) to their German month names, the reverse
#: of :data:`GERMAN_MONTHS`. Exported publicly so callers can render German
#: month names (e.g. in reports or emails) without duplicating the mapping.
GERMAN_MONTH_NAMES: dict[int, str] = {number: name for name, number in GERMAN_MONTHS.items()}


# The two headings under which the portal renders each meter's chart and
# comparison text. Matched by exact heading text — deliberately not
# positional, so an unrelated heading is never mistaken for a meter section.
_HEATING_HEADING = "Heizung"
_HOT_WATER_HEADING = "Warmwasser"

# Substrings that uniquely identify each dataset by its visible label text.
# These are the strings shown in the chart legend — far more stable than colors
# or dataset order/position.
#
# --- Dataset-selection fail-fast contract -----------------------------------
# Datasets are matched by searching their Chart.js ``label`` field for these
# markers (see _parse_chart_script). This is deliberately NOT positional and
# has NO fallback: if the portal ever rewords its German legend text (e.g.
# renames "Ihr Verbrauch" or "vergleichbare Haushalte"), the substring match
# fails, `your_ds`/`avg_ds` resolve to None, and _parse_chart_script raises
# ParseError immediately for that chart. We intentionally do not fall back to
# positional/index-based dataset selection in that case — a silent guess
# could swap "your consumption" and "average household" values without any
# indication, which is worse than a hard, debuggable failure. If the portal's
# wording changes, this is the single place to update the markers; the
# resulting ParseError message names the missing marker text so the failure
# is easy to diagnose (raise the log level to _TRACE to see the raw chart
# config that failed to match).
_YOUR_CONSUMPTION_MARKER = "Ihr Verbrauch"
_AVERAGE_MARKER = "vergleichbare Haushalte"

# Regex for the current-month sentence present on every consumption page.
# Example: "Sie haben im Mai 2026 weniger als ..."
_CURRENT_MONTH_RE = re.compile(r"Sie haben im (\w+) (\d{4})")

# Regex matching one full comparison sentence, e.g.:
# "Sie haben im Mai 2026 weniger als im April 2026 verbraucht."
# Sentences are extracted this way — rather than relying on the surrounding
# markup — because the portal renders them as plain text interspersed with
# inline <span> elements (for color) and, depending on the page layout, may
# join several sentences in a single container separated only by <br>. Both
# forms concatenate to the same running text once tags are stripped, so a
# content-based regex is more robust here than any DOM-structure assumption.
_COMPARISON_SENTENCE_RE = re.compile(r"Sie haben im \w+ \d{4}.*?verbraucht\.")

# Regex for the "als im <Month> <Year> verbraucht" / "wie im <Month> <Year>
# verbraucht" comparison sentence ("als im" for weniger/mehr, "wie im" for
# soviel/equal comparisons).
_ALS_IM_RE = re.compile(r"(?:als|wie) im (\w+) (\d{4}) verbraucht")

# Regex validating the portal's per-unit tab identifier format, e.g. "0001-001"
# (flat/unit number, then a sequence number that increments whenever the
# tenant/owner of that unit changes). Used only to validate the shape of the
# identifier before returning it verbatim as ObjectInfo.unit_id.
_UNIT_TAB_ID_RE = re.compile(r"^\d+-\d+$")

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

    for heading in soup.find_all("h5"):
        result = _process_meter_heading(heading)
        if result is None:
            continue
        is_heating, chart = result

        meter = _build_meter_report(heading, chart)
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

    Correctness guarantees and their fail-fast behavior:

    * **Dataset identity** ("Ihr Verbrauch" vs. "vergleichbare Haushalte") is
      resolved purely from each dataset's ``label`` text (see
      ``_YOUR_CONSUMPTION_MARKER``/``_AVERAGE_MARKER`` above). There is no
      positional or color-based fallback. If the portal changes its legend
      wording so that neither dataset matches, :func:`_parse_chart_script`
      raises :class:`ParseError` right here — it never guesses.
    * **Month alignment** (e.g. that a "Mai 2026" reading really holds May's
      numbers) relies on the Chart.js contract that ``data.labels`` and every
      dataset's ``data`` array share the same index space — ``labels[i]``
      always corresponds to ``datasets[*].data[i]``, exactly as the browser's
      own Chart.js renderer requires to draw grouped bars correctly. The
      readings loop below reuses that same index ``i`` to read both
      ``your_values[i]`` and ``avg_values[i]``, so it can never attribute a
      value to the wrong month — it either reads the correct paired value or,
      if a dataset's ``data`` array is shorter than ``labels`` (a malformed/
      inconsistent chart), leaves that reading's value as ``None`` rather
      than shifting indices or misattributing another month's number.
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
        your_values: list[float | None] = [_to_optional_float(v) for v in your_ds["data"]]
        avg_values: list[float | None] = [_to_optional_float(v) for v in avg_ds["data"]]
    except (ValueError, TypeError, KeyError) as exc:
        raise ParseError(f"Non-numeric data value in chart for '{canvas_id}': {exc}") from exc

    readings: list[MeterReading] = []
    for i, raw_label in enumerate(labels):
        label = str(raw_label).strip()
        if not label:
            continue
        month_num, year = _parse_german_month_year(label, canvas_id)
        # Reuse the same index `i` for both value arrays: Chart.js requires labels
        # and every dataset's data array to share one index space, so labels[i]
        # always pairs with your_values[i]/avg_values[i]. Never re-sort or
        # re-index here — a shorter data array yields None (see docstring above),
        # it must not shift and attribute a value to the wrong month.
        readings.append(
            MeterReading(
                month=month_num,
                year=year,
                your_kwh=your_values[i] if i < len(your_values) else None,
                average_kwh=avg_values[i] if i < len(avg_values) else None,
            )
        )

    if not readings:
        raise ParseError(f"No readings found in chart for '{canvas_id}'")

    return _ChartData(
        month=readings[0].month,
        year=readings[0].year,
        readings=readings,
    )


def _to_optional_float(value: float | int | str | None) -> float | None:
    """Convert a raw Chart.js data value to ``float``, or ``None`` for a JSON ``null``.

    ``None`` signals the portal genuinely did not supply a value for that month —
    distinct from an actual reading of ``0.0``.
    """
    return None if value is None else float(value)


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
    text: str,
    current_month: int,
    current_year: int,
) -> dict[str, Comparison]:
    """Parse comparison sentences out of *text* (the container's plain text).

    Returns a dict with keys ``vs_average``, ``vs_previous_month``,
    ``vs_previous_year`` mapped to :class:`Comparison` values. Sentences are
    located with :data:`_COMPARISON_SENTENCE_RE`, so the surrounding markup
    (separate divs, ``<br>``-joined text, inline color ``<span>`` elements)
    does not matter — only the sentence text itself.
    """
    results: dict[str, Comparison] = {}

    for match in _COMPARISON_SENTENCE_RE.finditer(text):
        sentence = match.group(0)
        direction = _parse_direction(sentence)
        if direction is None:
            # Every string matched by _COMPARISON_SENTENCE_RE is a full
            # "Sie haben im ... verbraucht." comparison sentence, so it is
            # expected to state a direction. If none of the known keywords
            # ("weniger"/"mehr"/"soviel") appear, the portal's wording has
            # changed in a way we don't recognise — fail fast rather than
            # silently drop the comparison.
            raise ParseError(
                "Comparison sentence does not contain a recognized direction "
                f"keyword ('weniger'/'mehr'/'soviel'): {sentence!r}"
            )
        key = _classify_reference(sentence, current_month, current_year)
        if key is not None:
            results[key] = direction

    return results


def _process_meter_heading(heading: Tag | object) -> tuple[bool, _ChartData] | None:
    """Extract chart data from a heading element, or None if not a meter heading."""
    if not isinstance(heading, Tag):
        return None
    heading_text = heading.get_text(strip=True)
    if heading_text == _HEATING_HEADING:
        is_heating = True
    elif heading_text == _HOT_WATER_HEADING:
        is_heating = False
    else:
        return None
    container = heading.parent
    if not isinstance(container, Tag):
        return None
    canvas = container.find("canvas")
    if not isinstance(canvas, Tag):
        return None
    canvas_id = str(canvas.get("id", ""))
    chart_script = _find_chart_script_in(container)
    if chart_script is None or not chart_script.string:
        _log.log(
            _TRACE, "Container HTML where script was not found:\n%s", _truncated(str(container))
        )
        raise ParseError(f"Chart script not found for canvas '{canvas_id}'")
    return is_heating, _parse_chart_script(chart_script.string, canvas_id)


def _find_chart_script_in(container: Tag) -> Tag | None:
    """Return the first script tag in *container* that contains a Chart.js call."""
    for script in container.find_all("script"):
        if isinstance(script, Tag) and script.string and "Chart(" in script.string:
            return script
    return None


def _find_comparison_text_in(container: Tag) -> str:
    """Return the plain text of the child div holding the comparison sentences.

    The comparison sentences live in a direct-child ``<div>`` of *container*
    (a sibling of the chart's canvas/script) — the one whose text contains
    "Sie haben im". Returns an empty string if no such div is found, letting
    the caller treat that meter's comparisons as simply absent instead of
    raising a hard error.
    """
    for child in cast(list[Tag], container.find_all("div", recursive=False)):
        if "Sie haben im" in child.get_text():
            return child.get_text()
    return ""


def _build_meter_report(heading: Tag, chart: _ChartData) -> MeterReport:
    """Build a :class:`MeterReport` from chart data and the sibling comparison text."""
    container = heading.parent
    comparisons: dict[str, Comparison] = {}
    if isinstance(container, Tag):
        comparison_text = _find_comparison_text_in(container)
        comparisons = _parse_comparisons(comparison_text, chart.month, chart.year)

    meter_name = heading.get_text(strip=True)
    current = chart.readings[0]
    previous_month_reading = _find_reading(
        chart.readings, chart.month, chart.year, _is_previous_month
    )
    previous_year_reading = _find_reading(
        chart.readings, chart.month, chart.year, _is_same_month_previous_year
    )

    _check_comparison_consistency(
        f"{meter_name} vs_average",
        current.average_kwh,
        "vs_average" in comparisons,
    )
    _check_comparison_consistency(
        f"{meter_name} vs_previous_month",
        previous_month_reading.your_kwh if previous_month_reading is not None else None,
        "vs_previous_month" in comparisons,
    )
    _check_comparison_consistency(
        f"{meter_name} vs_previous_year",
        previous_year_reading.your_kwh if previous_year_reading is not None else None,
        "vs_previous_year" in comparisons,
    )

    _check_comparison_direction(
        f"{meter_name} vs_average",
        comparisons.get("vs_average"),
        current.your_kwh,
        current.average_kwh,
    )
    _check_comparison_direction(
        f"{meter_name} vs_previous_month",
        comparisons.get("vs_previous_month"),
        current.your_kwh,
        previous_month_reading.your_kwh if previous_month_reading is not None else None,
    )
    _check_comparison_direction(
        f"{meter_name} vs_previous_year",
        comparisons.get("vs_previous_year"),
        current.your_kwh,
        previous_year_reading.your_kwh if previous_year_reading is not None else None,
    )

    return MeterReport(
        current_kwh=current.your_kwh,
        average_kwh=current.average_kwh,
        vs_average=comparisons.get("vs_average"),
        vs_previous_month=comparisons.get("vs_previous_month"),
        vs_previous_year=comparisons.get("vs_previous_year"),
        history=tuple(chart.readings),
    )


def _find_reading(
    readings: list[MeterReading],
    current_month: int,
    current_year: int,
    matches: Callable[[int, int, int, int], bool],
) -> MeterReading | None:
    """Return the reading for which *matches(current_month, current_year, r.month, r.year)*.

    Used to locate the previous-month or same-month-previous-year reading (via
    :func:`_is_previous_month` / :func:`_is_same_month_previous_year`) within the
    chart's history window. Returns ``None`` if no such reading is present in the
    window — this is the normal case when the portal's history simply doesn't
    reach that far back, and is treated as "kWh value not available".
    """
    return next(
        (r for r in readings if matches(current_month, current_year, r.month, r.year)),
        None,
    )


def _check_comparison_consistency(
    label: str,
    kwh: float | None,
    sentence_present: bool,
) -> None:
    """Raise :class:`ParseError` if *kwh* and *sentence_present* are inconsistent.

    The two must agree in both directions: a present kWh value requires a
    comparison sentence, and a comparison sentence requires a present kWh
    value. A kWh value of exactly ``0`` is treated as "not present" when no
    sentence backs it up — the portal is not known to reliably distinguish a
    genuine 0 kWh reading from an absent one in the rendered text, so that
    specific combination is not treated as an inconsistency.
    """
    effective_kwh_present = kwh is not None and not (kwh == 0 and not sentence_present)
    if effective_kwh_present and not sentence_present:
        raise ParseError(f"{label}: kWh value ({kwh}) present but comparison sentence is missing")
    if sentence_present and kwh is None:
        raise ParseError(f"{label}: comparison sentence present but kWh value is missing")


def _check_comparison_direction(
    label: str,
    comparison: Comparison | None,
    current_kwh: float | None,
    reference_kwh: float | None,
) -> None:
    """Raise :class:`ParseError` if *comparison* contradicts the actual kWh values.

    E.g. a "weniger" (LESS) sentence requires ``current_kwh < reference_kwh`` —
    if the portal's own numbers disagree with its own wording, that indicates
    either a parsing bug or an unannounced portal change, so we fail fast
    rather than silently return a self-contradictory report.
    """
    if comparison is None:
        return
    # _check_comparison_consistency (called before this for the same pair)
    # already guarantees reference_kwh is present whenever comparison is not
    # None. current_kwh is checked independently here because nothing else
    # ties it to comparison presence: the sentence describes *this* month's
    # consumption relative to the reference, so a missing current_kwh with a
    # present comparison is just as inconsistent as a missing reference_kwh.
    if current_kwh is None or reference_kwh is None:
        raise ParseError(
            f"{label}: comparison sentence ({comparison.value}) present but current "
            f"kWh ({current_kwh}) or reference kWh ({reference_kwh}) is missing"
        )
    if comparison is Comparison.LESS and not current_kwh < reference_kwh:
        raise ParseError(
            f"{label}: sentence says 'weniger' (less) but current kWh ({current_kwh}) "
            f"is not less than reference kWh ({reference_kwh})"
        )
    if comparison is Comparison.MORE and not current_kwh > reference_kwh:
        raise ParseError(
            f"{label}: sentence says 'mehr' (more) but current kWh ({current_kwh}) "
            f"is not greater than reference kWh ({reference_kwh})"
        )
    if comparison is Comparison.EQUAL and not math.isclose(
        current_kwh, reference_kwh, rel_tol=1e-9, abs_tol=1e-9
    ):
        raise ParseError(
            f"{label}: sentence says 'soviel' (equal) but current kWh ({current_kwh}) "
            f"differs from reference kWh ({reference_kwh})"
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
    """Extract the object number and address from the "ausgewähltes Objekt" field.

    The portal renders this as a ``<span class="field-label">ausgewähltes
    Objekt</span>`` followed by a sibling ``<div class="mt-1">`` containing the
    object number (``<span class="field-value">``) and one or more address
    lines (``<span class="text-gray-600">``), which are joined with ``", "``.
    """
    object_number = ""
    address = ""

    for label_span in cast(list[Tag], soup.find_all("span", class_="field-label")):
        if "ausgewähltes Objekt" not in label_span.get_text():
            continue
        value_div = label_span.find_next_sibling("div", class_="mt-1")
        if not isinstance(value_div, Tag):
            continue

        value_span = value_div.find("span", class_="field-value")
        if isinstance(value_span, Tag):
            object_number = value_span.get_text(strip=True)

        address_parts = [
            span.get_text(strip=True)
            for span in cast(list[Tag], value_div.find_all("span", class_="text-gray-600"))
        ]
        address = ", ".join(part for part in address_parts if part)
        break

    unit_id, occupant_name = _parse_unit_occupant_info(soup)

    return ObjectInfo(
        object_number=object_number,
        address=address,
        unit_id=unit_id,
        occupant_name=occupant_name,
    )


def _parse_unit_occupant_info(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract the unit identifier and occupant name from the selected unit tab.

    The portal renders the currently selected flat/unit as a tab such as::

        <li class="tab col s6 m3"><a href="#0001-001">0001-001&nbsp;&nbsp;Max Mustermann</a></li>

    The tab's fragment identifier (``"0001-001"``) is returned verbatim as
    :attr:`ObjectInfo.unit_id`; the occupant's name follows the identifier in
    the link text, separated by non-breaking spaces.

    Raises:
        ParseError: If the tab cannot be found, its identifier does not match
            the expected ``"<unit>-<sequence>"`` format, or the occupant name
            is empty. Unlike the object number/address (which the portal may
            legitimately omit), this data is expected to always be present, so
            its absence indicates unexpected page structure rather than a
            normal missing-field case.
    """
    tab_anchor = soup.find("li", class_="tab")
    if isinstance(tab_anchor, Tag):
        tab_anchor = tab_anchor.find("a")
    if not isinstance(tab_anchor, Tag):
        _log.log(_TRACE, "HTML where unit tab was not found:\n%s", _truncated(str(soup)))
        raise ParseError("Unit tab (<li class='tab'><a href='#<unit>-<sequence>'>) not found")

    unit_id = str(tab_anchor.get("href", "")).lstrip("#")
    if not _UNIT_TAB_ID_RE.match(unit_id):
        raise ParseError(f"Unexpected unit tab identifier format: {unit_id!r}")

    # The link text is "<tab_id><nbsp><nbsp><name>" — strip the identifier
    # prefix and any leading non-breaking/regular whitespace to get the name.
    name = tab_anchor.get_text().removeprefix(unit_id).strip().strip("\xa0").strip()
    if not name:
        raise ParseError(f"Occupant name not found in unit tab {unit_id!r}")
    return unit_id, name


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
