"""Tests for JSON (de)serialization of ConsumptionReport."""

from __future__ import annotations

import json

import pytest

from md24de import (
    Comparison,
    ConsumptionReport,
    MeterReading,
    MeterReport,
    ObjectInfo,
    ParseError,
    dump_consumption_report,
    load_consumption_report,
)


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
            vs_previous_month=None,
            vs_previous_year=Comparison.LESS,
            history=(
                MeterReading(year=2026, month=5, your_kwh=0.0, average_kwh=200.0),
                MeterReading(year=2026, month=4, your_kwh=150.0, average_kwh=300.0),
            ),
        ),
        hot_water=MeterReport(
            current_kwh=50.0,
            average_kwh=60.0,
            vs_average=Comparison.LESS,
            vs_previous_month=Comparison.MORE,
            vs_previous_year=Comparison.EQUAL,
            history=(MeterReading(year=2026, month=5, your_kwh=50.0, average_kwh=60.0),),
        ),
    )


class TestDumpConsumptionReport:
    def test_is_compact(self, report: ConsumptionReport) -> None:
        text = dump_consumption_report(report)
        assert "\n" not in text
        assert ": " not in text
        assert '", "' not in text  # no space after JSON separators (address itself has ", ")

    def test_omits_none_fields(self, report: ConsumptionReport) -> None:
        text = dump_consumption_report(report)
        data = json.loads(text)
        assert "vs_previous_month" not in data["heating"]
        assert "vs_previous_year" in data["heating"]

    def test_comparison_as_value(self, report: ConsumptionReport) -> None:
        data = json.loads(dump_consumption_report(report))
        assert data["heating"]["vs_average"] == "less"
        assert data["hot_water"]["vs_previous_month"] == "more"

    def test_history_is_list(self, report: ConsumptionReport) -> None:
        data = json.loads(dump_consumption_report(report))
        assert data["heating"]["history"] == [
            {"year": 2026, "month": 5, "your_kwh": 0.0, "average_kwh": 200.0},
            {"year": 2026, "month": 4, "your_kwh": 150.0, "average_kwh": 300.0},
        ]


class TestLoadConsumptionReport:
    def test_roundtrip(self, report: ConsumptionReport) -> None:
        text = dump_consumption_report(report)
        assert load_consumption_report(text) == report

    def test_missing_comparison_becomes_none(self, report: ConsumptionReport) -> None:
        text = dump_consumption_report(report)
        loaded = load_consumption_report(text)
        assert loaded.heating.vs_previous_month is None

    def test_invalid_json_raises_parse_error(self) -> None:
        with pytest.raises(ParseError):
            load_consumption_report("not json")

    def test_non_object_json_raises_parse_error(self) -> None:
        with pytest.raises(ParseError):
            load_consumption_report("[1, 2, 3]")

    def test_missing_field_raises_parse_error(self) -> None:
        with pytest.raises(ParseError):
            load_consumption_report('{"object_info": {"object_number": "1", "address": "a"}}')

    def test_unknown_comparison_value_raises_parse_error(self) -> None:
        text = (
            '{"object_info":{"object_number":"1","address":"a"},'
            '"heating":{"current_kwh":0.0,"average_kwh":0.0,"vs_average":"bogus",'
            '"history":[{"year":2026,"month":5,"your_kwh":0.0,"average_kwh":0.0}]},'
            '"hot_water":{"current_kwh":0.0,"average_kwh":0.0,'
            '"history":[{"year":2026,"month":5,"your_kwh":0.0,"average_kwh":0.0}]}}'
        )
        with pytest.raises(ParseError):
            load_consumption_report(text)
