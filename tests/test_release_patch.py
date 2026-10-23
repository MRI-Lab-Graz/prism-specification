"""scripts/release_patch.py: a schema patch becomes a reviewable schema release (archive, bump, regenerated docs)."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sp = _load("schema_patch")
rp = _load("release_patch")
PATCH = {"operations": [{"op": "add_enum_values", "path": "Technical.SpecimenType", "values": ["sweat"]}]}


def _git(root, *args):
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": __import__("os").environ["PATH"], "HOME": str(root)}
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env)


@pytest.fixture
def tree(tmp_path):
    """A copy of this repository's specification files with git history."""
    root = tmp_path / "repo"
    for folder in ("schemas", "specs", "scripts", "terms"):
        shutil.copytree(REPO / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _stable(root):
    return json.loads((root / "schemas" / "stable" / "biosample.schema.json").read_text(encoding="utf-8"))


def test_release_archives_bumps_patches_and_regenerates(tree):
    original = (tree / "schemas" / "stable" / "biosample.schema.json").read_bytes()
    old = json.loads(original)["version"]
    written = rp.release(tree, tree, "biosample", PATCH)
    new = _stable(tree)
    assert written == [f"schemas/archive/biosample/{old}.schema.json", "schemas/stable/biosample.schema.json", "specs/biosample.md"]
    assert (tree / written[0]).read_bytes() == original  # an exact copy of the previous stable file
    major, minor, _patch = map(int, old.split("."))
    assert new["version"] == f"{major}.{minor + 1}.0" and new["$id"].endswith(f"/v{new['version']}")
    assert "sweat" in new["properties"]["Technical"]["properties"]["SpecimenType"]["enum"]
    assert "`sweat`" in (tree / "specs" / "biosample.md").read_text(encoding="utf-8")  # the table lists it


def test_the_released_tree_passes_the_repository_checks(tree):
    rp.release(tree, tree, "biosample", PATCH)
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "release")
    versions = subprocess.run([sys.executable, str(tree / "scripts" / "check_schema_versions.py"), "HEAD~1", "HEAD"], capture_output=True, text=True)
    assert versions.returncode == 0, versions.stdout + versions.stderr
    tables = subprocess.run([sys.executable, str(tree / "scripts" / "generate_schema_reference.py"), "--check"], capture_output=True, text=True)
    assert tables.returncode == 0, tables.stdout + tables.stderr


def test_source_and_destination_can_differ_and_the_source_is_not_touched(tree, tmp_path):
    before = (tree / "schemas" / "stable" / "biosample.schema.json").read_bytes()
    dest = tmp_path / "bundle"
    written = rp.release(tree, dest, "biosample", PATCH)
    assert (tree / "schemas" / "stable" / "biosample.schema.json").read_bytes() == before
    assert all((dest / path).is_file() for path in written)
    assert not (dest / "schemas" / "stable" / "physio.schema.json").exists()  # only what changed


def test_releasing_the_same_patch_twice_is_an_error_and_writes_nothing(tree, tmp_path):
    rp.release(tree, tree, "biosample", PATCH)
    with pytest.raises(rp.PatchError, match="nothing to add"):  # the class release_patch exports: scripts load each other by path
        rp.release(tree, tmp_path / "again", "biosample", PATCH)
    assert not (tmp_path / "again").exists()


def test_an_existing_archive_entry_is_never_overwritten(tree, tmp_path):
    old = _stable(tree)["version"]
    (tree / "schemas" / "archive" / "biosample").mkdir(parents=True, exist_ok=True)
    (tree / "schemas" / "archive" / "biosample" / f"{old}.schema.json").write_text("{}", encoding="utf-8")
    with pytest.raises(rp.ReleaseError, match="already archived"):
        rp.release(tree, tmp_path / "out", "biosample", PATCH)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("version,ident", [("1.1", "https://prism.org/schemas/biosample/v1.1"), ("1.1.0", "https://prism.org/schemas/biosample/other"), ("x", "x")])
def test_an_unexpected_version_or_id_is_an_error(tree, tmp_path, version, ident):
    path = tree / "schemas" / "stable" / "biosample.schema.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"], data["$id"] = version, ident
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(rp.ReleaseError):
        rp.release(tree, tmp_path / "out", "biosample", PATCH)
    assert not (tmp_path / "out").exists()


