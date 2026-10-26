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
    assert (out / "files" / "terms" / "biosample" / "ferritin.json").is_file()
    assert (out / "log").read_text(encoding="utf-8") == ""


def test_check_cli_failure_writes_status_failed_and_the_reasons(tmp_path, monkeypatch):
    code, out = _run(tmp_path, monkeypatch, body=_body(_proposal({**PARENT, "Status": "official"}, CHILD)))
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed"
    assert "Status" in (out / "log").read_text(encoding="utf-8")
    assert not (out / "files").exists()


def test_check_cli_bad_body_is_a_failed_bundle_not_a_crash(tmp_path, monkeypatch):
    code, out = _run(tmp_path, monkeypatch, body="no sections at all")
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed"


def test_check_cli_file_mode_equals_issue_mode(tmp_path, monkeypatch):
    f = tmp_path / "proposal.json"
    f.write_text(json.dumps(_proposal(PARENT, CHILD)), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "ok"
    assert json.loads((out / "files/terms/biosample/ferritin.serum.json").read_text(encoding="utf-8"))["Units"] == "ug/L"


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
    written = sorted(p.relative_to(out / "files").as_posix() for p in (out / "files").rglob("*.json"))
    assert written == ["terms/biosample/ferritin.json", "terms/biosample/ferritin.plasma.json", "terms/biosample/ferritin.serum.json"]


def test_v2_check_cli_failure_writes_no_files(tmp_path, monkeypatch):
    f = tmp_path / "proposal.json"
    f.write_text(json.dumps({"format": V2, "files": {"schemas/stable/x.json": PARENT}}), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed" and not (out / "files").exists()
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


# --- v1.2.1: a length cap on IDs, a bundle that is always written, a log that always fits ---------

def test_ids_have_a_length_cap_per_segment():
    ok = "a" * 63
    assert _check(_v2(**{ok: {**PARENT, "TermID": f"prism:{ok}", "Label": "okaylong"}}))[1] == []
    too_long = "a" * 64
    path_problems = _check({"format": V2, "files": {f"terms/biosample/{too_long}.json": {**PARENT, "TermID": f"prism:{too_long}"}}})[1]
    assert path_problems and any("path" in p for p in path_problems)
    assert _check(_v2(**{"x_" + "b" * 64: {**CHILD, "TermID": "prism:x." + "b" * 64}}))[1]  # a long specimen part too
    v1 = _check(_proposal({**PARENT, "TermID": f"prism:{too_long}"}))[1]
    assert v1 and any("TermID" in p for p in v1)


def test_an_over_long_id_is_a_failed_bundle_not_a_crash(tmp_path, monkeypatch):
    long = "a" * 300
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"format": V2, "files": {f"terms/biosample/{long}.json": {**PARENT, "TermID": f"prism:{long}"}}}), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed" and not (out / "files").exists()


