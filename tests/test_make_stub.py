"""scripts/make_stub.py: a full template -> a stub with no instrument text (specs/instrument-ids.md)."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_library  # noqa: E402
import fingerprint  # noqa: E402
import make_stub  # noqa: E402

V = Draft7Validator(json.loads((ROOT / "schemas/stable/survey.schema.json").read_text(encoding="utf-8")))

FULL = {
    "Technical": {"StimulusType": "Questionnaire", "FileFormat": "tsv", "Language": "de",
                  "SoftwarePlatform": "LimeSurvey", "SoftwareVersion": "6.0", "Respondent": "self",
                  "AdministrationMethod": "online"},
    "I18n": {"Languages": ["de", "en"]},
    "Study": {
        "TaskName": "ads", "OriginalName": "Allgemeine Depressionsskala", "Citation": "Hautzinger (1993).",
        "LicenseID": "Proprietary", "Category": "Mood, Anxiety & Clinical Screening",
        "Instructions": {"en": "SECRET-INSTRUCTIONS", "de": "GEHEIME-ANWEISUNG"},
        "ArchiveMetadata": {"Durchführung/Instruktion": "SECRET-ARCHIVE", "Titel": "kept"},
    },
    "Metadata": {"SchemaVersion": "2.1.5", "CreationDate": "2026-11-18", "Creator": "x"},
    "ADS01": {
        "Description": {"de": "SECRET-DE-ITEM", "en": "SECRET-EN-ITEM"},
        "Levels": {"0": {"de": "SECRET-LEVEL-0", "en": "x"}, "1": "SECRET-LEVEL-1"},
        "Help": "SECRET-HELP", "OtherOption": {"enabled": True, "label": "SECRET-OTHER"},
        "DataType": "integer", "MinValue": 0, "MaxValue": 3,
        "VariantScales": [{"VariantID": "short", "MinValue": 0, "Levels": {"0": "SECRET-VARIANT"}}],
    },
    "ADS02": {"Description": "SECRET-PLAIN-ITEM", "Levels": {"0": "a"}},
    "ADS03": {"AliasOf": "ADS01"},
}


def test_no_instrument_text_survives():
    out = json.dumps(make_stub.make_stub(FULL), ensure_ascii=False)
    assert "SECRET" not in out and "GEHEIME" not in out


def test_the_stub_is_marked_and_keeps_the_facts():
    s = make_stub.make_stub(FULL)
    assert s["Study"]["ItemTextsIncluded"] is False
    assert s["Study"]["OriginalName"] == "Allgemeine Depressionsskala" and s["Study"]["Citation"]
    assert s["Study"]["ArchiveMetadata"] == {"Titel": "kept"}
    assert "Instructions" not in s["Study"]
    a = s["ADS01"]
    assert a["Description"] is None and a["Levels"] == {"0": None, "1": None}
    assert (a["DataType"], a["MinValue"], a["MaxValue"]) == ("integer", 0, 3)
    assert a["OtherOption"] == {"enabled": True} and "Help" not in a
    assert a["VariantScales"] == [{"VariantID": "short", "MinValue": 0}]
    assert s["ADS03"] == {"AliasOf": "ADS01"}


def test_every_item_with_text_gets_its_fingerprints():
    s = make_stub.make_stub(FULL)
    assert s["ADS01"]["Fingerprint"] == fingerprint.template_fingerprints(FULL)["ADS01"]
    assert set(s["ADS01"]["Fingerprint"]) == {"de", "en"}
    assert s["ADS02"]["Fingerprint"] == {"de": fingerprint.fingerprint("SECRET-PLAIN-ITEM")}
    assert "Fingerprint" not in s["ADS03"]


def test_the_stub_validates_and_passes_the_library_stub_rules():
    s = make_stub.make_stub(FULL)
    assert not list(V.iter_errors(s))
    assert check_library.stub_problems(s) == []


def test_the_input_is_not_changed():
    before = copy.deepcopy(FULL)
    make_stub.make_stub(FULL)
    assert FULL == before


def test_a_stub_cannot_be_stubbed_again():
    with pytest.raises(ValueError):
        make_stub.make_stub(make_stub.make_stub(FULL))


def test_command_line_writes_the_stub(tmp_path):
    f, out = tmp_path / "survey-ads.json", tmp_path / "stub.json"
    f.write_text(json.dumps(FULL), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_stub.py"), str(f), "-o", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text(encoding="utf-8")) == make_stub.make_stub(FULL)
    again = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_stub.py"), str(out)],
                           capture_output=True, text=True, encoding="utf-8")
    assert again.returncode == 1 and "already a stub" in again.stderr
