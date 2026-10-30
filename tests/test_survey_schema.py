import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((ROOT / "schemas/stable/survey.schema.json").read_text())
V = Draft7Validator(SCHEMA)

BASE = {
    "Technical": {
        "StimulusType": "Questionnaire",
        "FileFormat": "tsv",
        "SoftwarePlatform": "LimeSurvey",
        "SoftwareVersion": "6.0",
        "Language": "en",
        "Respondent": "self",
        "AdministrationMethod": "online",
    },
    "Study": {
        "TaskName": "pss",
        "OriginalName": "Perceived Stress Scale",
        "Citation": "Cohen et al. (1983)",
        "LicenseID": "CC-BY-4.0",
        "Category": "Mood, Anxiety & Clinical Screening",
    },
    "Metadata": {"SchemaVersion": "2.0.0", "CreationDate": "2026-10-30", "Creator": "PRISM Studio"},
    "Q01": {"Description": {"en": "I felt stressed"}},
}


def sidecar(block=None, key=None, value=None, drop=None):
    d = copy.deepcopy(BASE)
    if drop:
        del d[block][drop]
    elif block:
        d[block][key] = value
    return d


def valid(d):
    return not list(V.iter_errors(d))


def test_base_sidecar_valid():
    assert valid(BASE)


@pytest.mark.parametrize("block,key", [
    ("Technical", "Respondent"), ("Technical", "Language"), ("Technical", "AdministrationMethod"),
    ("Technical", "SoftwarePlatform"), ("Technical", "StimulusType"), ("Technical", "FileFormat"),
    ("Study", "TaskName"), ("Study", "Citation"), ("Study", "LicenseID"), ("Study", "OriginalName"),
    ("Metadata", "Creator"),
])
def test_empty_string_invalid(block, key):
    assert not valid(sidecar(block, key, ""))


@pytest.mark.parametrize("key,value", [
    ("OriginalName", {"en": "", "de": "Fragebogen"}),
    ("OriginalName", {"de": "Nur Deutsch"}),
    ("Description", {"de": "Nur Deutsch"}),
    ("Instructions", {"de": "Nur Deutsch"}),
    ("Construct", {"de": "Stress"}),
    ("License", {"de": "Nur Deutsch"}),
])
def test_language_object_needs_english(key, value):
    assert not valid(sidecar("Study", key, value))


@pytest.mark.parametrize("key,value", [
    ("OriginalName", {"en": "PSS", "de": "PSS"}),
    ("Description", {"en": "A stress scale", "de": "Eine Stressskala"}),
    ("ShortName", {"de": "PSS"}),  # unchanged: ShortName stays free
    ("Version", {"de": "3.0"}),  # unchanged: Version stays free
])
def test_language_object_valid(key, value):
    assert valid(sidecar("Study", key, value))


def test_creator_required():
    assert not valid(sidecar("Metadata", drop="Creator"))


def test_help_and_other_option_valid():
    d = copy.deepcopy(BASE)
    d["Q01"]["Help"] = {"en": "Pick one"}
    d["Q01"]["OtherOption"] = {"enabled": True}
    assert valid(d)
    d["Q01"]["Help"] = "Pick one"
    d["Q01"]["OtherOption"] = {"enabled": True, "label": {"en": "Other"}}
    assert valid(d)


@pytest.mark.parametrize("key,value", [
    ("Help", 5), ("OtherOption", "yes"), ("OtherOption", {"enabled": "yes"}),
])
def test_help_and_other_option_types(key, value):
    d = copy.deepcopy(BASE)
    d["Q01"][key] = value
    assert not valid(d)


def test_version_and_archive():
    assert SCHEMA["version"] == "2.0.0"
    assert SCHEMA["$id"].endswith("/v2.0.0")
    archived = json.loads((ROOT / "schemas/archive/survey/1.1.1.schema.json").read_text())
    assert archived["version"] == "1.1.1"
