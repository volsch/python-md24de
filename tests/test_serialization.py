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
from md24de._serialization import _to_json_value  # pyright: ignore[reportPrivateUsage]


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

    def test_unsupported_value_type_raises_parse_error(self) -> None:
        """_to_json_value() must reject types it has no defined mapping for."""
        with pytest.raises(ParseError, match="Cannot serialize value of type"):
            _to_json_value(object())

    def test_omits_none_kwh_values(self) -> None:
        """A missing (None) kwh value is omitted from JSON, like other None fields."""
        report = ConsumptionReport(
            object_info=ObjectInfo(object_number="1", address="a"),
            heating=MeterReport(
                current_kwh=None,
                average_kwh=200.0,
                vs_average=None,
                vs_previous_month=None,
                vs_previous_year=None,
                history=(MeterReading(year=2026, month=5, your_kwh=None, average_kwh=200.0),),
            ),
            hot_water=MeterReport(
                current_kwh=50.0,
                average_kwh=60.0,
                vs_average=None,
                vs_previous_month=None,
                vs_previous_year=None,
                history=(MeterReading(year=2026, month=5, your_kwh=50.0, average_kwh=60.0),),
            ),
        )
        data = json.loads(dump_consumption_report(report))
        assert "current_kwh" not in data["heating"]
        assert "your_kwh" not in data["heating"]["history"][0]


class TestLoadConsumptionReport:
    def test_roundtrip(self, report: ConsumptionReport) -> None:
        text = dump_consumption_report(report)
        assert load_consumption_report(text) == report

    def test_missing_comparison_becomes_none(self, report: ConsumptionReport) -> None:
        text = dump_consumption_report(report)
        loaded = load_consumption_report(text)
        assert loaded.heating.vs_previous_month is None

    def test_omitted_kwh_values_round_trip_to_none(self) -> None:
        """A kwh value omitted from the JSON (because it was None) reloads as None."""
        text = (
            '{"object_info":{"object_number":"1","address":"a"},'
            '"heating":{"average_kwh":200.0,'
            '"history":[{"year":2026,"month":5,"average_kwh":200.0}]},'
            '"hot_water":{"current_kwh":50.0,"average_kwh":60.0,'
            '"history":[{"year":2026,"month":5,"your_kwh":50.0,"average_kwh":60.0}]}}'
        )
        loaded = load_consumption_report(text)
        assert loaded.heating.current_kwh is None
        assert loaded.heating.history[0].your_kwh is None

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