def test_a_failure_while_writing_the_files_is_a_failed_bundle(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("File name too long")

    monkeypatch.setattr(tp, "write_terms", boom)
    f = tmp_path / "p.json"
    f.write_text(json.dumps(_v2(ferritin=PARENT, ferritin_serum=CHILD)), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed"
    assert "internal error" in (out / "log").read_text(encoding="utf-8")


def test_the_log_always_fits_in_a_github_comment(tmp_path, monkeypatch):
    key = "terms/biosample/" + "z" * 45_000 + ".json"
    doc = {"format": V2, "files": {key: {**PARENT, **{f"Bad{n}": 1 for n in range(60)}}}}
    f = tmp_path / "p.json"
    f.write_text(json.dumps(doc), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    log = (out / "log").read_text(encoding="utf-8")
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed"
    assert len(log.encode("utf-8")) < 20_000, len(log)  # a comment is limited to 65,536 characters


def test_contributing_documents_schema_patches():
    docs = (REPO / "CONTRIBUTING.md").read_text(encoding="utf-8")
    for needle in ("patches/<modality>.json", "add_enum_values", "add_optional_properties", "minor version", "archive", "in place"):
        assert needle in docs, needle
    assert "re-serialized" not in docs


def test_the_form_names_the_command_for_many_metrics():
    form = (REPO / ".github" / "ISSUE_TEMPLATE" / "propose-metric.yml").read_text(encoding="utf-8")
    assert "spec propose --project" in form and "--all" in form


# --- schema patches in proposals (layer 2): the bot prepares the schema release --------------------------

SWEAT = {"operations": [{"op": "add_enum_values", "path": "Technical.SpecimenType", "values": ["sweat"]}]}
OLD_VERSION = json.loads(SCHEMA.read_text(encoding="utf-8"))["version"]


def _with_patch(patch=SWEAT, **files):
    doc = _v2(**files)
    doc["files"]["patches/biosample.json"] = patch
    return doc


def _stable_bytes():
    return SCHEMA.read_bytes()


def test_a_patch_only_proposal_prepares_the_schema_release(tmp_path, monkeypatch):
    before = _stable_bytes()
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"format": V2, "files": {"patches/biosample.json": SWEAT}}), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "ok", (out / "log").read_text(encoding="utf-8")
    files = sorted(p.relative_to(out / "files").as_posix() for p in (out / "files").rglob("*") if p.is_file())
    assert files == [f"schemas/archive/biosample/{OLD_VERSION}.schema.json", "schemas/stable/biosample.schema.json", "specs/biosample.md"]
    assert _stable_bytes() == before  # the checkout is only read
    released = json.loads((out / "files" / "schemas" / "stable" / "biosample.schema.json").read_text(encoding="utf-8"))
    assert "sweat" in released["properties"]["Technical"]["properties"]["SpecimenType"]["enum"] and released["version"] != OLD_VERSION


def test_a_child_term_on_the_new_specimen_is_checked_against_the_patched_enum(tmp_path, monkeypatch):
    parent = {**PARENT, "TermID": "prism:sweatmarker", "Label": "sweatmarker", "Aliases": []}
    child = {**CHILD, "TermID": "prism:sweatmarker.sweat", "Parent": "prism:sweatmarker", "SpecimenType": "sweat"}
    f = tmp_path / "p.json"
    f.write_text(json.dumps(_with_patch(sweatmarker=parent, sweatmarker_sweat=child)), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert (out / "status").read_text(encoding="utf-8").strip() == "ok", (out / "log").read_text(encoding="utf-8")
    assert (out / "files" / "terms" / "biosample" / "sweatmarker.sweat.json").is_file()
    # without the patch the same term is refused: sweat is not a specimen type
    g = tmp_path / "q.json"
    g.write_text(json.dumps(_v2(sweatmarker=parent, sweatmarker_sweat=child)), encoding="utf-8")
    (tmp_path / "x").mkdir()
    _, out2 = _run(tmp_path / "x", monkeypatch, file=g)
    assert (out2 / "status").read_text(encoding="utf-8").strip() == "failed" and "sweat" in (out2 / "log").read_text(encoding="utf-8")


def test_check_proposal_needs_the_schema_to_check_a_patch():
    doc = {"format": V2, "files": {"patches/biosample.json": SWEAT}}
    _, problems = tp.check_proposal(doc, REGISTRY, SPECIMENS)
    assert any("schema" in p for p in problems)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert tp.check_proposal(doc, REGISTRY, SPECIMENS, schema)[1] == []


@pytest.mark.parametrize(
    "files",
    [
        {"patches/other.json": SWEAT}, {"patches/biosample/x.json": SWEAT}, {"patches/biosample.json/../x": SWEAT},
        {"patches/Biosample.json": SWEAT}, {"patches/biosample.json\n": SWEAT}, {"patches/biosample.json": "x"},
        {"patches/biosample.json": [SWEAT]}, {"patches/.json": SWEAT},
    ],
)
def test_patch_paths_outside_the_allow_list_are_rejected(files):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    terms, problems = tp.check_proposal({"format": V2, "files": files}, REGISTRY, SPECIMENS, schema)
    assert terms == [] and problems


@pytest.mark.parametrize(
    "patch",
    [
        {"operations": [{"op": "remove_enum_values", "path": "Technical.SpecimenType", "values": ["serum"]}]},
        {"operations": [{"op": "add_enum_values", "path": "Technical.SpecimenType", "values": ["serum"]}]},  # nothing to add
        {"operations": [{"op": "add_enum_values", "path": "Technical.SpecimenType", "values": ["Sweat"]}]},
        {"operations": []}, {"extra": 1, "operations": SWEAT["operations"]},
    ],
)
def test_a_bad_patch_is_a_failed_bundle_with_the_reason(tmp_path, monkeypatch, patch):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"format": V2, "files": {"patches/biosample.json": patch}}), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed" and not (out / "files").exists()
    assert "ERROR:" in (out / "log").read_text(encoding="utf-8")


