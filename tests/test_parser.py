"""Tests for the HTML parser."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup, Tag

from md24de._exceptions import ParseError
from md24de._models import Comparison
from md24de._parser import (  # pyright: ignore[reportPrivateUsage]
    GERMAN_MONTH_NAMES,
    GERMAN_MONTHS,
    _check_comparison_consistency,  # pyright: ignore[reportPrivateUsage]
    _classify_reference,  # pyright: ignore[reportPrivateUsage]
    _extract_chart_config,  # pyright: ignore[reportPrivateUsage]
    _find_comparison_text_in,  # pyright: ignore[reportPrivateUsage]
    _is_previous_month,  # pyright: ignore[reportPrivateUsage]
    _is_same_month_previous_year,  # pyright: ignore[reportPrivateUsage]
    _parse_chart_script,  # pyright: ignore[reportPrivateUsage]
    _parse_comparisons,  # pyright: ignore[reportPrivateUsage]
    _parse_direction,  # pyright: ignore[reportPrivateUsage]
    _parse_german_month_year,  # pyright: ignore[reportPrivateUsage]
    _parse_object_info,  # pyright: ignore[reportPrivateUsage]
    _process_meter_heading,  # pyright: ignore[reportPrivateUsage]
    parse_available_month,
    parse_consumption_html,
)


class TestParseAvailableMonth:
    def test_returns_correct_month_and_year(self, consumption_html: str) -> None:
        month = parse_available_month(consumption_html)
        assert month.month == 5
        assert month.year == 2026

    def test_missing_sentence_raises(self) -> None:
        with pytest.raises(ParseError, match="Sie haben im"):
            parse_available_month("<html><body>no match here</body></html>")

    def test_unknown_month_name_raises(self) -> None:
        with pytest.raises(ParseError, match="Unknown German month name"):
            parse_available_month("Sie haben im Octember 2026 weniger verbraucht")


class TestParseConsumptionHtml:
    """Integration tests against the real captured fixture."""

    def test_object_info(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.object_info.object_number == "000-000000"
        assert report.object_info.address == "Musterstraße 1, 12345 Musterstadt"
        assert report.object_info.unit_id == "0001-001"
        assert report.object_info.occupant_name == "Max Mustermann"

    # ------------------------------------------------------------------
    # Heating
    # ------------------------------------------------------------------

    def test_heating_current_kwh(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.heating.current_kwh == pytest.approx(15.0)

    def test_heating_average_kwh(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.heating.average_kwh == pytest.approx(210.0)

    def test_heating_vs_average(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.heating.vs_average is Comparison.LESS

    def test_heating_vs_previous_month(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.heating.vs_previous_month is Comparison.LESS

    def test_heating_vs_previous_year(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.heating.vs_previous_year is Comparison.LESS

    def test_heating_history_length(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert len(report.heating.history) == 3

    def test_heating_history_values(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        h = report.heating.history
        assert h[0].month == 5 and h[0].year == 2026
        assert h[0].your_kwh == pytest.approx(15.0) and h[0].average_kwh == pytest.approx(210.0)
        assert h[1].month == 4 and h[1].year == 2026
        assert h[1].your_kwh == pytest.approx(145.0) and h[1].average_kwh == pytest.approx(305.0)
        assert h[2].month == 5 and h[2].year == 2025
        assert h[2].your_kwh == pytest.approx(140.0) and h[2].average_kwh == pytest.approx(210.0)

    # ------------------------------------------------------------------
    # Hot water
    # ------------------------------------------------------------------

    def test_hot_water_current_kwh(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.hot_water.current_kwh == pytest.approx(55.0)

    def test_hot_water_average_kwh(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.hot_water.average_kwh == pytest.approx(65.0)

    def test_hot_water_vs_average(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.hot_water.vs_average is Comparison.LESS

    def test_hot_water_vs_previous_month(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.hot_water.vs_previous_month is Comparison.LESS

    def test_hot_water_vs_previous_year(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.hot_water.vs_previous_year is Comparison.LESS

    def test_hot_water_history_length(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert len(report.hot_water.history) == 3

    def test_hot_water_history_values(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        h = report.hot_water.history
        assert h[0].month == 5 and h[0].year == 2026
        assert h[0].your_kwh == pytest.approx(55.0) and h[0].average_kwh == pytest.approx(65.0)
        assert h[1].month == 4 and h[1].year == 2026
        assert h[1].your_kwh == pytest.approx(60.0) and h[1].average_kwh == pytest.approx(62.0)
        assert h[2].month == 5 and h[2].year == 2025
        assert h[2].your_kwh == pytest.approx(58.0) and h[2].average_kwh == pytest.approx(65.0)

    # ------------------------------------------------------------------
    # History is newest-first
    # ------------------------------------------------------------------

    def test_history_is_newest_first(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        years_months = [(r.year, r.month) for r in report.hot_water.history]
        assert years_months == [(2026, 5), (2026, 4), (2025, 5)]


class TestParseErrors:
    def test_empty_html_raises(self) -> None:
        with pytest.raises(ParseError):
            parse_consumption_html("<html></html>")

    def test_missing_chart_script_raises(self) -> None:
        html = """
        <html><body>
          <div>
            <h5>Heizung</h5>
            <div></div>
            <canvas id="100583bar"></canvas>
          </div>
        </body></html>
        """
        with pytest.raises(ParseError):
            parse_consumption_html(html)


class TestGermanMonths:
    def test_all_months_present(self) -> None:
        assert len(GERMAN_MONTHS) == 12
        assert GERMAN_MONTHS["Januar"] == 1
        assert GERMAN_MONTHS["Dezember"] == 12
        assert GERMAN_MONTHS["März"] == 3

    def test_all_values_unique(self) -> None:
        assert sorted(GERMAN_MONTHS.values()) == list(range(1, 13))

    def test_month_names_is_reverse_of_german_months(self) -> None:
        assert len(GERMAN_MONTH_NAMES) == 12
        assert GERMAN_MONTH_NAMES[1] == "Januar"
        assert GERMAN_MONTH_NAMES[12] == "Dezember"
        assert GERMAN_MONTH_NAMES[3] == "März"
        assert {name: number for number, name in GERMAN_MONTH_NAMES.items()} == GERMAN_MONTHS

    def test_month_names_publicly_exported(self) -> None:
        import md24de

        assert md24de.GERMAN_MONTH_NAMES is GERMAN_MONTH_NAMES


class TestHelpers:
    def test_is_previous_month_normal(self) -> None:
        assert _is_previous_month(5, 2026, 4, 2026) is True
        assert _is_previous_month(5, 2026, 3, 2026) is False
        assert _is_previous_month(5, 2026, 4, 2025) is False

    def test_is_previous_month_january(self) -> None:
        assert _is_previous_month(1, 2026, 12, 2025) is True
        assert _is_previous_month(1, 2026, 11, 2025) is False
        assert _is_previous_month(1, 2026, 12, 2026) is False

    def test_is_same_month_previous_year(self) -> None:
        assert _is_same_month_previous_year(5, 2026, 5, 2025) is True
        assert _is_same_month_previous_year(5, 2026, 4, 2025) is False
        assert _is_same_month_previous_year(5, 2026, 5, 2026) is False


# ---------------------------------------------------------------------------
# Helpers shared by low-level tests
# ---------------------------------------------------------------------------


def _chart_script(
    *,
    labels: str = "['Mai 2026']",
    your_data: str = "[55.0]",
    avg_data: str = "[65.0]",
    your_label: str = "Ihr Verbrauch kWh",
    avg_label: str = "Verbrauch vergleichbare Haushalte",
) -> str:
    return (
        "new Chart(ctx, {type:'bar',data:{"
        f"labels:{labels},"
        "datasets:["
        f"{{label:'{your_label}',data:{your_data}}},"
        f"{{label:'{avg_label}',data:{avg_data}}}"
        "]}})"
    )


def _heading_html(heading_text: str, script: str) -> str:
    # The leading non-meter <h5> (no canvas) exercises the
    # `if result is None: continue` branch in parse_consumption_html.
    # The comparison sentence matches the default `_chart_script()` average
    # kWh value so this fixture stays consistent (see `_check_comparison_consistency`)
    # and tests unrelated to that check aren't tripped up by it.
    return (
        "<html><body>"
        "<div><h5>Page Header</h5></div>"
        "<div>"
        f"<h5>{heading_text}</h5>"
        "<canvas id='100583bar'></canvas>"
        f"<script>{script}</script>"
        "<div>Sie haben im Mai 2026 weniger als vergleichbare Haushalte verbraucht.</div>"
        "</div></body></html>"
    )


# ---------------------------------------------------------------------------
# parse_consumption_html — error branches
# ---------------------------------------------------------------------------


class TestParseConsumptionHtmlErrors:
    def test_only_hot_water_raises_heating_not_found(self) -> None:
        html = _heading_html("Warmwasser", _chart_script())
        with pytest.raises(ParseError, match="Heating meter data not found"):
            parse_consumption_html(html)

    def test_only_heating_raises_hot_water_not_found(self) -> None:
        html = _heading_html("Heizung", _chart_script())
        with pytest.raises(ParseError, match="Hot-water meter data not found"):
            parse_consumption_html(html)


# ---------------------------------------------------------------------------
# parse_consumption_html — kWh / comparison-sentence consistency
# ---------------------------------------------------------------------------


def _both_meters_html(comparison_div: str, heating_script: str | None = None) -> str:
    """Build minimal consumption HTML for both meters using the given comparison div."""
    script = _chart_script()
    return (
        "<html><body>"
        "<li class='tab col s6 m3'><a href='#0001-001'>0001-001&nbsp;&nbsp;Max Mustermann</a></li>"
        f"<div><h5>Heizung</h5><canvas id='hzbar'></canvas>"
        f"<script>{heating_script or script}</script>"
        f"{comparison_div}</div>"
        f"<div><h5>Warmwasser</h5><canvas id='wwbar'></canvas><script>{script}</script>"
        "<div>Sie haben im Mai 2026 weniger als vergleichbare Haushalte verbraucht.</div></div>"
        "</body></html>"
    )


class TestBuildMeterReportConsistency:
    def test_average_kwh_without_sentence_raises(self) -> None:
        # _chart_script() defaults to a non-zero average_kwh (65.0), so a
        # comparison div lacking the "vergleichbare Haushalte" sentence is
        # inconsistent and must fail fast.
        html = _both_meters_html("<div>Keine Vergleichssätze hier.</div>")
        with pytest.raises(ParseError, match="vs_average.*kWh value .* present but"):
            parse_consumption_html(html)

    def test_sentence_without_average_kwh_raises(self) -> None:
        html = _both_meters_html(
            "<div>Sie haben im Mai 2026 weniger als vergleichbare Haushalte verbraucht.</div>",
            heating_script=_chart_script(avg_data="[null]"),
        )
        with pytest.raises(ParseError, match="vs_average.*comparison sentence present but"):
            parse_consumption_html(html)

    def test_zero_average_kwh_without_sentence_is_not_an_inconsistency(self) -> None:
        # A 0 kWh value with no backing sentence is treated as "not present"
        # rather than a genuine reading, since the portal cannot reliably be
        # told apart here — this must not raise.
        html = _both_meters_html(
            "<div>Keine Vergleichssätze hier.</div>",
            heating_script=_chart_script(avg_data="[0.0]"),
        )
        report = parse_consumption_html(html)
        assert report.heating.average_kwh is None or report.heating.average_kwh == 0.0
        assert report.heating.vs_average is None

    def test_consistent_html_parses_without_error(self) -> None:
        html = _both_meters_html(
            "<div>Sie haben im Mai 2026 weniger als vergleichbare Haushalte verbraucht.</div>"
        )
        report = parse_consumption_html(html)
        assert report.heating.vs_average is Comparison.LESS
        assert report.hot_water.vs_average is Comparison.LESS


# ---------------------------------------------------------------------------
# _check_comparison_consistency
# ---------------------------------------------------------------------------


class TestCheckComparisonConsistency:
    def test_kwh_present_and_sentence_present_is_consistent(self) -> None:
        _check_comparison_consistency("label", 10.0, sentence_present=True)

    def test_kwh_none_and_sentence_absent_is_consistent(self) -> None:
        _check_comparison_consistency("label", None, sentence_present=False)

    def test_kwh_present_and_sentence_absent_raises(self) -> None:
        with pytest.raises(ParseError, match="present but comparison sentence is missing"):
            _check_comparison_consistency("label", 10.0, sentence_present=False)

    def test_kwh_none_and_sentence_present_raises(self) -> None:
        with pytest.raises(ParseError, match="comparison sentence present but kWh value"):
            _check_comparison_consistency("label", None, sentence_present=True)

    def test_zero_kwh_and_sentence_absent_is_treated_as_not_present(self) -> None:
        # A 0 kWh reading without a backing sentence is regarded as "value
        # not present" rather than a genuine 0, so this must not raise.
        _check_comparison_consistency("label", 0.0, sentence_present=False)

    def test_zero_kwh_and_sentence_present_is_consistent(self) -> None:
        _check_comparison_consistency("label", 0.0, sentence_present=True)


# ---------------------------------------------------------------------------
# _extract_chart_config
# ---------------------------------------------------------------------------


class TestExtractChartConfig:
    def test_no_new_chart_call_raises(self) -> None:
        with pytest.raises(ParseError, match="new Chart"):
            _extract_chart_config("var x = 1;", "test")

    def test_new_chart_without_brace_raises(self) -> None:
        with pytest.raises(ParseError, match="Chart config object not found"):
            _extract_chart_config("new Chart(ctx)", "test")

    def test_unbalanced_braces_raises(self) -> None:
        with pytest.raises(ParseError, match="Unbalanced braces"):
            _extract_chart_config("new Chart(ctx, {unclosed", "test")

    def test_valid_extraction(self) -> None:
        block = _extract_chart_config("new Chart(ctx, {type: 'bar'})", "test")
        assert block == "{type: 'bar'}"


# ---------------------------------------------------------------------------
# _parse_chart_script
# ---------------------------------------------------------------------------


class TestParseChartScript:
    def test_json5_parse_error_raises(self) -> None:
        script = "new Chart(ctx, {broken: ::: !!})"
        with pytest.raises(ParseError, match="Failed to parse Chart.js config"):
            _parse_chart_script(script, "test_hz")

    def test_missing_data_key_raises(self) -> None:
        script = "new Chart(ctx, {type: 'bar'})"
        with pytest.raises(ParseError, match="Unexpected Chart.js config structure"):
            _parse_chart_script(script, "test_hz")

    def test_user_dataset_missing_raises(self) -> None:
        script = _chart_script(your_label="Wrong label", avg_label="vergleichbare Haushalte")
        with pytest.raises(ParseError, match="Ihr Verbrauch"):
            _parse_chart_script(script, "test_hz")

    def test_avg_dataset_missing_raises(self) -> None:
        script = _chart_script(avg_label="Other dataset")
        with pytest.raises(ParseError, match="vergleichbare Haushalte"):
            _parse_chart_script(script, "test_hz")

    def test_non_numeric_data_raises(self) -> None:
        script = _chart_script(your_data="['not_a_number']")
        with pytest.raises(ParseError, match="Non-numeric"):
            _parse_chart_script(script, "test_hz")

    def test_all_empty_labels_raises_no_readings(self) -> None:
        script = _chart_script(labels="['', '']", your_data="[1.0, 2.0]", avg_data="[3.0, 4.0]")
        with pytest.raises(ParseError, match="No readings found"):
            _parse_chart_script(script, "test_hz")

    def test_null_data_value_becomes_none(self) -> None:
        """A JSON ``null`` data point means "not supplied", distinct from 0.0."""
        script = _chart_script(your_data="[null]", avg_data="[0.0]")
        chart = _parse_chart_script(script, "test_hz")
        assert chart.readings[0].your_kwh is None
        assert chart.readings[0].average_kwh == pytest.approx(0.0)

    def test_missing_trailing_data_point_becomes_none(self) -> None:
        """Fewer data points than labels means the missing months become None, not 0.0."""
        script = _chart_script(
            labels="['Mai 2026', 'April 2026']",
            your_data="[55.0]",
            avg_data="[65.0]",
        )
        chart = _parse_chart_script(script, "test_hz")
        assert len(chart.readings) == 2
        assert chart.readings[1].your_kwh is None
        assert chart.readings[1].average_kwh is None

    def test_valid_script_returns_chart_data(self) -> None:
        chart = _parse_chart_script(_chart_script(), "test_hz")
        assert chart.month == 5
        assert chart.year == 2026
        assert len(chart.readings) == 1


# ---------------------------------------------------------------------------
# _parse_german_month_year
# ---------------------------------------------------------------------------


class TestParseGermanMonthYear:
    def test_wrong_part_count_raises(self) -> None:
        with pytest.raises(ParseError, match="Unexpected chart label format"):
            _parse_german_month_year("Mai 2026 extra", "test")

    def test_unknown_month_name_raises(self) -> None:
        with pytest.raises(ParseError, match="Unknown German month name"):
            _parse_german_month_year("Octember 2026", "test")

    def test_valid_label(self) -> None:
        month, year = _parse_german_month_year("Mai 2026", "test")
        assert month == 5
        assert year == 2026


# ---------------------------------------------------------------------------
# _parse_direction
# ---------------------------------------------------------------------------


class TestParseDirection:
    def test_weniger_returns_less(self) -> None:
        assert _parse_direction("Sie haben weniger verbraucht") is Comparison.LESS

    def test_mehr_returns_more(self) -> None:
        assert _parse_direction("Sie haben mehr verbraucht") is Comparison.MORE

    def test_soviel_returns_equal(self) -> None:
        result = _parse_direction("Sie haben soviel wie vergleichbare Haushalte verbraucht")
        assert result is Comparison.EQUAL

    def test_no_keyword_returns_none(self) -> None:
        assert _parse_direction("Keine Angabe hier") is None


# ---------------------------------------------------------------------------
# _classify_reference
# ---------------------------------------------------------------------------


class TestClassifyReference:
    def test_vs_average(self) -> None:
        assert _classify_reference("vergleichbare Haushalte im Vergleich", 5, 2026) == "vs_average"

    def test_no_als_im_returns_none(self) -> None:
        assert _classify_reference("some random text", 5, 2026) is None

    def test_als_im_no_regex_match_returns_none(self) -> None:
        # "als im" present but no German month+year follows
        assert _classify_reference("weniger als im Sommer verbraucht", 5, 2026) is None

    def test_unknown_month_in_reference_returns_none(self) -> None:
        assert _classify_reference("weniger als im Octember 2025 verbraucht", 5, 2026) is None

    def test_vs_previous_month(self) -> None:
        assert _classify_reference("weniger als im April 2026 verbraucht", 5, 2026) == (
            "vs_previous_month"
        )

    def test_vs_previous_year(self) -> None:
        assert _classify_reference("weniger als im Mai 2025 verbraucht", 5, 2026) == (
            "vs_previous_year"
        )

    def test_unrelated_reference_returns_none(self) -> None:
        # Reference to a month that is neither previous month nor same month previous year
        assert _classify_reference("weniger als im März 2024 verbraucht", 5, 2026) is None


# ---------------------------------------------------------------------------
# _process_meter_heading
# ---------------------------------------------------------------------------


class TestProcessMeterHeading:
    def test_non_tag_returns_none(self) -> None:
        assert _process_meter_heading("not a tag") is None

    def test_unrelated_heading_returns_none(self) -> None:
        soup = BeautifulSoup("<div><h5>Some other heading</h5></div>", "lxml")
        heading = soup.find("h5")
        assert _process_meter_heading(heading) is None

    def test_heading_without_canvas_returns_none(self) -> None:
        soup = BeautifulSoup("<div><h5>Heizung</h5></div>", "lxml")
        heading = soup.find("h5")
        assert _process_meter_heading(heading) is None

    def test_heading_with_canvas_but_no_chart_script_raises(self) -> None:
        soup = BeautifulSoup(
            "<div><h5>Heizung</h5><canvas id='100583bar'></canvas><script>var x=1</script></div>",
            "lxml",
        )
        heading = soup.find("h5")
        with pytest.raises(ParseError, match="Chart script not found"):
            _process_meter_heading(heading)


# ---------------------------------------------------------------------------
# _find_comparison_text_in
# ---------------------------------------------------------------------------


class TestFindComparisonTextIn:
    def test_no_matching_div_returns_empty_string(self) -> None:
        soup = BeautifulSoup("<div><div>unrelated text</div></div>", "lxml")
        container = soup.find("div")
        assert isinstance(container, Tag)
        assert _find_comparison_text_in(container) == ""

    def test_matching_div_returns_its_text(self) -> None:
        soup = BeautifulSoup(
            "<div><div>Sie haben im Mai 2026 weniger verbraucht.</div></div>", "lxml"
        )
        container = soup.find("div")
        assert isinstance(container, Tag)
        assert "Sie haben im Mai 2026" in _find_comparison_text_in(container)


# ---------------------------------------------------------------------------
# _parse_comparisons
# ---------------------------------------------------------------------------


class TestParseComparisons:
    def test_empty_text_returns_empty_dict(self) -> None:
        assert _parse_comparisons("   ", 5, 2026) == {}

    def test_no_sentence_match_returns_empty_dict(self) -> None:
        assert _parse_comparisons("Keine Richtung hier", 5, 2026) == {}

    def test_vs_average_found(self) -> None:
        text = "Sie haben im Mai 2026 weniger als vergleichbare Haushalte verbraucht."
        result = _parse_comparisons(text, 5, 2026)
        assert result.get("vs_average") is Comparison.LESS

    def test_multiple_sentences_joined_without_separator(self) -> None:
        # Mirrors how the portal concatenates <br>-joined sentences with no
        # whitespace between them once inline <span> tags are stripped.
        text = (
            "Sie haben im Mai 2026 weniger als vergleichbare Haushalte verbraucht."
            "Sie haben im Mai 2026 mehr als im April 2026 verbraucht."
            "Sie haben im Mai 2026 soviel wie im Mai 2025 verbraucht."
        )
        result = _parse_comparisons(text, 5, 2026)
        assert result["vs_average"] is Comparison.LESS
        assert result["vs_previous_month"] is Comparison.MORE
        assert result["vs_previous_year"] is Comparison.EQUAL

    def test_sentence_without_direction_keyword_raises(self) -> None:
        # A full "Sie haben im ... verbraucht." sentence that lacks any of the
        # known direction keywords ("weniger"/"mehr"/"soviel") must fail fast
        # rather than silently be dropped.
        text = "Sie haben im Mai 2026 genauso als vergleichbare Haushalte verbraucht."
        with pytest.raises(ParseError, match="recognized direction"):
            _parse_comparisons(text, 5, 2026)


_UNIT_TAB_HTML = (
    "<li class='tab col s6 m3'><a href='#0001-001'>0001-001&nbsp;&nbsp;Max Mustermann</a></li>"
)


class TestParseObjectInfo:
    def test_label_without_value_sibling_is_skipped(self) -> None:
        soup = BeautifulSoup(
            "<html><body><span class='field-label'>ausgewähltes Objekt</span>"
            f"{_UNIT_TAB_HTML}</body></html>",
            "lxml",
        )
        info = _parse_object_info(soup)
        assert info.object_number == ""
        assert info.address == ""

    def test_both_fields_populated(self) -> None:
        html = (
            "<html><body>"
            "<span class='field-label'>ausgewähltes Objekt</span>"
            "<div class='mt-1'>"
            "<span class='field-value'>123-456</span><br>"
            "<span class='text-gray-600'>Musterstraße 1</span><br>"
            "<span class='text-gray-600'>12345 Musterstadt</span>"
            "</div>"
            f"{_UNIT_TAB_HTML}"
            "</body></html>"
        )
        info = _parse_object_info(BeautifulSoup(html, "lxml"))
        assert info.object_number == "123-456"
        assert info.address == "Musterstraße 1, 12345 Musterstadt"
        assert info.unit_id == "0001-001"
        assert info.occupant_name == "Max Mustermann"

    def test_unrecognised_label_is_ignored(self) -> None:
        html = (
            "<html><body>"
            "<span class='field-label'>Sonstige Info</span>"
            "<div class='mt-1'><span class='field-value'>Wert</span></div>"
            f"{_UNIT_TAB_HTML}"
            "</body></html>"
        )
        info = _parse_object_info(BeautifulSoup(html, "lxml"))
        assert info.object_number == ""
        assert info.address == ""

    def test_missing_unit_tab_raises(self) -> None:
        html = (
            "<html><body>"
            "<span class='field-label'>ausgewähltes Objekt</span>"
            "<div class='mt-1'><span class='field-value'>123-456</span></div>"
            "</body></html>"
        )
        with pytest.raises(ParseError, match="Unit tab"):
            _parse_object_info(BeautifulSoup(html, "lxml"))

    def test_malformed_unit_tab_identifier_raises(self) -> None:
        html = (
            "<html><body>"
            "<li class='tab col s6 m3'><a href='#not-a-valid-id'>Max Mustermann</a></li>"
            "</body></html>"
        )
        with pytest.raises(ParseError, match="Unexpected unit tab identifier format"):
            _parse_object_info(BeautifulSoup(html, "lxml"))

    def test_empty_occupant_name_raises(self) -> None:
        html = (
            "<html><body>"
            "<li class='tab col s6 m3'><a href='#0001-001'>0001-001</a></li>"
            "</body></html>"
        )
        with pytest.raises(ParseError, match="Occupant name not found"):
            _parse_object_info(BeautifulSoup(html, "lxml"))
