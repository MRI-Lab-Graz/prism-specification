"""A proposal may carry links to other vocabularies: `mappings/<modality>/<family>.json` next to its term files.

The bot merges the new IDs into the family's existing mapping file and never changes an ID that is already mapped.
"""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAPPINGS = REPO / "mappings"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tp = _load("term_proposal")
ct = _load("check_terms")
SPECIMENS = ct.specimen_types(REPO / "schemas" / "stable" / "biosample.schema.json")
REGISTRY, _ = ct.load_terms(REPO / "terms" / "biosample")

PARENT = {"TermID": "prism:ferritin", "Level": "analyte", "Label": "ferritin", "Aliases": ["ferr"], "Description": "Iron store marker"}
CHILD = {"TermID": "prism:ferritin.serum", "Level": "analyte-specimen", "Parent": "prism:ferritin",
         "SpecimenType": "serum", "Units": "ug/L", "MinValue": 0}
LINK = {"SameAs": {"loinc": "https://loinc.org/2276-4"}}  # fixture, not a claim about ferritin


def _proposal(files=None, **extra):
    base = {"terms/biosample/ferritin.json": PARENT, "terms/biosample/ferritin.serum.json": CHILD}
    return {"format": tp.FORMAT_V2, "files": {**base, **(files or {})}, **extra}


def _check(proposal):
    return tp.check_proposal(proposal, REGISTRY, SPECIMENS, mappings_dir=MAPPINGS)


def test_a_new_term_can_bring_its_link():
    terms, problems = _check(_proposal({"mappings/biosample/ferritin.json": {"prism:ferritin.serum": LINK}}))
    assert problems == [] and len(terms) == 2


def test_a_link_for_an_existing_term_is_a_proposal_too():
    files = {"mappings/biosample/cortisol.json": {"prism:cortisol.serum": {"SameAs": {"snomed": "https://snomed.info/id/63638003"}}}}
    terms, problems = _check({"format": tp.FORMAT_V2, "files": files})
    assert problems == [] and terms == []


def test_an_id_that_is_already_mapped_cannot_be_changed_by_a_proposal():
    files = {"mappings/biosample/estradiol.json": {"prism:estradiol": {"SameAs": {"snomed": "https://snomed.info/id/126172006"}}}}
    _, problems = _check({"format": tp.FORMAT_V2, "files": files})
    assert any("already mapped" in p and "prism:estradiol" in p for p in problems)


def test_the_link_is_checked_like_any_mapping():
    for entry, words in (({"SameAs": {"nosuch": "https://example.org/1"}}, "unknown vocabulary"),
                         ({"SameAs": {"loinc": "https://example.org/1"}}, "must match"),
                         ({"Measures": [{"URL": "https://loinc.org/2276-4", "Match": "same"}]}, "Match")):
        _, problems = _check(_proposal({"mappings/biosample/ferritin.json": {"prism:ferritin.serum": entry}}))
        assert any(words in p for p in problems), (entry, problems)


def test_a_link_needs_a_term_that_exists_or_is_proposed():
    _, problems = _check({"format": tp.FORMAT_V2, "files": {"mappings/biosample/zonulin.json": {"prism:zonulin": LINK}}})
    assert any("not a term" in p for p in problems)


def test_the_key_must_belong_to_the_file_family():
    _, problems = _check(_proposal({"mappings/biosample/ferritin.json": {"prism:cortisol.saliva": LINK}}))
    assert any("family" in p for p in problems)


def test_a_mapping_file_must_be_an_object_of_entries():
    for bad in ([], {"prism:ferritin": []}, {"ferritin": LINK}):
        _, problems = _check(_proposal({"mappings/biosample/ferritin.json": bad}))
        assert problems, bad


def test_only_declared_term_modalities_and_known_paths_are_allowed():
    for path in ("mappings/survey/dass.json", "mappings/biosample/Ferritin.json", "mappings/biosample/x/y.json", "mappings/vocabularies.json"):
        _, problems = _check(_proposal({path: {"prism:ferritin": LINK}}))
        assert any("not allowed" in p for p in problems), path


def test_one_kind_of_data_per_proposal_includes_its_links():
    files = {"mappings/environment/air-temperature.json": {"prism:air-temperature": LINK}}
    _, problems = _check(_proposal(files))
    assert any("one kind of data" in p for p in problems)


def test_without_a_mappings_folder_a_link_cannot_be_checked():
    _, problems = tp.check_proposal(_proposal({"mappings/biosample/ferritin.json": {"prism:ferritin.serum": LINK}}), REGISTRY, SPECIMENS)
    assert any("mappings folder" in p for p in problems)


def test_the_bot_writes_the_family_file_merged_with_what_is_there(tmp_path):
    proposal = {"format": tp.FORMAT_V2, "files": {"mappings/biosample/estradiol.json": {"prism:estradiol.serum": LINK}}}
    src = tmp_path / "proposal.json"
    src.write_text(json.dumps(proposal), encoding="utf-8")
    out = tmp_path / "out"
    assert tp.main(["check", "--repo", str(REPO), "--file", str(src), "--out", str(out)]) == 0
    assert (out / "status").read_text(encoding="utf-8") == "ok\n"
    written = json.loads((out / "files/mappings/biosample/estradiol.json").read_text(encoding="utf-8"))
    assert list(written) == ["prism:estradiol", "prism:estradiol.serum"]  # what was there first, then the new ID
    assert written["prism:estradiol"] == json.loads((MAPPINGS / "biosample/estradiol.json").read_text(encoding="utf-8"))["prism:estradiol"]
    assert written["prism:estradiol.serum"] == LINK


def test_a_new_family_file_is_written_as_proposed(tmp_path):
    proposal = _proposal({"mappings/biosample/ferritin.json": {"prism:ferritin.serum": LINK}})
    src = tmp_path / "proposal.json"
    src.write_text(json.dumps(proposal), encoding="utf-8")
    out = tmp_path / "out"
    assert tp.main(["check", "--repo", str(REPO), "--file", str(src), "--out", str(out)]) == 0
    assert json.loads((out / "files/mappings/biosample/ferritin.json").read_text(encoding="utf-8")) == {"prism:ferritin.serum": LINK}
    assert (out / "files/terms/biosample/ferritin.serum.json").is_file()