def test_a_failure_while_preparing_the_release_is_a_failed_bundle(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(tp.release_patch, "release", boom)
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"format": V2, "files": {"patches/biosample.json": SWEAT}}), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert (out / "status").read_text(encoding="utf-8").strip() == "failed" and "internal error" in (out / "log").read_text(encoding="utf-8")
    assert not (out / "files").exists()


def test_the_pull_request_text_of_a_schema_release_asks_for_the_version_review():
    plain = tp.pr_body(5)
    release = tp.pr_body(5, schema_release=True)
    assert "version" not in plain.lower() and "archive" not in plain.lower()
    assert "version" in release.lower() and "archive" in release.lower()
    assert "in place" in release.lower() and "re-serial" not in release.lower()  # the schema file keeps its formatting


def test_pr_body_cli_reads_schema_release_from_the_environment(monkeypatch, capsys):
    monkeypatch.setenv("ISSUE_NUMBER", "3")
    monkeypatch.setenv("SCHEMA_RELEASE", "1")
    assert tp.main(["pr-body"]) == 0 and "archive" in capsys.readouterr().out.lower()


# --- a patch may target any modality's lists -------------------------------------------------------------

LICENSE = {"operations": [{"op": "add_enum_values", "path": "Study.LicenseID", "values": ["cc-by-nc-local"]}]}


def test_a_survey_patch_is_checked_against_the_survey_schema(tmp_path, monkeypatch):
    f = tmp_path / "p.json"  # the bot passes the biosample schema as --schema (propose-metric.yml)
    f.write_text(json.dumps({"format": V2, "files": {"patches/survey.json": LICENSE}}), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert code == 0 and (out / "status").read_text(encoding="utf-8").strip() == "ok", (out / "log").read_text(encoding="utf-8")
    assert (out / "files" / "schemas" / "stable" / "survey.schema.json").is_file()


def test_a_survey_patch_keeps_the_biosample_specimens_for_terms(tmp_path, monkeypatch):
    f = tmp_path / "p.json"
    doc = _v2(ferritin=PARENT, ferritin_serum=CHILD)
    doc["files"]["patches/survey.json"] = LICENSE
    f.write_text(json.dumps(doc), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert (out / "status").read_text(encoding="utf-8").strip() == "ok", (out / "log").read_text(encoding="utf-8")
    assert (out / "files" / "terms" / "biosample" / "ferritin.serum.json").is_file()
    # the term is still checked against biosample's specimen types, not survey's (which has none)
    bad = _v2(ferritin=PARENT, ferritin_serum={**CHILD, "SpecimenType": "nonsense"})
    bad["files"]["patches/survey.json"] = LICENSE
    f.write_text(json.dumps(bad), encoding="utf-8")
    (tmp_path / "x").mkdir()
    _, out2 = _run(tmp_path / "x", monkeypatch, file=f)
    assert (out2 / "status").read_text(encoding="utf-8").strip() == "failed"


def test_a_patch_for_a_modality_without_a_schema_is_a_problem(tmp_path, monkeypatch):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"format": V2, "files": {"patches/nosuch.json": LICENSE}}), encoding="utf-8")
    code, out = _run(tmp_path, monkeypatch, file=f)
    assert "patches/nosuch.json: no modality nosuch in schemas/stable" in (out / "log").read_text(encoding="utf-8")


