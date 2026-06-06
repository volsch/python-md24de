"""Tests for the HTML parser."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup, Tag

from md24de._exceptions import ParseError
from md24de._models import Comparison
from md24de._parser import (  # pyright: ignore[reportPrivateUsage]
    GERMAN_MONTHS,
    _canvas_is_heating,  # pyright: ignore[reportPrivateUsage]
    _classify_reference,  # pyright: ignore[reportPrivateUsage]
    _extract_chart_config,  # pyright: ignore[reportPrivateUsage]
    _is_previous_month,  # pyright: ignore[reportPrivateUsage]
    _is_same_month_previous_year,  # pyright: ignore[reportPrivateUsage]
    _parse_chart_script,  # pyright: ignore[reportPrivateUsage]
    _parse_comparisons,  # pyright: ignore[reportPrivateUsage]
    _parse_direction,  # pyright: ignore[reportPrivateUsage]
    _parse_german_month_year,  # pyright: ignore[reportPrivateUsage]
    _parse_object_info,  # pyright: ignore[reportPrivateUsage]
    _process_meter_h1,  # pyright: ignore[reportPrivateUsage]
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

    # ------------------------------------------------------------------
    # Heating
    # ------------------------------------------------------------------

    def test_heating_current_kwh(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.heating.current_kwh == pytest.approx(0.0)

    def test_heating_average_kwh(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.heating.average_kwh == pytest.approx(134.0)

    def test_heating_vs_average(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.heating.vs_average is Comparison.LESS

    def test_heating_vs_previous_month_is_none(self, consumption_html: str) -> None:
        # May 2026 had 0 kWh heating — portal omits previous-month comparison.
        report = parse_consumption_html(consumption_html)
        assert report.heating.vs_previous_month is None

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
        assert h[0].your_kwh == pytest.approx(0.0) and h[0].average_kwh == pytest.approx(134.0)
        assert h[1].month == 4 and h[1].year == 2026
        assert h[1].your_kwh == pytest.approx(132.0) and h[1].average_kwh == pytest.approx(269.0)
        assert h[2].month == 5 and h[2].year == 2025
        assert h[2].your_kwh == pytest.approx(128.0) and h[2].average_kwh == pytest.approx(134.0)

    # ------------------------------------------------------------------
    # Hot water
    # ------------------------------------------------------------------

    def test_hot_water_current_kwh(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.hot_water.current_kwh == pytest.approx(82.0)

    def test_hot_water_average_kwh(self, consumption_html: str) -> None:
        report = parse_consumption_html(consumption_html)
        assert report.hot_water.average_kwh == pytest.approx(94.0)

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
        assert h[0].your_kwh == pytest.approx(82.0) and h[0].average_kwh == pytest.approx(94.0)
        assert h[1].month == 4 and h[1].year == 2026
        assert h[1].your_kwh == pytest.approx(103.0) and h[1].average_kwh == pytest.approx(91.0)
        assert h[2].month == 5 and h[2].year == 2025
        assert h[2].your_kwh == pytest.approx(115.0) and h[2].average_kwh == pytest.approx(94.0)

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
          <h1>Heizung</h1>
          <div></div>
          <canvas id="chart_med_0001_hz"></canvas>
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
    canvas_id: str = "test_hz",
    labels: str = "['Mai 2026']",
    your_data: str = "[82.0]",
    avg_data: str = "[94.0]",
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


def _h1_html(canvas_suffix: str, script: str) -> str:
    # The leading non-meter <h1> (no canvas) exercises the
    # `if result is None: continue` branch in parse_consumption_html.
    return (
        "<html><body>"
        "<div><h1>Page Header</h1></div>"
        "<div>"
        f"<h1>Meter Heading</h1>"
        f"<canvas id='chart_med_0001_{canvas_suffix}'></canvas>"
        f"<script>{script}</script>"
        "</div></body></html>"
    )


# ---------------------------------------------------------------------------
# parse_consumption_html — error branches
# ---------------------------------------------------------------------------


class TestParseConsumptionHtmlErrors:
    def test_only_hot_water_raises_heating_not_found(self) -> None:
        html = _h1_html("ww", _chart_script())
        with pytest.raises(ParseError, match="Heating meter data not found"):
            parse_consumption_html(html)

    def test_only_heating_raises_hot_water_not_found(self) -> None:
        html = _h1_html("hz", _chart_script())
        with pytest.raises(ParseError, match="Hot-water meter data not found"):
            parse_consumption_html(html)


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
# _canvas_is_heating
# ---------------------------------------------------------------------------


class TestCanvasIsHeating:
    def test_hz_returns_true(self) -> None:
        assert _canvas_is_heating("chart_med_0001_hz") is True

    def test_ww_returns_false(self) -> None:
        assert _canvas_is_heating("chart_med_0001_ww") is False

    def test_unknown_suffix_returns_none(self) -> None:
        assert _canvas_is_heating("chart_med_0001_xx") is None


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
# _process_meter_h1
# ---------------------------------------------------------------------------


class TestProcessMeterH1:
    def test_non_tag_returns_none(self) -> None:
        assert _process_meter_h1("not a tag") is None

    def test_h1_without_canvas_returns_none(self) -> None:
        soup = BeautifulSoup("<div><h1>heading</h1></div>", "lxml")
        h1 = soup.find("h1")
        assert _process_meter_h1(h1) is None

    def test_h1_with_unknown_canvas_suffix_returns_none(self) -> None:
        soup = BeautifulSoup(
            "<div><h1>heading</h1><canvas id='chart_unknown_xx'></canvas></div>", "lxml"
        )
        h1 = soup.find("h1")
        assert _process_meter_h1(h1) is None

    def test_h1_with_canvas_but_no_chart_script_raises(self) -> None:
        soup = BeautifulSoup(
            "<div><h1>h</h1><canvas id='chart_med_0001_hz'></canvas><script>var x=1</script></div>",
            "lxml",
        )
        h1 = soup.find("h1")
        with pytest.raises(ParseError, match="Chart script not found"):
            _process_meter_h1(h1)


# ---------------------------------------------------------------------------
# _parse_object_info
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _parse_comparisons
# ---------------------------------------------------------------------------


class TestParseComparisons:
    def test_empty_text_div_is_skipped(self) -> None:
        soup = BeautifulSoup("<div><div>   </div></div>", "lxml")
        div = soup.find("div")
        assert isinstance(div, Tag)
        result = _parse_comparisons(div, 5, 2026)
        assert result == {}

    def test_no_direction_keyword_is_skipped(self) -> None:
        soup = BeautifulSoup("<div><div>Keine Richtung hier</div></div>", "lxml")
        div = soup.find("div")
        assert isinstance(div, Tag)
        result = _parse_comparisons(div, 5, 2026)
        assert result == {}

    def test_vs_average_found(self) -> None:
        soup = BeautifulSoup(
            "<div><div>Sie haben weniger als vergleichbare Haushalte</div></div>", "lxml"
        )
        div = soup.find("div")
        assert isinstance(div, Tag)
        result = _parse_comparisons(div, 5, 2026)
        assert result.get("vs_average") is Comparison.LESS


class TestParseObjectInfo:
    def test_name_div_without_value_sibling_is_skipped(self) -> None:
        soup = BeautifulSoup(
            "<html><body><div class='name'>Objektnummer</div></body></html>", "lxml"
        )
        info = _parse_object_info(soup)
        assert info.object_number == ""

    def test_both_fields_populated(self) -> None:
        html = (
            "<html><body>"
            "<div class='name'>Objektnummer</div><div class='value'>123-456</div>"
            "<div class='name'>Adresse</div><div class='value'>Musterstraße 1</div>"
            "</body></html>"
        )
        info = _parse_object_info(BeautifulSoup(html, "lxml"))
        assert info.object_number == "123-456"
        assert info.address == "Musterstraße 1"

    def test_unrecognised_label_is_ignored(self) -> None:
        html = (
            "<html><body>"
            "<div class='name'>Sonstige Info</div><div class='value'>Wert</div>"
            "</body></html>"
        )
        info = _parse_object_info(BeautifulSoup(html, "lxml"))
        assert info.object_number == ""
        assert info.address == ""
