import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_schema_versions.py"
spec = importlib.util.spec_from_file_location("check_schema_versions", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

STABLE = "schemas/stable/survey.schema.json"
ARCH = "schemas/archive/survey/1.0.0.schema.json"


def _doc(version, extra=0):
    return json.dumps({"version": version, "x": extra})


def _run(changes, base=None, head=None):
    base, head = base or {}, head or {}
    return mod.check(changes, base.get, head.get, lambda p: p in head, {"survey"})


def test_new_modality_without_archive_passes():
    assert _run([("A", STABLE)], head={STABLE: _doc("1.0.0")}) == []


def test_correct_release_passes():
    errors = _run(
        [("M", STABLE), ("A", ARCH)],
        base={STABLE: _doc("1.0.0")},
        head={STABLE: _doc("1.1.0", 1), ARCH: _doc("1.0.0")},
    )
    assert errors == []


def test_changed_content_without_a_version_bump_fails():
    errors = _run([("M", STABLE)], base={STABLE: _doc("1.0.0")}, head={STABLE: _doc("1.0.0", 1)})
    assert any("version" in e for e in errors)


def test_bump_without_archiving_the_previous_version_fails():
    errors = _run([("M", STABLE)], base={STABLE: _doc("1.0.0")}, head={STABLE: _doc("1.1.0")})
    assert any("1.0.0" in e and "archive" in e for e in errors)


def test_archived_copy_must_equal_the_previous_stable_file():
    errors = _run(
        [("M", STABLE), ("A", ARCH)],
        base={STABLE: _doc("1.0.0")},
        head={STABLE: _doc("1.1.0"), ARCH: _doc("1.0.0", 99)},
    )
    assert any("differs" in e for e in errors)


def test_editing_or_deleting_an_archive_file_fails():
    for status in ("M", "D"):
        assert _run([(status, ARCH)], base={ARCH: _doc("1.0.0")}, head={ARCH: _doc("1.0.0", 1)})


def test_unrelated_changes_pass():
    assert _run([("M", "docs/index.rst"), ("M", "schemas/stable/project.schema.json")]) == []


def test_unreadable_version_in_head_fails():
    errors = _run([("M", STABLE)], base={STABLE: _doc("1.0.0")}, head={STABLE: '{"x": 1}'})
    assert any("could not read" in e and "head" in e for e in errors)


def test_invalid_json_in_head_fails():
    errors = _run([("M", STABLE)], base={STABLE: _doc("1.0.0")}, head={STABLE: "{not json"})
    assert any("could not read" in e and "head" in e for e in errors)


def test_invalid_json_in_base_fails():
    errors = _run([("M", STABLE)], base={STABLE: "{not json"}, head={STABLE: _doc("1.1.0")})
    assert any("could not read" in e and "base" in e for e in errors)


def test_parse_name_status_splits_status_and_path():
    text = f"D\t{ARCH}\nA\t{ARCH}.new\n"
    assert mod.parse_name_status(text) == [("D", ARCH), ("A", ARCH + ".new")]


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True,
    )


def _commit_all(repo, message):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    monkeypatch.chdir(repo)
    stable = repo / "schemas/stable"
    stable.mkdir(parents=True)
    (stable / "entities.schema.json").write_text(json.dumps({"modalities": {"survey": {}}}))
    return repo


def test_git_mv_of_archived_file_is_rejected(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    archive = repo / "schemas/archive/survey"
    archive.mkdir(parents=True)
    (archive / "1.0.0.schema.json").write_text(_doc("1.0.0"))
    _commit_all(repo, "base")
    _git(repo, "mv", "schemas/archive/survey/1.0.0.schema.json", "schemas/archive/survey/moved.schema.json")
    _commit_all(repo, "move archive")

    assert mod.main(["x", "HEAD~1", "HEAD"]) == 1
    assert "archived versions are frozen" in capsys.readouterr().out


def test_missing_entities_schema_fails_loudly(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    (repo / "schemas/stable/entities.schema.json").unlink()
    (repo / "README.md").write_text("x")
    _commit_all(repo, "base")
    (repo / "README.md").write_text("y")
    _commit_all(repo, "head")

    assert mod.main(["x", "HEAD~1", "HEAD"]) == 1
    assert "modalities" in capsys.readouterr().out


@pytest.mark.parametrize("status, head, lost", [
    ("M", "prism:a\nprism:c\n", "prism:b"),
    ("D", None, "prism:a, prism:b"),
])
def test_a_released_survey_id_line_is_never_lost(status, head, lost):
    errors = _run([(status, "ids/survey-ids.txt")], {"ids/survey-ids.txt": "prism:a\nprism:b\n"},
                  {} if head is None else {"ids/survey-ids.txt": head})
    assert errors == [f"ids/survey-ids.txt: released IDs are frozen, lines lost: {lost}"]


def test_adding_a_released_survey_id_passes():
    assert _run([("M", "ids/survey-ids.txt")], {"ids/survey-ids.txt": "prism:a\n"},
                {"ids/survey-ids.txt": "prism:0\nprism:a\n"}) == []


def test_ids_added_to_the_base_after_the_branch_point_are_not_lost(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    ids = repo / "ids" / "survey-ids.txt"
    ids.parent.mkdir()
    ids.write_text("prism:a\n", encoding="utf-8")
    _commit_all(repo, "ids")
    _git(repo, "branch", "main-now")
    ids.write_text("prism:a\nprism:x\n", encoding="utf-8")
    _commit_all(repo, "branch adds x")
    _git(repo, "branch", "topic")
    _git(repo, "checkout", "-q", "main-now")
    ids.write_text("prism:a\nprism:y\n", encoding="utf-8")
    _commit_all(repo, "base adds y")

    assert mod.main(["x", "main-now", "topic"]) == 0, capsys.readouterr().out
