"""Dimension-checked unit conversion and network transfer estimates; no external I/O."""
import json
import math

from app.core.tool_registry import failed

# dimension, multiplier to base unit, offset in base units
UNITS = {
    "m": ("length", 1, 0), "km": ("length", 1000, 0), "cm": ("length", .01, 0),
    "mm": ("length", .001, 0), "in": ("length", .0254, 0), "ft": ("length", .3048, 0),
    "kg": ("mass", 1, 0), "g": ("mass", .001, 0), "lb": ("mass", .45359237, 0),
    "s": ("time", 1, 0), "min": ("time", 60, 0), "h": ("time", 3600, 0),
    "B": ("data", 1, 0), "KB": ("data", 1000, 0), "MB": ("data", 1e6, 0), "GB": ("data", 1e9, 0),
    "KiB": ("data", 1024, 0), "MiB": ("data", 1024 ** 2, 0), "GiB": ("data", 1024 ** 3, 0),
    "K": ("temperature", 1, 0), "C": ("temperature", 1, 273.15),
    "F": ("temperature", 5 / 9, 273.15 - 32 * 5 / 9),
    "J": ("energy", 1, 0), "kJ": ("energy", 1000, 0), "Wh": ("energy", 3600, 0), "kWh": ("energy", 3.6e6, 0),
    "W": ("power", 1, 0), "kW": ("power", 1000, 0),
}


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e15:
        raise ValueError("Values must be finite numbers with magnitude at most 1e15.")
    return value


def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    try:
        value = _finite(value)
        if not isinstance(from_unit, str) or not isinstance(to_unit, str) or from_unit not in UNITS or to_unit not in UNITS:
            raise ValueError("Use a supported, case-sensitive unit: " + ", ".join(UNITS))
        dimension, scale, offset = UNITS[from_unit]
        target, target_scale, target_offset = UNITS[to_unit]
        if dimension != target:
            raise ValueError("Cannot convert between different dimensions.")
        base = value * scale + offset
        if dimension == "temperature" and base < -1e-10:
            raise ValueError("Temperature cannot be below absolute zero.")
        if dimension == "temperature":
            base = max(0, base)
        converted = (base - target_offset) / target_scale
    except ValueError as e:
        return failed(f"Error: {e}")
    return json.dumps({"value": value, "from_unit": from_unit, "to_unit": to_unit,
                       "result": converted, "dimension": dimension,
                       "note": "Temperature conversions are absolute temperatures, not temperature differences. KB/MB/GB are decimal bytes; KiB/MiB/GiB are binary bytes."}, indent=2)


def estimate_transfer(size: float, size_unit: str, bandwidth_mbps: float,
                      utilization_percent: float = 80) -> str:
    try:
        size, bandwidth, utilization = map(_finite, (size, bandwidth_mbps, utilization_percent))
        if not isinstance(size_unit, str) or size_unit not in UNITS or UNITS[size_unit][0] != "data":
            raise ValueError("size_unit must be B, KB, MB, GB, KiB, MiB or GiB.")
        if size < 0 or bandwidth <= 0 or not 0 < utilization <= 100:
            raise ValueError("Size must be nonnegative, bandwidth positive and utilization in (0, 100].")
        seconds = size * UNITS[size_unit][1] * 8 / (bandwidth * 1e6 * utilization / 100)
        if not math.isfinite(seconds):
            raise ValueError("This input combination exceeds the supported numeric range.")
    except (ValueError, ZeroDivisionError) as e:
        return failed(f"Error: {e}")
    return json.dumps({"seconds": seconds, "minutes": seconds / 60,
                       "effective_mbps": bandwidth * utilization / 100,
                       "assumptions": "Constant effective rate. Mbps means decimal megabits/second; file size is bytes. Estimate excludes setup, retries and changing congestion; not a measured speed test."}, indent=2)
