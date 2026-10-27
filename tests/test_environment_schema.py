import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

SCHEMA = json.loads((Path(__file__).parent.parent / "schemas/stable/environment.schema.json").read_text())
V = Draft7Validator(SCHEMA)


def sidecar(**col):
    d = {
        "Technical": {"Source": "open-meteo"},
        "Study": {"EnvironmentName": "weather"},
        "Metadata": {"SchemaVersion": "2.0.0", "CreationDate": "2026-10-26"},
        "temp_max_3d": {"Term": "prism:air-temperature", "Window": {"Start": "P3D", "End": "PT0S"}, "Statistic": "max"},
    }
    d["temp_max_3d"].update(col)
    return d


def test_minimal_sidecar_valid():
    assert not list(V.iter_errors(sidecar()))


@pytest.mark.parametrize("start,ok", [("3 days", False), ("-P3D", False), ("P", False), ("PT", False),
                                      ("PT30M", True), ("P1W", True), ("P1DT12H", True)])
def test_window_duration_pattern(start, ok):
    assert (not list(V.iter_errors(sidecar(Window={"Start": start, "End": "PT0S"})))) == ok


def test_statistic_enum():
    assert list(V.iter_errors(sidecar(Statistic="median")))


def test_old_privacy_block_not_required():
    d = sidecar()
    assert "Privacy" not in d and not list(V.iter_errors(d))


def test_version_and_id():
    assert SCHEMA["version"] == "2.1.0"
    assert SCHEMA["$id"].endswith("/v2.1.0")


def test_environment_schema_2_1_0():
    desc = json.dumps(SCHEMA)
    assert "unitless" in desc and '`count`' in desc
    archived = Path(__file__).parent.parent / "schemas/archive/environment/2.0.0.schema.json"
    assert json.loads(archived.read_text())["version"] == "2.0.0"
