"""terms/environment: one term per column the environment converter writes."""

import json
from pathlib import Path

TERMS = Path(__file__).resolve().parent.parent / "terms" / "environment"

CONVERTER_COLUMNS = {
    "temp_c", "apparent_temp_c", "dew_point_c", "humidity_pct", "pressure_hpa", "precip_mm",
    "wind_speed_ms", "cloud_cover_pct", "uv_index", "shortwave_radiation_wm2", "aqi",
    "pm25_ug_m3", "pm10_ug_m3", "no2_ug_m3", "o3_ug_m3", "pollen_birch", "pollen_grass",
    "pollen_mugwort", "pollen_ragweed", "pollen_total", "pollen_risk_bin", "elevation_m",
    "sun_hours_today", "hours_since_sun", "moon_illumination_pct", "moon_phase", "hour_bin",
    "season_code", "sun_phase", "heatwave_status", "weather_regime",
}


def test_converter_columns_all_have_terms():
    aliases = set()
    for f in TERMS.glob("*.json"):
        aliases.update(json.loads(f.read_text(encoding="utf-8"))["Aliases"])
    assert aliases == CONVERTER_COLUMNS
