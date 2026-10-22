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
