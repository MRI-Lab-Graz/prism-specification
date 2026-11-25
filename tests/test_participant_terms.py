"""Tables (participants): terms without a modality, `termsFrom`, links on answer values (roadmap step 0c)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_mappings  # noqa: E402
import check_modalities  # noqa: E402
import check_terms  # noqa: E402
import term_proposal  # noqa: E402

SCHEMAS = ROOT / "schemas" / "stable"
NECK = {"TermID": "prism:neck", "Level": "variable", "Label": "neck", "Description": "x", "Status": "official"}


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def repo(tmp_path, terms_from=("biometrics",), table_term=NECK, source_term=None):
    write(tmp_path / "schemas/stable/entities.schema.json", {
        "modalities": {"biometrics": {"terms": {"nonTermColumns": []}}},
        "tables": {"participants": {"description": "x", "terms": {"nonTermColumns": [], "unitsOptional": True, "termsFrom": list(terms_from)}}},
    })
    write(tmp_path / "schemas/stable/biometrics.schema.json", {})
    write(tmp_path / "terms/biometrics/hip.json",
          source_term or {"TermID": "prism:hip", "Level": "variable", "Label": "hip", "Units": "cm", "Status": "official"})
    write(tmp_path / f"terms/participants/neck.json", table_term)
    write(tmp_path / "ids/survey-ids.txt.keep", {})
    (tmp_path / "ids/survey-ids.txt").write_text("", encoding="utf-8")
    return tmp_path


def run_all(path, capsys):
    code = check_terms.main(["--all", "--repo", str(path)])
    return code, capsys.readouterr().out


def test_a_table_term_may_have_neither_units_nor_levels(tmp_path, capsys):
    assert run_all(repo(tmp_path), capsys) == (0, "")


def test_a_table_term_may_not_have_both(tmp_path, capsys):
    code, out = run_all(repo(tmp_path, table_term={**NECK, "Units": "cm", "Levels": {"a": "b"}}), capsys)
    assert code == 1 and "participants/neck" in out


def test_a_modality_term_still_needs_one_of_them(tmp_path, capsys):
    code, out = run_all(repo(tmp_path, source_term={"TermID": "prism:hip", "Level": "variable", "Label": "hip",
                                                    "Status": "official"}), capsys)
    assert code == 1 and "biometrics/hip" in out


def test_terms_from_must_name_a_declared_registry(tmp_path, capsys):
    code, out = run_all(repo(tmp_path, terms_from=["nope"]), capsys)
    assert code == 1 and "termsFrom" in out and "nope" in out


def test_a_name_may_not_mean_two_terms_across_terms_from(tmp_path, capsys):
    code, out = run_all(repo(tmp_path, table_term={**NECK, "Aliases": ["Hip"]}), capsys)
    assert code == 1 and "'hip'" in out.lower()


def test_a_table_entry_is_checked_like_a_modality_entry():
    entities = json.loads((SCHEMAS / "entities.schema.json").read_text(encoding="utf-8"))
    entities["tables"]["participants"]["colour"] = "red"
    entities["tables"]["participants"]["terms"]["termsFrom"] = "biometrics"
    problems = check_modalities.check(entities, SCHEMAS)
    assert any("participants" in p and "colour" in p for p in problems)
    assert any("participants" in p and "array" in p for p in problems)


def test_a_table_terms_folder_needs_its_declaration(tmp_path):
    (tmp_path / "terms" / "participants").mkdir(parents=True)
    entities = {"modalities": {}, "tables": {}}
    assert check_modalities.check(entities, SCHEMAS, tmp_path / "terms") == []  # nothing declared, nothing to compare
    entities["tables"] = {"other": {"description": "x", "terms": {"nonTermColumns": []}}}
    assert any(p.startswith("other") for p in check_modalities.check(entities, SCHEMAS, tmp_path / "terms"))


@pytest.mark.parametrize("url, problem", [
    ("http://neurobagel.org/vocab/Sex", None),
    ("http://example.org/Sex", "must match"),
])
def test_an_answer_value_may_be_linked_with_same_as(url, problem):
    vocabs, _ = check_mappings.load_vocabularies(ROOT / "mappings" / "vocabularies.json")
    found = check_mappings.entry_problems({"Levels": {"M": {"SameAs": {"neurobagel": url}}}}, "x", vocabs, {"M", "F"})
    assert (found == []) if problem is None else any(problem in p for p in found)


def test_the_shipped_participant_terms():
    declared = check_terms.term_modalities(ROOT)
    assert declared["participants"] == {"nonTermColumns": ["participant_id"], "unitsOptional": True,
                                        "termsFrom": ["biometrics"]}
    registry = check_terms.load_terms(ROOT / "terms" / "participants")[0]
    body = check_terms.load_terms(ROOT / "terms" / "biometrics")[0]
    assert len(registry) == 26 and {"height", "weight", "bmi"} <= set(body)
    assert registry["education-level"]["Aliases"] == ["education_level"]
    assert {"sex", "handedness", "gender"} == {k for k, t in registry.items() if "Levels" in t}
    assert not {"participant-id", "height", "bmi", "medication-details"} & set(registry)
    assert check_terms.expand("prism:sex", ROOT).endswith("terms/participants/sex")


def test_a_term_can_be_proposed_for_the_participants_table(tmp_path):
    term = {"TermID": "prism:siblings", "Level": "variable", "Label": "number of siblings", "Description": "Siblings."}
    proposal = {"format": "prism-proposal/2", "files": {"terms/participants/siblings.json": term}}
    (tmp_path / "p.json").write_text(json.dumps(proposal), encoding="utf-8")
    out = tmp_path / "bundle"
    assert term_proposal.main(["check", "--file", str(tmp_path / "p.json"), "--repo", str(ROOT), "--out", str(out)]) == 0
    assert (out / "log").read_text(encoding="utf-8") == ""
    assert (out / "files" / "terms" / "participants" / "siblings.json").is_file()