def test_headings_typed_into_context_do_not_replace_the_proposal_or_agreements():
    # The form puts Context before Proposal; the last duplicate heading wins, so the real ones win.
    forged = '### Proposal\n\n```json\n{"format": "evil"}\n```\n\n### Agreements\n\n- [x] a\n- [x] b\n'
    proposal = _proposal(PARENT)
    unagreed = "### Agreements\n\n- [ ] licence\n- [ ] no personal data\n"
    body = f"### Context\n\n{forged}\n" + _body(proposal, agree=unagreed)
    with pytest.raises(tp.ProposalError, match="agreements"):
        tp.extract_proposal(body)
    assert tp.extract_proposal(f"### Context\n\n{forged}\n" + _body(proposal)) == proposal


# --- proposing a new kind of data -------------------------------------------------------------

NEW_KIND = ("### Description\n\nSkin temperature from a wrist sensor\n\n### Closest kind of data\n\n_No response_\n\n"
            "### Sample file\n\n```\ntime\ttemp\n0\t33.1\n```\n\n### Agreements\n\n- [x] licence\n- [x] made up\n")


def test_sample_problems_measures_the_text_without_its_fence_and_crlf():
    body = "a\tb\r\n1\t2\r\n"
    assert tp.sample_problems(f"```\n{body}```") == tp.sample_problems(body) == []
    assert tp.sample_problems("  ") == ["the sample is empty"]
    assert tp.sample_problems("```text\n\n```") == ["the sample is empty"]
    assert "larger than 50000 bytes" in tp.sample_problems("x" * 50_001)[0]
    assert tp.sample_problems("x" * 50_000) == []
    assert tp.sample_problems("```text\n" + "x" * 50_000 + "\n```") == []


def test_check_new_kind_needs_description_sample_and_both_agreements():
    assert tp.check_new_kind(NEW_KIND) == []
    assert tp.check_new_kind(NEW_KIND.replace("\n", "\r\n")) == []
    assert tp.check_new_kind(NEW_KIND.replace("- [x] made up", "- [ ] made up"))
    assert tp.check_new_kind(NEW_KIND.replace("Skin temperature from a wrist sensor", ""))
    assert tp.check_new_kind("")


def test_check_new_kind_command_prints_one_problem_per_line(monkeypatch, capsys):
    monkeypatch.setenv("ISSUE_BODY", NEW_KIND)
    assert tp.main(["check-new-kind"]) == 0
    assert capsys.readouterr().out == ""
    monkeypatch.setenv("ISSUE_BODY", NEW_KIND.replace("- [x] made up", "- [ ] made up").replace("temp\n0", "").replace("Skin temperature from a wrist sensor", ""))
    assert tp.main(["check-new-kind"]) == 1
    assert len(capsys.readouterr().out.splitlines()) >= 2


def test_a_patch_of_another_modality_without_schemas_says_to_pass_schemas():
    doc = {"format": V2, "files": {"patches/survey.json": SWEAT}}
    _, problems = tp.check_proposal(doc, REGISTRY, SPECIMENS, json.loads(SCHEMA.read_text(encoding="utf-8")))
    assert problems and "schemas" in problems[0]


# --- any term modality: environment (one level), built in a temporary repository -----------------

NOISE = {"TermID": "prism:noise-level", "Level": "variable", "Label": "noise level", "Units": "dB",
         "Description": "Sound pressure level"}


