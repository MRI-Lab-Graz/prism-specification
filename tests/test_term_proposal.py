"""scripts/term_proposal.py: the proposal format sent by `prism_tools.py terms propose` or the issue form."""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tp = _load("term_proposal")
ct = _load("check_terms")
SCHEMA = REPO / "schemas" / "stable" / "biosample.schema.json"
SPECIMENS = ct.specimen_types(SCHEMA)
REGISTRY, _ = ct.load_terms(REPO / "terms" / "biosample")

PARENT = {"TermID": "prism:ferritin", "Level": "analyte", "Label": "ferritin", "Aliases": ["ferr"], "Description": "Iron store marker"}
CHILD = {"TermID": "prism:ferritin.serum", "Level": "analyte-specimen", "Parent": "prism:ferritin",
         "SpecimenType": "serum", "Units": "ug/L", "MinValue": 0}
AGREE = "### Agreements\n\n- [x] I agree to the licence\n- [x] No personal data\n"


def _body(proposal, fenced=True, agree=AGREE):
    text = proposal if isinstance(proposal, str) else json.dumps(proposal)
    value = f"```json\n{text}\n```" if fenced else text
    return f"### Proposal\n\n{value}\n\n{agree}"


def _proposal(*terms, modality="biosample"):
    return {"modality": modality, "terms": list(terms)}


def _check(proposal):
    return tp.check_proposal(proposal, REGISTRY, SPECIMENS)


def test_extract_reads_fenced_and_bare_json():
    p = _proposal(PARENT, CHILD)
    assert tp.extract_proposal(_body(p)) == p
    assert tp.extract_proposal(_body(p, fenced=False)) == p


def test_extract_requires_both_checkboxes():
    p = _proposal(PARENT, CHILD)
    for agree in ("### Agreements\n\n- [x] a\n- [ ] b\n", "### Agreements\n\n- [ ] a\n- [ ] b\n", "", "### Agreements\n\n- [x] only one\n"):
        with pytest.raises(tp.ProposalError):
            tp.extract_proposal(_body(p, agree=agree))


def test_extract_rejects_missing_oversize_and_two_blocks():
    p = _proposal(PARENT, CHILD)
    two = _body(json.dumps(p) + "\n```\n\n```json\n{}", fenced=True)  # two fenced blocks inside the Proposal field
    for body in ("", "### Agreements\n\n- [x] a\n- [x] b\n", _body("x" * (tp.MAX_BYTES + 1), fenced=False), two, _body("{not json", fenced=False)):
        with pytest.raises(tp.ProposalError):
            tp.extract_proposal(body)


def test_valid_parent_and_child_pass_and_get_status_official():
    terms, problems = _check(_proposal(PARENT, CHILD))
    assert problems == [] and [t["Status"] for t in terms] == ["official", "official"]
    assert "Status" not in PARENT  # the input is not modified


def test_child_only_with_official_parent_passes():
    child = {**CHILD, "TermID": "prism:cortisol.hair", "Parent": "prism:cortisol", "SpecimenType": "hair"}
    terms, problems = _check(_proposal(child))
    assert problems == [] and len(terms) == 1


def test_child_only_without_parent_fails():
    _, problems = _check(_proposal(CHILD))
    assert any("Parent" in p for p in problems)


def test_already_official_id_fails_naming_the_term():
    child = {**CHILD, "TermID": "prism:cortisol.saliva", "Parent": "prism:cortisol", "SpecimenType": "saliva"}
    _, problems = _check(_proposal(child))
    assert any("prism:cortisol.saliva" in p and "official" in p for p in problems)


def test_alias_or_label_owned_by_an_official_term_fails():
    for field, value in (("Aliases", ["cort"]), ("Label", "Cortisol")):
        _, problems = _check(_proposal({**PARENT, field: value}, CHILD))
        assert problems, field


def test_status_replacedby_and_unknown_fields_fail():
    for extra in ({"Status": "official"}, {"ReplacedBy": "prism:x"}, {"Evil": 1}):
        _, problems = _check(_proposal({**PARENT, **extra}, CHILD))
        assert any(next(iter(extra)) in p for p in problems), extra


def test_bids_prefix_and_traversal_ids_fail():
    for tid in ("bids:ferritin", "prism:../x", "prism:A", "prism:a/b", "ferritin", "prism:"):
        _, problems = _check(_proposal({**PARENT, "TermID": tid}, CHILD))
        assert problems, tid


def test_more_than_two_terms_fails():
    extra = {**CHILD, "TermID": "prism:ferritin.plasma", "SpecimenType": "plasma"}
    _, problems = _check(_proposal(PARENT, CHILD, extra))
    assert any("at most" in p for p in problems)


def test_proposal_that_is_not_an_object_or_has_no_terms_fails():
    for bad in ([], "x", {"modality": "biosample"}, {"modality": "biosample", "terms": []}, {"modality": "biosample", "terms": ["x"]},
                {"modality": "survey", "terms": [PARENT]}):
        _, problems = _check(bad)
        assert problems, bad
