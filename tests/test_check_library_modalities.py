"""check_library also covers library/biometrics, biosample and environment: descriptive metadata is English."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_library  # noqa: E402

GOOD = {
    "I18n": {"Languages": ["en"]},
    "Technical": {"Type": "PhysicalPerformance", "FileFormat": "tsv", "Equipment": {"en": "Tape"}},
    "Study": {"BiometricName": "x", "OriginalName": {"de": "Sprungtest"}, "Instructions": {"de": "Springen Sie so hoch wie möglich."},
              "Description": {"en": "Vertical jump height."}},
    "x_1": {"DataType": "float", "Description": {"en": "Jump height, trial 1"}, "Units": "cm"},
}


def problems(tmp_path, mutate, modality="biometrics"):
    data = copy.deepcopy(GOOD)
    mutate(data)
    folder = tmp_path / "library" / modality
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{modality}-x.json").write_text(json.dumps(data), encoding="utf-8")
    return check_library.check(tmp_path)


def test_good_non_survey_template_passes_and_other_languages_stay_free_in_name_and_instructions(tmp_path):
    assert problems(tmp_path, lambda d: None) == []


@pytest.mark.parametrize("modality", ["biometrics", "biosample", "environment"])
def test_every_non_survey_modality_is_read(tmp_path, modality):
    assert problems(tmp_path, lambda d: d["Study"].update(Description={"de": "Sprunghöhe beim Sprung."}), modality)


def test_other_language_key_in_a_descriptive_field_is_refused(tmp_path):
    out = problems(tmp_path, lambda d: d["Technical"].update(Equipment={"en": "Tape", "de": "Maßband"}))
    assert any("Technical.Equipment" in x for x in out)


def test_german_text_in_a_descriptive_field_is_refused(tmp_path):
    out = problems(tmp_path, lambda d: d["Study"].update(ExclusionCriteria="Akute Erkrankung und kürzliche Verletzungen der Beine"))
    assert any("Study.ExclusionCriteria: text looks German" in x for x in out)


def test_german_item_description_is_refused(tmp_path):
    out = problems(tmp_path, lambda d: d["x_1"].update(Description={"en": "Sprunghöhe", "de": "Sprunghöhe, Versuch 1"}))
    assert any("x_1.Description" in x for x in out)


def test_text_extraction_artefact_is_refused(tmp_path):
    assert problems(tmp_path, lambda d: d["Study"].update(Description={"en": "eﬃcient jump"}))


def test_a_translated_abbreviation_is_refused(tmp_path):
    out = problems(tmp_path, lambda d: d["Study"].update(ShortName={"en": "FAB", "de": "FAB"}))
    assert any("Study.ShortName" in x for x in out)
