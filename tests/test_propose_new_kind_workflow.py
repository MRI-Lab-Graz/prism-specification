"""The propose-new-kind-of-data issue form and workflow: untrusted issue text must never reach a shell."""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
FORM = REPO / ".github" / "ISSUE_TEMPLATE" / "propose-new-kind-of-data.yml"
WORKFLOW = REPO / ".github" / "workflows" / "propose-new-kind-of-data.yml"


def _form():
    return yaml.safe_load(FORM.read_text(encoding="utf-8"))


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _field(form, field_id):
    return next(item for item in form["body"] if item.get("id") == field_id)


def test_new_kind_form_fields_and_order():
    form = _form()
    assert form["name"] == "Propose a new kind of data"
    assert form["labels"] == ["type: new-kind-of-data", "status: needs-triage"]
    assert [i.get("id") for i in form["body"] if i.get("id")] == ["description", "closest_kind", "sample", "agreements"]


def test_new_kind_form_field_details():
    form = _form()
    for field_id, kind, label, required in [("description", "textarea", "Description", True),
                                            ("closest_kind", "input", "Closest kind of data", False),
                                            ("sample", "textarea", "Sample file", True)]:
        field = _field(form, field_id)
        assert field["type"] == kind and field["attributes"]["label"] == label
        assert bool(field.get("validations", {}).get("required")) is required
    assert _field(form, "sample")["attributes"]["render"] == "text"
    agreements = _field(form, "agreements")
    assert agreements["attributes"]["label"] == "Agreements"
    options = agreements["attributes"]["options"]
    assert len(options) == 2 and all(o["required"] for o in options)
    assert options[1]["label"] == "The sample is made up and contains no real participant data."
    intro = form["body"][0]["attributes"]["value"]
    assert "PRISM release" in intro and "attachments" in intro


def test_workflow_runs_on_new_issues_with_the_label_only_and_has_minimal_permissions():
    wf = _workflow()
    assert wf[True]["issues"]["types"] == ["opened"]  # `on` is parsed as the boolean True by YAML 1.1
    assert wf["permissions"] == {}
    assert len(wf["jobs"]) == 1
    job = next(iter(wf["jobs"].values()))
    assert "type: new-kind-of-data" in job["if"]
    assert job["permissions"] == {"contents": "read", "issues": "write"}


def test_new_kind_workflow_passes_issue_text_only_through_env():
    job = next(iter(_workflow()["jobs"].values()))
    for step in job["steps"]:
        assert "${{" not in step.get("run", ""), step.get("name")
    check = next(s for s in job["steps"] if "check-new-kind" in s.get("run", ""))
    assert check["env"]["ISSUE_BODY"] == "${{ github.event.issue.body }}"
    comment = [s for s in job["steps"] if "gh issue comment" in s.get("run", "")]
    assert comment and all(s["env"]["ISSUE_NUMBER"] == "${{ github.event.issue.number }}" for s in comment)
    assert all('"$ISSUE_NUMBER"' in s["run"] for s in comment)


def test_checkout_has_no_credentials_and_every_action_is_pinned():
    job = next(iter(_workflow()["jobs"].values()))
    checkout = next(s for s in job["steps"] if "checkout" in s.get("uses", ""))
    assert checkout["with"]["persist-credentials"] is False
    for step in job["steps"]:
        if "uses" in step:
            assert re.search(r"@[0-9a-f]{40}( |$)", step["uses"]), step["uses"]


def test_workflow_opens_no_pr_and_moves_no_artifacts():
    text = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in ("pr create", "upload-artifact", "download-artifact", "git push", "curl", "wget"):
        assert forbidden not in text