def test_an_unknown_modality_is_an_error(tree, tmp_path):
    with pytest.raises(rp.ReleaseError, match="modality"):
        rp.release(tree, tmp_path / "out", "../x", PATCH)
    with pytest.raises(rp.ReleaseError, match="no schema"):
        rp.release(tree, tmp_path / "out", "nosuchmodality", PATCH)


def test_the_released_schema_keeps_the_file_style_so_the_diff_is_small(tree):
    """A reviewer should see the added value and the version bump, not a re-formatted file."""
    import difflib

    path = tree / "schemas" / "stable" / "biosample.schema.json"
    before = path.read_text(encoding="utf-8").splitlines()
    rp.release(tree, tree, "biosample", PATCH)
    after = path.read_text(encoding="utf-8").splitlines()
    changed = [line for line in difflib.unified_diff(before, after, lineterm="", n=0) if line[:1] in "+-" and line[:3] not in ("+++", "---")]
    assert len(changed) <= 8, "\n".join(changed[:20])


# --- surgical edits: the file's own formatting stays, whatever it is ------------------------------------

def _released(tree, patch=PATCH, rewrite=None):
    path = tree / "schemas" / "stable" / "biosample.schema.json"
    if rewrite:
        path.write_text(rewrite(path.read_text(encoding="utf-8")), encoding="utf-8")
    original = json.loads(path.read_text(encoding="utf-8"))
    rp.release(tree, tree, "biosample", patch)
    return original, path.read_text(encoding="utf-8")


def _expected(original, patch):
    expected, _notes = sp.apply_patch(original, patch)
    major, minor, _p = map(int, original["version"].split("."))
    expected["version"] = f"{major}.{minor + 1}.0"
    expected["$id"] = original["$id"][: -len(original["version"])] + expected["version"]
    return expected


PROP_PATCH = {"operations": [
    {"op": "add_enum_values", "path": "Technical.SpecimenType", "values": ["sweat", "tears"]},
    {"op": "add_optional_properties", "path": "Technical", "properties": {"SweatRate": {"type": "number", "description": "mg/min"}}},
    {"op": "add_enum_values", "path": "Technical.CollectionMethod", "values": ["wipe"]},
]}


def _lines_changed(before: str, after: str) -> int:
    import difflib

    return len([l for l in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")])


def test_the_edited_file_means_exactly_what_the_applied_patch_means(tree):
    original, text = _released(tree, PROP_PATCH)
    assert json.loads(text) == _expected(original, PROP_PATCH)


def test_a_property_is_inserted_in_the_style_of_its_neighbours(tree):
    before = (tree / "schemas" / "stable" / "biosample.schema.json").read_text(encoding="utf-8")
    _, text = _released(tree, PROP_PATCH)
    assert _lines_changed(before, text) <= 12  # version, $id, three enum edits and one property: not the whole file
    assert '"SweatRate": {' in text and text.count("\n") - before.count("\n") <= 6


def test_a_multi_line_enum_array_is_extended_in_place(tree):
    def spread(text):
        return text.replace('"enum": ["whole-blood", "serum",', '"enum": [\n            "whole-blood", "serum",', 1).replace('"csf", "other"]', '"csf",\n            "other"\n          ]', 1)

    original, text = _released(tree, PATCH, rewrite=spread)
    assert json.loads(text) == _expected(original, PATCH)
    assert '"other",\n            "sweat"\n          ]' in text


def test_an_unusual_layout_falls_back_to_a_full_rewrite_that_is_still_correct(tree):
    original, text = _released(tree, PROP_PATCH, rewrite=lambda t: json.dumps(json.loads(t), separators=(",", ":")))  # minified: one line
    assert json.loads(text) == _expected(original, PROP_PATCH)


def test_an_odd_but_valid_layout_is_handled(tree):
    def odd(text):  # tabs, CRLF, and spaces around colons
        return json.dumps(json.loads(text), indent="\t").replace("\n", "\r\n").replace('": ', '" : ')

    original, text = _released(tree, PROP_PATCH, rewrite=odd)
    assert json.loads(text) == _expected(original, PROP_PATCH)
