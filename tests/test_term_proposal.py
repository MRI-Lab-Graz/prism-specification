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


# --- task A2: write_terms, pr_body, command line ----------------------------

import shutil


def test_write_terms_creates_one_file_per_term_and_passes_the_registry_check(tmp_path):
    shutil.copytree(REPO / "terms", tmp_path / "terms")
    terms, problems = _check(_proposal(PARENT, CHILD))
    assert problems == []
    written = tp.write_terms(terms, tmp_path / "terms", "biosample")
    assert sorted(p.name for p in written) == ["ferritin.json", "ferritin.serum.json"]
    registry, load_problems = ct.load_terms(tmp_path / "terms" / "biosample")
    assert load_problems == [] and ct.check_registry(registry, SPECIMENS) == []
    assert json.loads(written[0].read_text(encoding="utf-8"))["Status"] == "official"


def test_write_terms_refuses_a_bad_local_part(tmp_path):
    for tid in ("prism:../x", "prism:A", "prism:a/b"):
        with pytest.raises(tp.ProposalError):
            tp.write_terms([{**PARENT, "TermID": tid}], tmp_path, "biosample")
    assert not list(tmp_path.rglob("*.json"))


def _run(tmp_path, monkeypatch, body=None, file=None, proposal=None):
    out = tmp_path / "bundle"
    argv = ["check", "--terms", str(REPO / "terms" / "biosample"), "--schema", str(SCHEMA), "--out", str(out)]
    if file is not None:
        argv += ["--file", str(file)]
    if body is not None:
        monkeypatch.setenv("ISSUE_BODY", body)
    return tp.main(argv), out


def test_check_cli_with_issue_body_env_writes_an_ok_bundle(tmp_path, monkeypatch):
    code, out = _run(tmp_path, monkeypatch, body=_body(_proposal(PARENT, CHILD)))
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "ok"
    assert (out / "terms" / "biosample" / "ferritin.json").is_file()
    assert (out / "log").read_text(encoding="utf-8") == ""


def test_check_cli_failure_writes_status_failed_and_the_reasons(tmp_path, monkeypatch):
    code, out = _run(tmp_path, monkeypatch, body=_body(_proposal({**PARENT, "Status": "official"}, CHILD)))
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed"
    assert "Status" in (out / "log").read_text(encoding="utf-8")
    assert not (out / "terms").exists()


def test_check_cli_bad_body_is_a_failed_bundle_not_a_crash(tmp_path, monkeypatch):
    code, out = _run(tmp_path, monkeypatch, body="no sections at all")
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed"


