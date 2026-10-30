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
    "I18n": {"Languages": ["en"]},
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


def _nested(path, value):
    d = copy.deepcopy(BASE)
    study = d["Study"]
    if path == "Translation.Notes":
        study["Translation"] = {"Notes": value}
    elif path == "References.Notes":
        study["References"] = [{"Type": "primary", "Notes": value}]
    elif path == "VariantDefinitions.Description":
        study["VariantDefinitions"] = [{"VariantID": "short", "Description": value}]
    else:
        study[path] = value
    return d


MORE_FIELDS = ["Reliability", "Validity", "Norming", "PermissionsNote", "Translation.Notes",
               "References.Notes", "VariantDefinitions.Description"]


@pytest.mark.parametrize("path", MORE_FIELDS)
def test_more_text_fields_need_english(path):
    assert not valid(_nested(path, {"de": "x"}))
    assert not valid(_nested(path, {"en": "", "de": "x"}))
    assert valid(_nested(path, {"en": "x"}))
    assert valid(_nested(path, {"en": "x", "de": "y"}))
    assert valid(_nested(path, "plain string"))


def with_i18n(value=None, drop=False):
    d = copy.deepcopy(BASE)
    if drop:
        del d["I18n"]
    else:
        d["I18n"] = value
    return d


@pytest.mark.parametrize("i18n", [
    {}, {"Languages": []}, {"Languages": ["en", ""]}, {"Languages": ["en", "en"]},
    {"Languages": ["en"], "DefaultLanguage": ""}, {"DefaultLanguage": "en"},
])
def test_i18n_invalid(i18n):
    assert not valid(with_i18n(i18n))


def test_i18n_required():
    assert not valid(with_i18n(drop=True))


@pytest.mark.parametrize("i18n", [
    {"Languages": ["en"]}, {"Languages": ["en", "de"]}, {"Languages": ["en", "de-AT"]},
    {"Languages": ["en", "de"], "DefaultLanguage": "de"},
])
def test_i18n_valid(i18n):
    assert valid(with_i18n(i18n))


def test_project_only_required_is_exact():
    px = SCHEMA["x-prism"]["projectOnlyRequired"]
    assert px == {"Technical": ["Respondent", "AdministrationMethod", "SoftwarePlatform"]}
    assert set(px["Technical"]) <= set(SCHEMA["properties"]["Technical"]["required"])
    assert "projectOnlyRequiredNote" in SCHEMA["x-prism"]
    assert "SoftwareVersion" in SCHEMA["x-prism"]["projectOnlyRequiredNote"]
