"""Session-independent JSON (de)serialization for :class:`ConsumptionReport`."""

from __future__ import annotations

import json
import logging
from dataclasses import fields, is_dataclass
from typing import Any, cast

from md24de._exceptions import ParseError
from md24de._models import (
    Comparison,
    ConsumptionReport,
    MeterReading,
    MeterReport,
    ObjectInfo,
)

_log = logging.getLogger(__name__)

# Recursive JSON value type used while walking the dataclass tree.
type JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


def dump_consumption_report(report: ConsumptionReport) -> str:
    """Serialize *report* to a compact JSON string.

    Fields holding ``None`` (e.g. a comparison the portal did not provide)
    are omitted from the output entirely, rather than being written as
    ``null``. This function does not require an active session — it only
    operates on an already-parsed :class:`ConsumptionReport`.

    Args:
        report: The consumption report to serialize.

    Returns:
        A compact JSON string (no extraneous whitespace).
    """
    data = _to_json_value(report)
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    _log.debug("Serialized consumption report to JSON (%d chars)", len(text))
    return text


def load_consumption_report(data: str) -> ConsumptionReport:
    """Parse a JSON string produced by :func:`dump_consumption_report`.

    Args:
        data: JSON text describing a :class:`ConsumptionReport`.

    Returns:
        The reconstructed :class:`ConsumptionReport`.

    Raises:
        ParseError: If *data* is not valid JSON or does not match the
            expected report structure.
    """
    try:
        parsed: Any = json.loads(data)
        if not isinstance(parsed, dict):
            raise ParseError("Consumption report JSON must be an object")  # noqa: TRY301
        obj = cast(dict[str, Any], parsed)
        report = ConsumptionReport(
            object_info=_object_info_from_dict(cast(dict[str, Any], obj["object_info"])),
            heating=_meter_report_from_dict(cast(dict[str, Any], obj["heating"])),
            hot_water=_meter_report_from_dict(cast(dict[str, Any], obj["hot_water"])),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ParseError(f"Invalid consumption report JSON: {exc}") from exc
    _log.debug("Parsed consumption report from JSON")
    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_json_value(value: object) -> JSONValue:
    """Recursively convert dataclasses/enums/tuples into plain JSON values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _to_json_value(field_value)
            for f in fields(value)
            if (field_value := getattr(value, f.name)) is not None
        }
    if isinstance(value, Comparison):
        return value.value
    if isinstance(value, tuple):
        return [_to_json_value(v) for v in cast(tuple[object, ...], value)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ParseError(f"Cannot serialize value of type {type(value).__name__} to JSON")


def _object_info_from_dict(obj: dict[str, Any]) -> ObjectInfo:
    return ObjectInfo(
        object_number=obj["object_number"],
        address=obj["address"],
        unit_id=obj.get("unit_id", ""),
        occupant_name=obj.get("occupant_name", ""),
    )


def _meter_report_from_dict(obj: dict[str, Any]) -> MeterReport:
    return MeterReport(
        current_kwh=obj.get("current_kwh"),
        average_kwh=obj.get("average_kwh"),
        vs_average=_comparison_from_value(obj.get("vs_average")),
        vs_previous_month=_comparison_from_value(obj.get("vs_previous_month")),
        vs_previous_year=_comparison_from_value(obj.get("vs_previous_year")),
        history=tuple(_meter_reading_from_dict(cast(dict[str, Any], h)) for h in obj["history"]),
    )


def _meter_reading_from_dict(obj: dict[str, Any]) -> MeterReading:
    return MeterReading(
        year=obj["year"],
        month=obj["month"],
        your_kwh=obj.get("your_kwh"),
        average_kwh=obj.get("average_kwh"),
    )


def _comparison_from_value(value: str | None) -> Comparison | None:
    return Comparison(value) if value is not None else None
