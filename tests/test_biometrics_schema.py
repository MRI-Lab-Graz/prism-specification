"""The biometrics schema guides template authors: one field per fact, clear hardware/software/trial wording."""

import json
from pathlib import Path

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "schemas/stable/biometrics.schema.json").read_text())
STUDY = SCHEMA["properties"]["Study"]["properties"]
TECH = SCHEMA["properties"]["Technical"]["properties"]
ITEM = SCHEMA["additionalProperties"]["properties"]


def test_muscular_power_is_a_category():
    assert "muscular-power" in STUDY["Category"]["enum"]


def test_aliases_are_gone():
    assert "Instruction" not in STUDY and "Reference" not in STUDY


def test_equipment_is_hardware_and_software_goes_elsewhere():
    assert "SoftwarePlatform" in TECH["Equipment"]["description"]


def test_run_hint_is_not_a_trial_number():
    assert "not a trial" in ITEM["RunHint"]["description"]


def test_item_description_stays_short():
    assert "no device or protocol" in ITEM["Description"]["description"]
