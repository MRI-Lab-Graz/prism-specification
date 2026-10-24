"""The propose-metric issue form and workflow: untrusted issue text must never reach a shell."""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
FORM = REPO / ".github" / "ISSUE_TEMPLATE" / "propose-metric.yml"
WORKFLOW = REPO / ".github" / "workflows" / "propose-metric.yml"


def _form():
    return yaml.safe_load(FORM.read_text(encoding="utf-8"))


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _field(form, field_id):
    return next(item for item in form["body"] if item.get("id") == field_id)


def test_form_has_a_required_json_proposal_and_two_required_agreements():
    form = _form()
    assert "type: new-metric" in form["labels"]
    proposal = _field(form, "proposal")
    assert proposal["type"] == "textarea" and proposal["attributes"]["label"] == "Proposal"
    assert proposal["attributes"]["render"] == "json" and proposal["validations"]["required"] is True
    agreements = _field(form, "agreements")
    assert agreements["attributes"]["label"] == "Agreements"
    assert len(agreements["attributes"]["options"]) == 2 and all(o["required"] for o in agreements["attributes"]["options"])


def test_workflow_runs_on_new_issues_with_the_metric_label_only():
    wf = _workflow()
    assert wf[True]["issues"]["types"] == ["opened"]  # `on` is parsed as the boolean True by YAML 1.1
    assert wf["permissions"] == {}
    for name in ("check", "report"):
        assert "type: new-metric" in wf["jobs"][name]["if"]


def test_check_job_is_read_only_and_has_no_credentials():
    job = _workflow()["jobs"]["check"]
    assert job["permissions"] == {"contents": "read"}
    checkout = next(s for s in job["steps"] if "checkout" in s.get("uses", ""))
    assert checkout["with"]["persist-credentials"] is False


def test_no_run_step_interpolates_github_context():
    for name, job in _workflow()["jobs"].items():
        for step in job["steps"]:
            assert "${{" not in step.get("run", ""), (name, step.get("name"))