def test_check_cli_file_mode_equals_issue_mode(tmp_path, monkeypatch):
    f = tmp_path / "proposal.json"
    f.write_text(json.dumps(_proposal(PARENT, CHILD)), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "ok"
    assert json.loads((out / "terms/biosample/ferritin.serum.json").read_text(encoding="utf-8"))["Units"] == "ug/L"


def test_check_cli_file_mode_rejects_oversize_and_non_json(tmp_path, monkeypatch):
    f = tmp_path / "p.json"
    for text in ("{nope", "x" * (tp.MAX_BYTES + 1)):
        f.write_text(text, encoding="utf-8")
        _, out = _run(tmp_path, monkeypatch, file=f)
        assert (out / "status").read_text(encoding="utf-8").strip() == "failed"
        shutil.rmtree(out)


def test_pr_body_is_a_draft_with_the_checklist_and_no_dead_warnings_section():
    body = tp.pr_body(7)
    assert "draft" in body.lower() and "#7" in body and "frozen" in body and "UCUM" in body
    assert "Warnings" not in body  # the check only writes errors, which fail the bundle


def test_pr_body_cli_reads_the_environment(monkeypatch, capsys):
    monkeypatch.setenv("ISSUE_NUMBER", "12")
    assert tp.main(["pr-body"]) == 0 and "#12" in capsys.readouterr().out


# --- review fixes: value types, trailing newline, always a bundle, CRLF -------

@pytest.mark.parametrize(
    "where,field,value",
    [
        ("parent", "Aliases", 5), ("parent", "Aliases", [1]), ("parent", "Equivalents", 1), ("parent", "Label", ["a"]),
        ("parent", "Description", {"x": 1}), ("parent", "Level", 3),
        ("child", "AlternativeUnits", {"a": 1}), ("child", "Units", 5), ("child", "Units", {"x": 1}),
        ("child", "MinValue", "zero"), ("child", "MinValue", True), ("child", "WarnMaxValue", [1]),
        ("child", "LOINC", 5), ("child", "SpecimenType", ["serum"]), ("child", "Parent", 7),
    ],
)
def test_value_types_are_checked_without_crashing(where, field, value):
    parent, child = dict(PARENT), dict(CHILD)
    (parent if where == "parent" else child)[field] = value
    terms, problems = _check(_proposal(parent, child))
    assert terms == [] and any(field in p for p in problems)


def test_trailing_newline_in_an_id_is_rejected_and_never_becomes_a_file(tmp_path):
    _, problems = _check(_proposal({**PARENT, "TermID": "prism:zonulin\n"}, CHILD))
    assert problems
    with pytest.raises(tp.ProposalError):
        tp.write_terms([{**PARENT, "TermID": "prism:a\n"}], tmp_path, "biosample")
    assert not list(tmp_path.rglob("*"))


def test_internal_error_still_writes_a_failed_bundle(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(tp, "check_proposal", boom)
    code, out = _run(tmp_path, monkeypatch, body=_body(_proposal(PARENT, CHILD)))
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed"
    assert "internal error" in (out / "log").read_text(encoding="utf-8")


def test_extract_handles_crlf_bodies_and_backticks_inside_strings():
    p = _proposal({**PARENT, "Description": "uses ``` fences inside text"}, CHILD)
    assert tp.extract_proposal(_body(p)) == p
    assert tp.extract_proposal(_body(p).replace("\n", "\r\n")) == p
    assert tp.extract_proposal(_body(p, fenced=False).replace("\n", "\r\n")) == p


def test_a_flood_of_problems_is_capped_so_the_comment_fits_on_github(tmp_path, monkeypatch):
    junk = {f"X{i}": 1 for i in range(300)}
    code, out = _run(tmp_path, monkeypatch, body=_body(_proposal({**PARENT, **junk}, CHILD)))
    log = (out / "log").read_text(encoding="utf-8")
    assert code == 0 and len(log.splitlines()) <= 51 and "and 250 more" in log


# --- proposal format v2: files by repository path (many terms) -----------------------------------

V2 = "prism-proposal/2"


def _v2(**files):
    return {"format": V2, "files": {f"terms/biosample/{stem.replace('_', '.')}.json": term for stem, term in files.items()}}


def _child(local, specimen, **over):
    return {**CHILD, "TermID": f"prism:{local}.{specimen}", "SpecimenType": specimen, "Parent": f"prism:{local}", **over}


def test_v2_many_terms_with_the_parent_only_in_the_proposal():
    doc = _v2(ferritin=PARENT, ferritin_serum=CHILD, ferritin_plasma=_child("ferritin", "plasma"),
              ferritin_saliva=_child("ferritin", "saliva"))
    terms, problems = _check(doc)
    assert problems == [] and len(terms) == 4 and all(t["Status"] == "official" for t in terms)


def test_v1_is_converted_to_the_same_files():
    pairs, problems = tp.normalize(_proposal(PARENT, CHILD))
    assert problems == [] and [path for path, _ in pairs] == ["terms/biosample/ferritin.json", "terms/biosample/ferritin.serum.json"]
    assert tp.normalize(_v2(ferritin=PARENT, ferritin_serum=CHILD))[0] == pairs


@pytest.mark.parametrize(
    "doc",
    [
        {"format": V2},
        {"format": V2, "files": {}},
        {"format": V2, "files": []},
        {"format": V2, "files": "x"},
        {"format": "prism-proposal/3", "files": {"terms/biosample/ferritin.json": PARENT}},
        {"files": {"terms/biosample/ferritin.json": PARENT}},  # files without the format marker
        {"format": V2, "files": {"terms/biosample/ferritin.json": PARENT}, "extra": 1},
        {"format": V2, "files": {"terms/biosample/ferritin.json": "not an object"}},
        {"format": V2, "files": {"terms/biosample/ferritin.json": [PARENT]}},
    ],
    ids=["no files", "empty files", "list files", "string files", "other format", "no format", "extra key", "string value", "list value"],
)
def test_v2_shape_problems(doc):
    terms, problems = _check(doc)
    assert terms == [] and problems


@pytest.mark.parametrize(
    "path",
    [
        "terms/biosample/../../schemas/stable/biosample.schema.json",
        "terms/biosample/ferritin.json/../x.json",
        "/etc/passwd",
        "terms/biosample/Ferritin.json",
        "terms/biosample/ferritin.json\n",
        "terms/biosample/ferritin.JSON",
        "terms/biosample/ferritin.txt",
        "terms/biosample/sub/ferritin.json",
        "terms/environment/ferritin.json",
        "terms/biosample/.json",
        "terms//ferritin.json",
        "schemas/stable/ferritin.json",
        ".github/workflows/x.json",
        "scripts/ferritin.json",
        "specs/ferritin.json",
        "terms/biosample/ferritin",
        "",
    ],
)
def test_v2_paths_outside_the_allow_list_are_rejected(path):
    terms, problems = _check({"format": V2, "files": {path: PARENT}})
    assert terms == [] and any("path" in p for p in problems)


def test_v2_the_file_name_must_match_the_term_id():
    terms, problems = _check({"format": V2, "files": {"terms/biosample/other.json": PARENT}})
    assert terms == [] and any("ferritin" in p and "other" in p for p in problems)


def test_v2_limits_on_the_number_of_files():
    ok = {"format": V2, "files": {f"terms/biosample/m{n}-x.json": {**PARENT, "TermID": f"prism:m{n}-x", "Label": f"m{n}x", "Aliases": []}
                                  for n in range(tp.MAX_FILES)}}
    terms, problems = _check(ok)
    assert problems == [] and len(terms) == tp.MAX_FILES
    ok["files"]["terms/biosample/extra-x.json"] = {**PARENT, "TermID": "prism:extra-x", "Label": "extrax", "Aliases": []}
    assert any("at most" in p for p in _check(ok)[1])


def test_v2_a_term_that_is_already_official_is_named():
    cortisol = {"TermID": "prism:cortisol", "Level": "analyte", "Label": "mine", "Aliases": [], "Description": "d"}
    terms, problems = _check({"format": V2, "files": {"terms/biosample/cortisol.json": cortisol}})
    assert terms == [] and any("prism:cortisol" in p and "official" in p for p in problems)
    assert any("cort" in p for p in _check(_v2(ferritin={**PARENT, "Aliases": ["cort"]}, ferritin_serum=CHILD))[1])


def test_v2_forbidden_fields_and_bad_values_are_reported_per_file():
    _, problems = _check(_v2(ferritin={**PARENT, "Status": "official"}, ferritin_serum={**CHILD, "Units": 5}))
    assert any("Status" in p for p in problems) and any("Units" in p for p in problems)


def test_v2_a_child_needs_its_parent_in_the_registry_or_the_proposal():
    assert _check(_v2(ferritin_serum=CHILD))[0] == [] and any("Parent" in p for p in _check(_v2(ferritin_serum=CHILD))[1])
    cortisol_hair = {**CHILD, "TermID": "prism:cortisol.hair", "Parent": "prism:cortisol", "SpecimenType": "hair"}
    assert _check(_v2(cortisol_hair=cortisol_hair))[1] == []


def test_v2_size_limit_applies_to_the_form_and_to_files():
    big = _v2(ferritin={**PARENT, "Description": "x" * (tp.MAX_BYTES + 1)})
    with pytest.raises(tp.ProposalError):
        tp.extract_proposal(_body(json.dumps(big), fenced=False))


def test_v2_check_cli_writes_the_files_at_their_paths(tmp_path, monkeypatch):
    doc = _v2(ferritin=PARENT, ferritin_serum=CHILD, ferritin_plasma=_child("ferritin", "plasma"))
    f = tmp_path / "proposal.json"
    f.write_text(json.dumps(doc), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "ok"
    written = sorted(p.relative_to(out).as_posix() for p in (out / "terms").rglob("*.json"))
    assert written == ["terms/biosample/ferritin.json", "terms/biosample/ferritin.plasma.json", "terms/biosample/ferritin.serum.json"]


def test_v2_check_cli_failure_writes_no_files(tmp_path, monkeypatch):
    f = tmp_path / "proposal.json"
    f.write_text(json.dumps({"format": V2, "files": {"schemas/stable/x.json": PARENT}}), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed" and not (out / "terms").exists()
    assert "schemas/stable/x.json" in (out / "log").read_text(encoding="utf-8")


def test_v1_keeps_its_two_term_cap():
    extra = {**CHILD, "TermID": "prism:ferritin.plasma", "SpecimenType": "plasma"}
    assert any("at most 2" in p for p in _check(_proposal(PARENT, CHILD, extra))[1])


# --- task A2: the paste path, the form and the docs describe format v2 ----------------------------

def _forty():
    return {"format": V2, "files": {f"terms/biosample/m{n}-x.json": {**PARENT, "TermID": f"prism:m{n}-x", "Label": f"m{n}x", "Aliases": [], "Description": "d" * 400}
                                    for n in range(tp.MAX_FILES)}}


def test_a_forty_term_proposal_pasted_into_the_form_passes_with_crlf_and_fences():
    doc = _forty()
    text = json.dumps(doc, indent=2)
    assert 20_000 < len(text.encode("utf-8")) < tp.MAX_BYTES  # too big for the old limit and for a link, fine for the form
    body = _body(text).replace("\n", "\r\n")
    assert tp.extract_proposal(body) == doc
    terms, problems = _check(tp.extract_proposal(body))
    assert problems == [] and len(terms) == tp.MAX_FILES


def test_the_form_and_contributing_describe_format_v2():
    form = (REPO / ".github" / "ISSUE_TEMPLATE" / "propose-metric.yml").read_text(encoding="utf-8")
    docs = (REPO / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "one or two terms" not in form and "one or two terms" not in docs
    assert V2 in docs and "terms/<modality>/<id>.json" in docs
    assert str(tp.MAX_FILES) in docs and "50,000" in docs