def _env_repo(tmp_path):
    """A repository whose entities declare biosample (two levels) and environment (one level)."""
    repo = tmp_path / "repo"
    stable = repo / "schemas" / "stable"
    stable.mkdir(parents=True)
    entities = json.loads((REPO / "schemas" / "stable" / "entities.schema.json").read_text(encoding="utf-8"))
    entities["modalities"]["environment"]["terms"] = {"nonTermColumns": ["onset", "duration"]}
    (stable / "entities.schema.json").write_text(json.dumps(entities), encoding="utf-8")
    (stable / "biosample.schema.json").write_text(SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")
    (stable / "environment.schema.json").write_text("{}", encoding="utf-8")
    (repo / "terms" / "biosample").mkdir(parents=True)
    (repo / "terms" / "environment").mkdir(parents=True)
    return repo


def _env_check(repo, files, tmp_path):
    out = tmp_path / "bundle"
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"format": tp.FORMAT_V2, "files": files}), encoding="utf-8")
    assert tp.main(["check", "--repo", str(repo), "--file", str(path), "--out", str(out)]) == 0
    return out, (out / "status").read_text(encoding="utf-8").strip(), (out / "log").read_text(encoding="utf-8")


def test_environment_variable_proposal_ok(tmp_path):
    repo = _env_repo(tmp_path)
    out, status, log = _env_check(repo, {"terms/environment/noise-level.json": NOISE}, tmp_path)
    assert status == "ok", log
    written = json.loads((out / "files" / "terms" / "environment" / "noise-level.json").read_text(encoding="utf-8"))
    assert written["Status"] == "official"


def test_environment_check_proposal_with_none_specimens():
    proposal = {"format": tp.FORMAT_V2, "files": {"terms/environment/noise-level.json": NOISE}}
    terms, problems = tp.check_proposal(proposal, {}, None, modalities={"environment": {"nonTermColumns": []}})
    assert problems == [] and terms[0]["Status"] == "official"


def test_environment_term_with_dot_is_refused(tmp_path):
    repo = _env_repo(tmp_path)
    term = {**NOISE, "TermID": "prism:air-temperature.indoor"}
    _out, status, log = _env_check(repo, {"terms/environment/air-temperature.indoor.json": term}, tmp_path)
    assert status == "failed" and "air-temperature.indoor" in log and "local part" in log


def test_mixed_modalities_refused(tmp_path):
    repo = _env_repo(tmp_path)
    _out, status, log = _env_check(repo, {"terms/biosample/ferritin.json": PARENT,
                                          "terms/environment/noise-level.json": NOISE}, tmp_path)
    assert status == "failed" and "one kind of data per proposal" in log


def test_unknown_term_modality_refused(tmp_path):
    repo = _env_repo(tmp_path)
    _out, status, log = _env_check(repo, {"terms/physio/x.json": NOISE}, tmp_path)
    assert status == "failed" and "not allowed" in log and "biosample" in log and "environment" in log


def test_biosample_proposal_through_repo_needs_no_terms_or_schema_flags(tmp_path):
    repo = _env_repo(tmp_path)
    _out, status, log = _env_check(repo, {"terms/biosample/ferritin.json": PARENT}, tmp_path)
    assert status == "ok", log


def test_new_term_fields_are_allowed():
    for field, value in (("Levels", {"1": "low"}), ("CFStandardName", "air_temperature")):
        assert field in tp.ALLOWED_FIELDS


def test_explicit_missing_schema_is_a_failed_bundle(tmp_path):
    repo = _env_repo(tmp_path)
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"format": tp.FORMAT_V2, "files": {"terms/biosample/ferritin.json": PARENT}}), encoding="utf-8")
    out = tmp_path / "bundle"
    argv = ["check", "--repo", str(repo), "--terms", str(repo / "terms" / "biosample"),
            "--schema", str(tmp_path / "nope.json"), "--file", str(path), "--out", str(out)]
    assert tp.main(argv) == 0 and (out / "status").read_text(encoding="utf-8").strip() == "failed"


def test_declared_modality_without_schema_file_is_a_failed_bundle(tmp_path):
    repo = _env_repo(tmp_path)
    (repo / "schemas" / "stable" / "biosample.schema.json").unlink()
    _out, status, _log = _env_check(repo, {"terms/biosample/ferritin.json": PARENT}, tmp_path)
    assert status == "failed"