def test_every_action_is_pinned_to_a_commit():
    for job in _workflow()["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.search(r"@[0-9a-f]{40}( |$)", step["uses"]), step["uses"]


def test_report_job_verifies_the_bundle_and_only_trusted_authors_get_a_pull_request():
    job = _workflow()["jobs"]["report"]
    text = yaml.safe_dump(job)
    assert "find bundle" in text and "needs-changes" in text
    pr_step = next(s for s in job["steps"] if "draft" in s.get("name", "").lower())
    for role in ("OWNER", "MEMBER", "COLLABORATOR"):
        assert role in pr_step["if"]
    assert "--draft" in pr_step["run"]


# --- the verify step is shell: run the workflow's own snippet against real bundles -------------

import subprocess

import pytest


def _verify_script():
    step = next(s for s in _workflow()["jobs"]["report"]["steps"] if s.get("id") == "bundle")
    return step["run"]


def _bundle(root: Path, extra=()):
    folder = root / "bundle" / "files" / "terms" / "biosample"
    folder.mkdir(parents=True)
    (root / "bundle" / "status").write_text("ok\n", encoding="utf-8")
    (root / "bundle" / "log").write_text("", encoding="utf-8")
    (folder / "ferritin.json").write_text("{}\n", encoding="utf-8")
    for rel in extra:
        target = root / "bundle" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")
    return root


def _verify(root: Path):
    env = {"PATH": __import__("os").environ["PATH"], "GITHUB_OUTPUT": str(root / "out.txt")}
    return subprocess.run(["bash", "-e", "-c", _verify_script()], cwd=root, env=env, capture_output=True, text=True)


def test_verify_step_accepts_a_good_bundle(tmp_path):
    assert _verify(_bundle(tmp_path)).returncode == 0


@pytest.mark.parametrize("extra", [
    ("extra.txt",), ("files/extra.txt",), ("files/terms/biosample/..evil",), ("files/terms/biosample/UPPER.json",),
    ("files/terms/biosample/" + "a" * 64 + ".json",), ("files/terms/biosample/a.b.c.json",),
    ("terms/biosample/ferritin.json",),  # the layout before schema patches: not accepted any more
    ("files/scripts/term_proposal.py",), ("files/.github/workflows/x.yml",), ("files/CODEOWNERS",), ("files/LICENSE",),
    ("files/schemas/stable/biosample.json",), ("files/schemas/stable/UPPER.schema.json",), ("files/schemas/stable/x/y.schema.json",),
    ("files/schemas/stable/../x.schema.json",), ("files/schemas/v0.2/biosample.schema.json",),
    ("files/schemas/archive/biosample/latest.schema.json",), ("files/schemas/archive/biosample/1.2.schema.json",),
    ("files/schemas/archive/biosample/1.2.0.schema.json.bak",), ("files/schemas/archive/1.2.0.schema.json",),
    ("files/specs/x/y.md",), ("files/specs/biosample.txt",), ("files/specs/UPPER.md",), ("files/specs/.md",),
])
def test_verify_step_rejects_unexpected_files(tmp_path, extra):
    result = _verify(_bundle(tmp_path, extra))
    assert result.returncode != 0 and "unexpected files" in result.stderr


def test_verify_step_rejects_symlinks(tmp_path):
    root = _bundle(tmp_path)
    (root / "bundle" / "link").symlink_to("/etc/passwd")
    assert _verify(root).returncode != 0


def test_verify_step_rejects_newline_tricks_in_directory_names(tmp_path):
    # find prints this one path as two lines, each of which looks like an allowed file
    root = _bundle(tmp_path)
    trick = root / "bundle" / "files" / "terms" / "biosample" / "x.json\nbundle"
    trick.mkdir()
    (trick / "status").write_text("x\n", encoding="utf-8")
    result = _verify(root)
    assert result.returncode != 0 and "unexpected files" in result.stderr


def test_pr_step_no_longer_passes_a_log_file():
    step = next(s for s in _workflow()["jobs"]["report"]["steps"] if "draft" in s.get("name", "").lower())
    assert "LOG_FILE" not in step.get("env", {})


# --- schema releases: the bundle may also hold the archive, the stable schema and the spec page ---------

@pytest.mark.parametrize("extra", [
    ("files/schemas/stable/biosample.schema.json",),
    ("files/schemas/archive/biosample/1.2.0.schema.json",),
    ("files/specs/biosample.md",),
    ("files/terms/biosample/ferritin.serum.json",),
    ("files/schemas/stable/biosample.schema.json", "files/schemas/archive/biosample/1.2.0.schema.json", "files/specs/biosample.md"),
])
def test_verify_step_accepts_the_files_of_a_schema_release(tmp_path, extra):
    result = _verify(_bundle(tmp_path, extra))
    assert result.returncode == 0, result.stderr


def test_the_pull_request_step_copies_only_the_verified_files_and_marks_schema_releases():
    step = next(s for s in _workflow()["jobs"]["report"]["steps"] if "draft" in s.get("name", "").lower())
    script = step["run"]
    assert "cp -R bundle/files/. ." in script and "bundle/terms" not in script
    assert "git add terms schemas specs" in script
    assert "SCHEMA_RELEASE" in script and "bundle/files/schemas" in script
    assert script.index("pr-body") > script.index("SCHEMA_RELEASE")  # the marker is set before the text is written


def test_the_failure_comment_reads_the_log_of_the_bundle():
    step = next(s for s in _workflow()["jobs"]["report"]["steps"] if "problems" in s.get("name", "").lower())
    assert "bundle/log" in step["run"]


def test_form_has_an_optional_context_field_before_the_proposal():
    form = _form()
    ids = [item.get("id") for item in form["body"]]
    assert ids.index("context") < ids.index("proposal")
    field = _field(form, "context")
    assert field["type"] == "textarea"
    assert field["attributes"]["label"] == "Context"
    assert not field.get("validations", {}).get("required")
