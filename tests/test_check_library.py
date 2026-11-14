"""scripts/check_library.py and the shipped templates (dass, dass21, demo)."""

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_library  # noqa: E402

LIB = ROOT / "library" / "survey"
GOOD = {
    "Technical": {"StimulusType": "Questionnaire", "FileFormat": "tsv", "Language": "en"},
    "I18n": {"Languages": ["en"]},
    "Study": {
        "TaskName": "x",
        "OriginalName": {"en": "X"},
        "License": 'The rights holder says: "Free to copy."',
        "Source": "https://example.org/x",
        "LicenseChecked": "2026-11-14",
        "LicenseTerms": ["Do not sell."],
        "LicenseLanguages": ["en"],
    },
    "X01": {"Description": {"en": "Item"}, "Levels": {"0": {"en": "No"}}},
}


def problems(tmp_path, mutate):
    data = copy.deepcopy(GOOD)
    mutate(data)
    (tmp_path / "library" / "survey").mkdir(parents=True)
    (tmp_path / "library" / "survey" / "survey-x.json").write_text(json.dumps(data), encoding="utf-8")
    return check_library.check(tmp_path)


def test_good_template_passes(tmp_path):
    assert problems(tmp_path, lambda d: None) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["Study"].update(License="Public domain, no quote."),  # a
        lambda d: d["Study"].update(Source="www.example.org"),  # b
        lambda d: d["Study"].update(LicenseChecked="14.11.2026"),  # c
        lambda d: d["Study"].update(LicenseTerms="Do not sell."),  # d
        lambda d: d["Study"].update(LicenseTerms=[]),  # d
        lambda d: d["X01"]["Levels"]["0"].update(de="Nein"),  # e
        lambda d: d["Study"]["OriginalName"].update(de="X"),  # e
        lambda d: d["Study"].pop("LicenseLanguages"),  # e-missing
        lambda d: d["Study"].update(LicenseLanguages=[]),  # e-empty
        lambda d: d["Study"].update(LicenseLanguages=["EN"]),  # e-bad code
        lambda d: d["Study"].update(LicenseLanguages="en"),  # e-not a list
        lambda d: d["Technical"].update(Language="de"),  # e-technical
        lambda d: d["I18n"].update(Languages=["en", "de"]),  # e-i18n
        lambda d: d["Study"].update(License={"en": 'He says: "Free to copy."', "de": "x"}),  # e-license dict
        lambda d: d["Study"].update(ItemCount=1),  # f
        lambda d: d["Study"].update(Subscales={}),  # f
        lambda d: d["X01"].update(Reversed=False),  # f
    ],
    ids=["a", "b", "c", "d-str", "d-empty", "e-levels", "e-name", "e-missing", "e-empty", "e-badcode",
         "e-notlist", "e-technical", "e-i18n", "e-license", "f-itemcount", "f-subscales", "f-reversed"],
)
def test_each_rule_refuses_and_names_the_file(tmp_path, mutate):
    out = problems(tmp_path, mutate)
    assert out and all("survey-x.json" in line for line in out)


def test_refusal_names_the_language(tmp_path):
    out = problems(tmp_path, lambda d: d["X01"]["Levels"]["0"].update(de="Nein"))
    assert any("'de'" in line and "survey-x.json" in line for line in out)


def german(d):
    d["Technical"]["Language"] = "de"
    d["I18n"]["Languages"] = ["de"]
    d["Study"]["LicenseLanguages"] = ["de"]
    d["Study"]["OriginalName"] = {"de": "X"}
    d["X01"] = {"Description": {"de": "Punkt"}, "Levels": {"0": {"de": "Nein"}}}


def test_german_only_template_with_german_evidence_passes(tmp_path):
    assert problems(tmp_path, german) == []


def test_plain_string_german_template_passes(tmp_path):
    def f(d):
        german(d)
        d["X01"] = {"Description": "Punkt"}
    assert problems(tmp_path, f) == []


def test_german_key_in_english_template_is_refused(tmp_path):
    assert problems(tmp_path, lambda d: d["X01"]["Description"].update(de="Punkt"))


def test_cli_exit_code(tmp_path):
    problems(tmp_path, lambda d: d["Study"].update(ItemCount=1))
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_library.py"), "--repo", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "survey-x.json" in r.stdout


def test_every_shipped_template_passes():
    assert check_library.check(ROOT) == []


def derived(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    task = path.stem.removeprefix("survey-")
    items = [k for k, v in data.items() if k not in ("Technical", "Metadata", "I18n", "Study") and isinstance(v, dict)]
    return {f"prism:{task}.{k.lower().replace('_', '-')}" for k in items}


def released(task):
    # score IDs (prism:<task>.score-...) come from the recipes, not from template items
    ids = (ROOT / "ids" / "survey-ids.txt").read_text(encoding="utf-8").split()
    return {i for i in ids if i.startswith(f"prism:{task}.") and not i.startswith(f"prism:{task}.score-")}


@pytest.mark.parametrize("task", ["dass", "dass21", "demo"])
def test_real_template(task):
    path = LIB / f"survey-{task}.json"
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert derived(path) == released(task) and len(derived(path)) == {"dass": 42, "dass21": 21, "demo": 8}[task]
    schema = json.loads((ROOT / "schemas" / "stable" / "survey.schema.json").read_text(encoding="utf-8"))
    project_only = schema["x-prism"]["projectOnlyRequired"]["Technical"]  # optional in a library template
    errs = [e.message for e in Draft7Validator(schema).iter_errors(data)
            if not any(f"'{f}' is a required property" in e.message for f in project_only)]
    assert errs == []
    assert not re.search(r'"(?!en")[a-z]{2}"\s*:\s*"', text)  # no other language key
    assert data["Study"]["Source"] == {"demo": "https://github.com/MRI-Lab-Graz/prism-specification"}.get(task, "https://www2.psy.unsw.edu.au/dass/")
    assert data["Study"]["LicenseChecked"] == "2026-11-14"
    assert data["I18n"]["Languages"] == ["en"]
