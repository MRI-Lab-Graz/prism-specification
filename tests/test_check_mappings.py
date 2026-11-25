"""scripts/check_mappings.py, scripts/survey_ids.py and the move of TermURL into mappings/."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_mappings  # noqa: E402
import check_terms  # noqa: E402
import survey_ids  # noqa: E402

URL = "https://example.org/thing/123"  # test-only vocabulary `example`, not a real code
VOCABS = {"example": {"pattern": r"^https://example\.org/[a-z]+/\d+$", "label": "Test vocabulary"}}
BIOSAMPLE_TERMS = {
    "cortisol": {"TermID": "prism:cortisol", "Level": "analyte", "Label": "cortisol", "Status": "official"},
    "cortisol.serum": {"TermID": "prism:cortisol.serum", "Level": "analyte-specimen", "Parent": "prism:cortisol",
                       "SpecimenType": "serum", "Units": "nmol/L", "Status": "official"},
}
TEMPLATE = {
    "Study": {"TaskName": "xq"},
    "XQ01": {"Description": {"en": "Item"}, "Levels": {"0": {"en": "No"}, "1": {"en": "Yes"}}},
}
RECIPE = {"Scores": [{"Name": "xq_total", "Description": "sum"}]}
SURVEY_IDS = ["prism:xq", "prism:xq.xq01", "prism:xq.score-total", "prism:other", "prism:other.o1"]


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    write(tmp_path / "schemas/stable/entities.schema.json",
          {"modalities": {"biosample": {"terms": {"contextField": "Technical.SpecimenType"}}}})
    for stem, term in BIOSAMPLE_TERMS.items():
        write(tmp_path / f"terms/biosample/{stem}.json", term)
    write(tmp_path / "library/survey/survey-xq.json", TEMPLATE)
    write(tmp_path / "recipes/survey/recipe-xq.json", RECIPE)
    (tmp_path / "ids").mkdir()
    (tmp_path / "ids/survey-ids.txt").write_text("".join(f"{i}\n" for i in SURVEY_IDS), encoding="utf-8")
    write(tmp_path / "mappings/vocabularies.json", VOCABS)
    return tmp_path


def run(repo):
    return check_mappings.check(repo)


def put(repo, modality, family, data):
    write(repo / "mappings" / modality / f"{family}.json", data)


def says(problems, text):
    return any(text in p for p in problems)


def test_a_valid_file_passes(repo):
    put(repo, "biosample", "cortisol", {"prism:cortisol": {"SameAs": {"example": URL}},
                                         "prism:cortisol.serum": {"Measures": [
                                             {"URL": URL, "Match": "exact", "Higher": "more", "Source": "me",
                                              "Checked": "2026-11-14", "Status": "reviewed"}]}})
    put(repo, "survey", "xq", {
        "prism:xq.xq01": {
            "Measures": [{"URL": URL}],
            "ValueRules": [{"Name": "xq-present", "Source": "manual",
                            "Rules": [{"When": {"Op": ">=", "Value": 1}, "State": "present"},
                                      {"When": {"Op": "in", "Value": [0, 2]}, "State": "absent"}]}],
            "Levels": {"1": {"Measures": [{"URL": URL, "Match": "narrower"}]}}},
        "prism:xq.score-total": {"Measures": [{"URL": URL}]}})
    assert run(repo) == []


def test_no_mappings_folder_is_fine(repo):
    assert run(repo) == []


def test_unreleased_key(repo):
    put(repo, "survey", "xq", {"prism:xq.xq99": {"SameAs": {"example": URL}}})
    assert says(run(repo), "prism:xq.xq99")
    put(repo, "biosample", "ferritin", {"prism:ferritin": {"SameAs": {"example": URL}}})
    assert says(run(repo), "prism:ferritin")


def test_child_of_an_existing_analyte_is_accepted(repo):
    put(repo, "biosample", "cortisol", {"prism:cortisol.saliva": {"SameAs": {"example": URL}}})
    assert run(repo) == []


def test_family_must_match_the_file_name(repo):
    put(repo, "survey", "other", {"prism:xq.xq01": {"SameAs": {"example": URL}}})
    assert says(run(repo), "family")


def test_unknown_vocabulary_and_bad_url(repo):
    put(repo, "biosample", "cortisol", {"prism:cortisol": {"SameAs": {"nowhere": URL}}})
    assert says(run(repo), "nowhere")
    put(repo, "biosample", "cortisol", {"prism:cortisol": {"SameAs": {"example": "https://example.org/x"}}})
    assert says(run(repo), "example")
    put(repo, "biosample", "cortisol", {"prism:cortisol": {"Measures": [{"URL": "https://elsewhere.org/1"}]}})
    assert says(run(repo), "URL")


def test_vocabulary_patterns_come_from_the_data_file(repo):
    write(repo / "mappings/vocabularies.json",
          {"example": {"pattern": r"^https://example\.org/only$", "label": "x"}})
    put(repo, "biosample", "cortisol", {"prism:cortisol": {"SameAs": {"example": URL}}})
    assert says(run(repo), "example")
    put(repo, "biosample", "cortisol", {"prism:cortisol": {"SameAs": {"example": "https://example.org/only"}}})
    assert run(repo) == []


@pytest.mark.parametrize("entry", [
    {"URL": 5},
    {"URL": URL, "Match": "same"},
    {"URL": URL, "Higher": "up"},
    {"URL": URL, "Status": "ok"},
    {"URL": URL, "Checked": "yesterday"},
    {"URL": URL, "Source": 7},
    {"URL": URL, "Note": "free text"},
    {"Match": "exact"},
    "text",
])
def test_bad_measures_entries_are_messages(repo, entry):
    put(repo, "biosample", "cortisol", {"prism:cortisol": {"Measures": [entry]}})
    assert run(repo)


@pytest.mark.parametrize("value", [
    {"SameAs": []}, {"SameAs": {"example": 5}}, {"Measures": {}}, {"ValueRules": {}}, {"Levels": []},
    {"Extra": 1}, [], "text",
])
def test_wrong_types_are_messages_not_crashes(repo, value):
    put(repo, "biosample", "cortisol", {"prism:cortisol": value})
    assert run(repo)


def test_file_that_is_not_an_object_or_not_json(repo):
    put(repo, "biosample", "cortisol", [1])
    assert run(repo)
    (repo / "mappings/biosample/cortisol.json").write_text("{", encoding="utf-8")
    assert run(repo)


@pytest.mark.parametrize("rule", [
    {"Name": "Bad Name", "Source": "s", "Rules": [{"When": {"Op": "==", "Value": 1}, "State": "x"}]},
    {"Name": "n", "Source": "s", "Rules": [{"When": {"Op": "~", "Value": 1}, "State": "x"}]},
    {"Name": "n", "Source": "s", "Rules": [{"When": {"Op": "==", "Value": 1}, "State": "Not A Slug"}]},
    {"Name": "n", "Source": "s", "Rules": [{"When": {"Op": "in", "Value": 1}, "State": "x"}]},
    {"Name": "n", "Source": "s", "Rules": [{"When": {"Op": "==", "Value": [1]}, "State": "x"}]},
    {"Name": "n", "Source": "s", "Rules": []},
    {"Name": "n", "Source": "s"},
])
def test_bad_value_rules(repo, rule):
    put(repo, "biosample", "cortisol", {"prism:cortisol": {"ValueRules": [rule]}})
    assert run(repo)


def test_levels_must_exist_in_the_definition(repo):
    put(repo, "survey", "xq", {"prism:xq.xq01": {"Levels": {"7": {"Measures": [{"URL": URL}]}}}})
    assert says(run(repo), "'7'")
    put(repo, "survey", "xq", {"prism:xq.xq01": {"Levels": {"1": {"SameAs": {"example": URL}}}}})
    assert run(repo)  # a level carries Measures and ValueRules only


def test_levels_refused_when_the_definition_has_none(repo):
    put(repo, "biosample", "cortisol", {"prism:cortisol": {"Levels": {"1": {"Measures": [{"URL": URL}]}}}})
    assert says(run(repo), "Levels")
    put(repo, "survey", "other", {"prism:other.o1": {"Levels": {"1": {"Measures": [{"URL": URL}]}}}})
    assert says(run(repo), "Levels")


def test_term_levels_are_the_definition(repo):
    write(repo / "terms/environment/noise.json", {"TermID": "prism:noise", "Level": "variable", "Label": "n",
                                                  "Levels": {"low": "l"}, "Status": "official"})
    write(repo / "schemas/stable/entities.schema.json", {"modalities": {
        "biosample": {"terms": {"contextField": "Technical.SpecimenType"}}, "environment": {"terms": {}}}})
    put(repo, "environment", "noise", {"prism:noise": {"Levels": {"low": {"Measures": [{"URL": URL}]}}}})
    assert run(repo) == []
    put(repo, "environment", "noise", {"prism:noise": {"Levels": {"high": {"Measures": [{"URL": URL}]}}}})
    assert says(run(repo), "'high'")


def test_one_id_in_two_files(repo):
    put(repo, "survey", "xq", {"prism:xq.xq01": {"SameAs": {"example": URL}}})
    put(repo, "survey", "xq2", {"prism:xq.xq01": {"SameAs": {"example": URL}}})
    assert says(run(repo), "two files") or says(run(repo), "already")


def test_unknown_modality_folder(repo):
    put(repo, "astrology", "x", {})
    assert says(run(repo), "astrology")


def test_derived_survey_ids_must_be_in_the_released_list(repo):
    (repo / "ids/survey-ids.txt").write_text("prism:xq\n", encoding="utf-8")
    problems = run(repo)
    assert says(problems, "prism:xq.xq01") and says(problems, "prism:xq.score-total")


def test_cli_exit_codes(repo):
    script = ROOT / "scripts" / "check_mappings.py"
    ok = subprocess.run([sys.executable, str(script), "--repo", str(repo)], capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout.startswith("warning: 1 released survey ID")
    put(repo, "biosample", "cortisol", {"prism:ferritin": {}})
    bad = subprocess.run([sys.executable, str(script), "--repo", str(repo)], capture_output=True, text=True)
    assert bad.returncode == 1 and "prism:ferritin" in bad.stdout


# --- the real repository ---------------------------------------------------------

def test_the_shipped_mappings_pass():
    assert check_mappings.check(ROOT) == []


def test_vocabularies_are_data_with_a_pattern_and_a_label():
    vocabs = json.loads((ROOT / "mappings/vocabularies.json").read_text(encoding="utf-8"))
    assert {"snomed", "loinc", "chebi", "ncit"} <= set(vocabs)  # the first four; tests/test_vocabularies.py has the rest
    assert all(set(v) == {"pattern", "label"} for v in vocabs.values())


def test_the_eight_snomed_links_moved_unchanged():
    expected = {"estradiol": "126172005", "progesterone": None, "testosterone": None, "free-testosterone": None,
                "lh": None, "fsh": None, "prolactin": None, "shbg": None}
    assert set(expected) <= {p.stem for p in (ROOT / "mappings/biosample").glob("*.json")}
    for analyte in expected:
        data = json.loads((ROOT / f"mappings/biosample/{analyte}.json").read_text(encoding="utf-8"))
        assert list(data) == [f"prism:{analyte}"]
        assert list(data[f"prism:{analyte}"]) == ["SameAs"]
        term = json.loads((ROOT / f"terms/biosample/{analyte}.json").read_text(encoding="utf-8"))
        assert "TermURL" not in term
    est = json.loads((ROOT / "mappings/biosample/estradiol.json").read_text(encoding="utf-8"))
    assert est["prism:estradiol"]["SameAs"] == {"snomed": "https://snomed.info/id/126172005"}


def test_termurl_in_a_term_is_refused():
    term = {"TermID": "prism:cortisol", "Level": "analyte", "Label": "cortisol", "Status": "official",
            "TermURL": {"snomed": "https://snomed.info/id/63638003"}}
    problems = check_terms.check_registry({"cortisol": term}, [])
    assert any("mappings/" in p for p in problems)


# --- survey_ids is the same derivation as Studio's --------------------------------

STUDIO = Path("/Volumes/Evo/work/github/prism-studio")


def test_survey_ids_agree_with_studio_on_the_shipped_templates():
    if not (STUDIO / "src" / "survey_terms.py").is_file():
        pytest.skip("Studio checkout not available")
    code = (
        "import sys, json; sys.path.insert(0, sys.argv[1]);"
        "from src.survey_terms import build_survey_registry as b;"
        "from pathlib import Path; r = Path(sys.argv[2]);"
        "print(json.dumps(b(r/'library'/'survey', r/'recipes'/'survey'), sort_keys=True))"
    )
    done = subprocess.run([sys.executable, "-c", code, str(STUDIO), str(ROOT)], capture_output=True, text=True)
    if done.returncode:
        pytest.skip("Studio code cannot be imported here: " + done.stderr[-200:])
    theirs = json.loads(done.stdout)
    ours = survey_ids.build_survey_registry(ROOT / "library" / "survey", ROOT / "recipes" / "survey")
    assert json.loads(json.dumps(ours, sort_keys=True)) == theirs
    assert {"prism:dass", "prism:dass21"} <= {t["TermID"] for t in ours[0].values()}


def test_survey_ids_helpers():
    assert survey_ids.item_local_id("tipi", "TIPI02") == "tipi.tipi02"
    assert survey_ids.score_local_id("tipi", "tipi_extraversion") == "tipi.score-extraversion"


def test_released_instruments_without_a_library_file_are_warned_about(repo):
    warnings = check_mappings.missing_targets(repo)
    assert len(warnings) == 1 and "prism:other" in warnings[0] and "xq" not in warnings[0]


def test_a_mapping_for_an_id_without_a_library_file_is_an_error(repo):
    put(repo, "survey", "other", {"prism:other.o1": {"SameAs": {"example": URL}}})
    assert says(run(repo), "no library file")


def test_the_warning_does_not_fail_the_run(repo, capsys):
    assert check_mappings.main(["--repo", str(repo)]) == 0
    assert "warning: 1 released survey ID" in capsys.readouterr().out


def test_loinc_in_a_term_is_refused_and_belongs_in_mappings():
    term = {"TermID": "prism:cortisol", "Level": "analyte", "Label": "cortisol", "Status": "official", "LOINC": "2143-6"}
    problems = check_terms.check_registry({"cortisol": term}, [])
    assert any("LOINC" in p and "mappings/" in p for p in problems)


def test_the_two_loinc_codes_of_the_registry_moved_into_mappings_unchanged():
    expected = {"crp": ("prism:crp.serum", "30522-7"), "il6": ("prism:il6.serum", "26881-3")}
    for family, (tid, code) in expected.items():
        term = json.loads((ROOT / f"terms/biosample/{tid.partition(':')[2]}.json").read_text(encoding="utf-8"))
        assert "LOINC" not in term
        mapping = json.loads((ROOT / f"mappings/biosample/{family}.json").read_text(encoding="utf-8"))
        assert mapping[tid]["SameAs"] == {"loinc": f"https://loinc.org/{code}"}


# --- deprecated survey IDs: ids/survey-deprecated.json (read by Studio's src/survey_terms.deprecated_ids) ----

def deprecate(repo, data):
    write(repo / "ids/survey-deprecated.json", data)


def test_a_valid_deprecation_passes_also_for_an_id_that_left_the_template(repo):
    deprecate(repo, {"prism:other.o1": {"ReplacedBy": "prism:xq.xq01"}})
    assert run(repo) == []


@pytest.mark.parametrize("data, text", [
    (["x"], "must hold a JSON object"),
    ({"prism:xq.nope": {"ReplacedBy": "prism:xq.xq01"}}, "prism:xq.nope is not a released survey ID"),
    ({"prism:xq.xq01": {}}, "prism:xq.xq01 must be {\"ReplacedBy\""),
    ({"prism:xq.xq01": "prism:xq"}, "prism:xq.xq01 must be {\"ReplacedBy\""),
    ({"prism:xq.xq01": {"ReplacedBy": "prism:xq", "Why": "x"}}, "prism:xq.xq01 must be {\"ReplacedBy\""),
    ({"prism:xq.xq01": {"ReplacedBy": "prism:xq.nope"}}, "prism:xq.nope, which is not a released survey ID"),
    ({"prism:xq.xq01": {"ReplacedBy": "prism:xq.xq01"}}, "which is deprecated itself"),
    ({"prism:xq.xq01": {"ReplacedBy": "prism:other"}, "prism:other": {"ReplacedBy": "prism:xq"}},
     "which is deprecated itself"),
])
def test_a_bad_deprecation_is_a_problem(repo, data, text):
    deprecate(repo, data)
    assert says(run(repo), text)


def test_deprecations_are_checked_without_a_mappings_folder(repo):
    (repo / "mappings/vocabularies.json").unlink()
    (repo / "mappings").rmdir()
    deprecate(repo, {"prism:xq.xq01": {}})
    assert says(run(repo), "survey-deprecated.json")


def test_a_link_on_a_deprecated_id_is_a_warning_not_a_problem(repo, capsys):
    put(repo, "survey", "xq", {"prism:xq.xq01": {"Measures": [{"URL": URL}]}})
    deprecate(repo, {"prism:xq.xq01": {"ReplacedBy": "prism:xq"}})
    assert check_mappings.main(["--repo", str(repo)]) == 0
    assert ("warning: mappings/survey/xq.json: prism:xq.xq01 is deprecated, link its replacement prism:xq"
            in capsys.readouterr().out)
