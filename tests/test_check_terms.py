"""scripts/check_terms.py: the term registry rules (also run in the prism-specification repository)."""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_terms.py"
SCHEMA = REPO / "schemas" / "stable" / "biosample.schema.json"
TERMS = REPO / "terms" / "biosample"


def _load():
    spec = importlib.util.spec_from_file_location("check_terms", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load()
load_terms = _mod.load_terms
SPECIMENS = json.loads(SCHEMA.read_text(encoding="utf-8"))["properties"]["Technical"]["properties"]["SpecimenType"]["enum"]


def check_registry(registry):
    return _mod.check_registry(registry, SPECIMENS)


SEED_IDS = {
    "cortisol", "cortisol.saliva", "cortisol.serum",
    "alpha-amylase", "alpha-amylase.saliva",
    "crp", "crp.serum", "il6", "il6.serum", "tnfa", "tnfa.serum",
}


def _parent(local="cortisol", **over):
    t = {"TermID": f"prism:{local}", "Level": "analyte", "Label": local, "Aliases": [],
         "Description": "d", "Status": "official"}
    t.update(over)
    return t


def _child(parent="cortisol", specimen="saliva", **over):
    t = {"TermID": f"prism:{parent}.{specimen}", "Level": "analyte-specimen",
         "Parent": f"prism:{parent}", "SpecimenType": specimen, "Units": "nmol/L",
         "MinValue": 0, "Status": "official"}
    t.update(over)
    return t


def _ok():
    return {"cortisol": _parent(), "cortisol.saliva": _child()}


def _text(problems):
    return " | ".join(problems)


def test_shipped_registry_is_valid():
    registry, problems = load_terms(TERMS)
    assert problems == [] and SEED_IDS <= set(registry)
    assert check_registry(registry) == []


def test_check_registry_accepts_a_clean_registry():
    assert check_registry(_ok()) == []


def test_check_registry_flags_orphan_child():
    reg = {"cortisol.saliva": _child()}
    assert "parent" in _text(check_registry(reg)).lower()


def test_check_registry_flags_alias_collision():
    reg = {"cortisol": _parent(Aliases=["Cort"]), "hormone": _parent("hormone", Aliases=["cort"])}
    assert "cort" in _text(check_registry(reg)).lower()


def test_check_registry_flags_alias_equal_to_other_term_id():
    reg = {"cortisol": _parent(Aliases=["crp"]), "crp": _parent("crp")}
    assert "crp" in _text(check_registry(reg))


def test_check_registry_flags_bad_specimen():
    reg = {"cortisol": _parent(), "cortisol.nails": _child(specimen="nails")}
    assert "nails" in _text(check_registry(reg))


def test_check_registry_flags_deprecated_without_replacedby():
    reg = _ok()
    reg["cortisol"]["Status"] = "deprecated"
    assert "ReplacedBy" in _text(check_registry(reg))


def test_check_registry_flags_dangling_replacedby():
    reg = _ok()
    reg["cortisol"].update(Status="deprecated", ReplacedBy="prism:gone")
    assert "prism:gone" in _text(check_registry(reg))


def test_check_registry_flags_id_not_matching_filename():
    reg = {"cort": _parent("cortisol")}
    assert "cort" in _text(check_registry(reg))


def test_check_registry_flags_bad_id_format():
    assert check_registry({"Cortisol": _parent("Cortisol")})  # uppercase local part
    assert check_registry({"cortisol": _parent(TermID="foo:cortisol")})  # unknown prefix
    reg = _ok()
    reg["cortisol.saliva"]["TermID"] = "prism:cortisol.serum"  # child id != parent.specimen
    assert check_registry(reg)


def test_check_registry_flags_equivalent_collision():
    reg = _ok()
    reg["cortisol"]["Equivalents"] = ["loinc:2143-6"]
    reg["cortisol.saliva"]["Equivalents"] = ["loinc:2143-6"]
    assert "loinc:2143-6" in _text(check_registry(reg))


def test_check_registry_flags_child_without_units():
    reg = _ok()
    del reg["cortisol.saliva"]["Units"]
    assert "Units" in _text(check_registry(reg))


def test_check_registry_flags_label_collisions():
    a = _parent("il6", Label="Interleukin-6")
    assert check_registry({"il6": a, "il-6": _parent("il-6", Label="interleukin-6")})
    assert check_registry({"il6": a, "other": _parent("other", Aliases=["Interleukin-6"])})



def test_unreadable_term_file_is_a_problem(tmp_path):
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    (tmp_path / "good.json").write_text(json.dumps({"TermID": "prism:good"}), encoding="utf-8")
    registry, problems = load_terms(tmp_path)
    assert list(registry) == ["good"] and any("bad.json" in p for p in problems)


def test_cli_passes_on_shipped_terms(capsys):
    assert _mod.main(["--terms", str(TERMS), "--schema", str(SCHEMA)]) == 0


def test_cli_fails_on_a_broken_registry(tmp_path, capsys):
    (tmp_path / "x.json").write_text(json.dumps({"TermID": "foo:x"}), encoding="utf-8")
    assert _mod.main(["--terms", str(tmp_path), "--schema", str(SCHEMA)]) == 1
    assert "foo:x" in capsys.readouterr().out


def test_specimen_types_reads_the_enum_from_the_schema():
    assert _mod.specimen_types(SCHEMA) == SPECIMENS and "saliva" in SPECIMENS


def test_specimen_types_is_empty_for_a_schema_without_specimens():
    assert _mod.specimen_types(REPO / "schemas/stable/survey.schema.json") == []


def test_a_trailing_newline_is_not_a_valid_slug():
    bad = {"TermID": "prism:x\n", "Level": "analyte", "Label": "x", "Aliases": [], "Description": "d", "Status": "official"}
    assert check_registry({"x\n": bad})


# --- polish batch ---------------------------------------------------------------

def test_registry_files_with_wrong_value_types_are_reported_not_crashed_on():
    for field, value in (("Aliases", "abc"), ("Aliases", 5), ("Equivalents", {"a": 1}), ("Label", ["x"]), ("Description", 3)):
        problems = check_registry({"cortisol": _parent(**{field: value})})
        assert any(field in p for p in problems), field


def test_a_string_in_aliases_does_not_claim_single_letters():
    reg = {"cortisol": _parent(Aliases="abc"), "other": _parent("other", Aliases=["a"])}
    problems = check_registry(reg)
    assert problems and not any("'a'" in p and "claimed" in p for p in problems)


def test_seed_terms_know_their_common_spellings():
    registry, _ = load_terms(TERMS)
    assert "il-6" in registry["il6"]["Aliases"] and "tnf-alpha" in registry["tnfa"]["Aliases"] and "hscrp" in registry["crp"]["Aliases"]


def test_registry_ids_have_the_same_length_cap_as_proposals():
    long = "a" * 64
    reg = {long: _parent(long)}
    assert any("local part" in p or "pattern" in p for p in check_registry(reg))
    assert check_registry({"a" * 63: _parent("a" * 63, Label="short")}) == []


# --- one-level (variable) registries, e.g. environment ---

def _var(local="air-temperature", **over):
    t = {"TermID": f"prism:{local}", "Level": "variable", "Label": local.replace("-", " "),
         "Units": "degC", "CFStandardName": "air_temperature", "Status": "official"}
    t.update(over)
    return {k: v for k, v in t.items() if v is not None}  # None drops the key


def _one_level(term):
    return _mod.check_registry({"air-temperature": term}, None)


def test_variable_term_ok():
    assert _one_level(_var()) == []


def test_variable_needs_units_or_levels_not_both():
    both = _var(Levels={"0": "none"})
    neither = {k: v for k, v in _var().items() if k != "Units"}
    assert "Units or Levels" in _text(_one_level(both))
    assert "Units or Levels" in _text(_one_level(neither))


def test_variable_id_has_no_dot():
    reg = {"air-temperature.indoor": _var("air-temperature.indoor")}
    assert _mod.check_registry(reg, None)


def test_analyte_level_refused_in_one_level_registry():
    assert "Level must be 'variable'" in _text(_one_level(_parent("air-temperature")))


def test_levels_type_checked():
    assert "Levels must be an object of strings" in _text(_one_level(_var(Units=None, Levels=["a"])))


def test_cf_name_pattern():
    assert _one_level(_var(CFStandardName="Air Temperature"))


def test_term_modalities_reads_declarations():
    assert _mod.term_modalities(REPO)["biosample"]["contextField"] == "Technical.SpecimenType"


def test_cli_modality_environment(tmp_path):
    (tmp_path / "schemas" / "stable").mkdir(parents=True)
    (tmp_path / "terms" / "environment").mkdir(parents=True)
    ent = {"modalities": {"environment": {"terms": {"nonTermColumns": ["timestamp"]}}}}
    (tmp_path / "schemas/stable/entities.schema.json").write_text(json.dumps(ent))
    (tmp_path / "schemas/stable/environment.schema.json").write_text("{}")
    (tmp_path / "terms/environment/air-temperature.json").write_text(json.dumps(_var()))
    assert _mod.main(["--modality", "environment", "--repo", str(tmp_path)]) == 0
    (tmp_path / "terms/environment/air-temperature.json").write_text(json.dumps(_var(Units=None)))
    assert _mod.main(["--modality", "environment", "--repo", str(tmp_path)]) == 1


# --- final review: empty Units/Levels, --all, exclusive options, CI and PR template ---

import pytest
import yaml


def test_variable_with_empty_units_or_levels_is_a_problem():
    assert "Units or Levels" in _text(_one_level(_var(Units="")))
    assert "Units or Levels" in _text(_one_level(_var(Units=None, Levels={})))


def _two_modality_repo(tmp_path, entities=None):
    (tmp_path / "schemas" / "stable").mkdir(parents=True)
    ent = entities if entities is not None else {"modalities": {
        "environment": {"terms": {"nonTermColumns": []}},
        "biosample": {"terms": {"nonTermColumns": [], "contextField": "Technical.SpecimenType"}}}}
    (tmp_path / "schemas/stable/entities.schema.json").write_text(json.dumps(ent))
    (tmp_path / "schemas/stable/environment.schema.json").write_text("{}")
    (tmp_path / "schemas/stable/biosample.schema.json").write_text(SCHEMA.read_text(encoding="utf-8"))
    for name in ("environment", "biosample"):
        (tmp_path / "terms" / name).mkdir(parents=True)
    (tmp_path / "terms/environment/air-temperature.json").write_text(json.dumps(_var()))
    return tmp_path


def test_cli_all_checks_every_declared_modality(tmp_path, capsys):
    repo = _two_modality_repo(tmp_path)
    assert _mod.main(["--all", "--repo", str(repo)]) == 0
    (repo / "terms/biosample/bad.json").write_text(json.dumps(_parent("bad", Label="")))
    assert _mod.main(["--all", "--repo", str(repo)]) == 1
    assert "biosample" in capsys.readouterr().out


def test_cli_all_fails_when_no_modality_declares_terms(tmp_path):
    repo = _two_modality_repo(tmp_path, entities={"modalities": {}})
    with pytest.raises(SystemExit) as exc:
        _mod.main(["--all", "--repo", str(repo)])
    assert exc.value.code != 0


@pytest.mark.parametrize("argv", [
    ["--modality", "biosample", "--terms", "terms/biosample"],
    ["--modality", "biosample", "--schema", str(SCHEMA)],
    ["--all", "--modality", "biosample"],
    ["--all", "--terms", "terms/biosample", "--schema", str(SCHEMA)],
])
def test_cli_modes_are_exclusive(argv):
    with pytest.raises(SystemExit) as exc:
        _mod.main(argv)
    assert exc.value.code == 2


def test_ci_checks_every_term_modality_without_a_swallowed_reader():
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    step = next(s for s in ci["jobs"]["checks"]["steps"] if s.get("name") == "Term registry")
    assert step["run"].strip() == "python scripts/check_terms.py --all"


def test_pr_template_names_the_check_for_every_kind_of_data_with_terms():
    text = (REPO / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert "check_terms.py --modality NAME" in text and "--terms terms/biosample" not in text


GROUPS = {
    "Temperature and humidity": "air-temperature apparent-temperature dew-point-temperature relative-humidity heat-status",
    "Wind, pressure and rain": "surface-air-pressure wind-speed precipitation cloud-cover weather-regime",
    "Sun and light": "shortwave-radiation uv-index daylight-duration hours-since-daylight sun-phase",
    "Air quality": "european-aqi pm25 pm10 nitrogen-dioxide ozone",
    "Pollen": "pollen-birch pollen-grass pollen-mugwort pollen-ragweed pollen-total pollen-risk",
    "Place and time": "elevation season time-of-day moon-phase moon-illumination",
}


def test_group_type_and_length():
    for bad in (5, ["Pollen"], "", "x" * 61, "two\nlines"):
        assert any("Group" in p for p in _mod.type_problems({"Group": bad}, "t")), bad
    assert _mod.type_problems({"Group": "Pollen"}, "t") == []
    assert _mod.type_problems({"Group": "x" * 60}, "t") == []


def test_every_environment_term_has_one_of_the_six_groups():
    import json
    folder = Path(__file__).resolve().parent.parent / "terms" / "environment"
    found = {}
    for f in folder.glob("*.json"):
        found.setdefault(json.loads(f.read_text(encoding="utf-8")).get("Group"), []).append(f.stem)
    assert {g: sorted(v) for g, v in found.items()} == {g: sorted(v.split()) for g, v in GROUPS.items()}
    assert sum(len(v) for v in found.values()) == 31
