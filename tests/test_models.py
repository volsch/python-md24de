"""Tests for data models."""

from __future__ import annotations

import pytest

from md24de import (
    AvailableMonth,
    Comparison,
    ConsumptionReport,
    MeterReading,
    MeterReport,
    ObjectInfo,
)


class TestComparison:
    def test_values(self) -> None:
        assert Comparison.LESS.value == "less"
        assert Comparison.MORE.value == "more"
        assert Comparison.EQUAL.value == "equal"
        assert Comparison.LESS.value == "less"
        assert Comparison.MORE.value == "more"

    def test_members(self) -> None:
        assert set(Comparison) == {Comparison.LESS, Comparison.MORE, Comparison.EQUAL}


class TestAvailableMonth:
    def test_creation(self) -> None:
        m = AvailableMonth(year=2026, month=5)
        assert m.month == 5
        assert m.year == 2026

    def test_frozen(self) -> None:
        m = AvailableMonth(year=2026, month=5)
        with pytest.raises(AttributeError):
            m.month = 6  # type: ignore[misc]

    def test_equality(self) -> None:
        assert AvailableMonth(year=2026, month=5) == AvailableMonth(year=2026, month=5)
        assert AvailableMonth(year=2026, month=5) != AvailableMonth(year=2026, month=6)

    def test_hashable(self) -> None:
        s = {AvailableMonth(year=2026, month=5), AvailableMonth(year=2026, month=5)}
        assert len(s) == 1


class TestMeterReading:
    def test_creation(self) -> None:
        r = MeterReading(year=2026, month=5, your_kwh=55.0, average_kwh=65.0)
        assert r.month == 5
        assert r.year == 2026
        assert r.your_kwh == pytest.approx(55.0)
        assert r.average_kwh == pytest.approx(65.0)

    def test_frozen(self) -> None:
        r = MeterReading(year=2026, month=5, your_kwh=55.0, average_kwh=65.0)
        with pytest.raises(AttributeError):
            r.your_kwh = 0.0  # type: ignore[misc]


class TestMeterReport:
    def _make(self) -> MeterReport:
        return MeterReport(
            current_kwh=55.0,
            average_kwh=65.0,
            vs_average=Comparison.LESS,
            vs_previous_month=Comparison.LESS,
            vs_previous_year=Comparison.LESS,
            history=(MeterReading(year=2026, month=5, your_kwh=55.0, average_kwh=65.0),),
        )

    def test_creation(self) -> None:
        r = self._make()
        assert r.current_kwh == pytest.approx(55.0)
        assert r.vs_average is Comparison.LESS
        assert r.vs_previous_month is Comparison.LESS
        assert r.vs_previous_year is Comparison.LESS

    def test_optional_fields_none(self) -> None:
        r = MeterReport(
            current_kwh=0.0,
            average_kwh=210.0,
            vs_average=Comparison.LESS,
            vs_previous_month=None,
            vs_previous_year=None,
            history=(),
        )
        assert r.vs_previous_month is None
        assert r.vs_previous_year is None

    def test_history_is_tuple(self) -> None:
        r = self._make()
        assert isinstance(r.history, tuple)

    def test_frozen(self) -> None:
        r = self._make()
        with pytest.raises(AttributeError):
            r.current_kwh = 0.0  # type: ignore[misc]


class TestObjectInfo:
    def test_creation(self) -> None:
        o = ObjectInfo(
            object_number="000-000000",
            address="Musterstr. 1, 12345 Berlin",
            unit_id="0001-001",
            occupant_name="Max Mustermann",
        )
        assert o.object_number == "000-000000"
        assert o.address == "Musterstr. 1, 12345 Berlin"
        assert o.unit_id == "0001-001"
        assert o.occupant_name == "Max Mustermann"

    def test_frozen(self) -> None:
        o = ObjectInfo(
            object_number="x",
            address="y",
            unit_id="0001-001",
            occupant_name="Max Mustermann",
        )
        with pytest.raises(AttributeError):
            o.object_number = "z"  # type: ignore[misc]


class TestConsumptionReport:
    def test_frozen(self) -> None:
        report = ConsumptionReport(
            object_info=ObjectInfo(
                object_number="x",
                address="y",
                unit_id="0001-001",
                occupant_name="Max Mustermann",
            ),
            heating=MeterReport(
                current_kwh=0.0,
                average_kwh=210.0,
                vs_average=Comparison.LESS,
                vs_previous_month=None,
                vs_previous_year=Comparison.LESS,
                history=(),
            ),
            hot_water=MeterReport(
                current_kwh=55.0,
                average_kwh=65.0,
                vs_average=Comparison.LESS,
                vs_previous_month=Comparison.LESS,
                vs_previous_year=Comparison.LESS,
                history=(),
            ),
        )
        with pytest.raises(AttributeError):
            report.object_info = ObjectInfo(  # type: ignore[misc]
                object_number="z",
                address="w",
                unit_id="0002-001",
                occupant_name="Erika Musterfrau",
            )
