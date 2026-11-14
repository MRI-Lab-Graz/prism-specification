"""The meaning fields are out of the six schemas again.

Temporary: delete this file in a later task, once origin/main has moved on past the removal.
"""
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
# modality: (block version, pre-block version, new version)
TABLE = {
    "biometrics": ("1.1.2", "1.1.1", "1.1.3"),
    "biosample": ("1.1.1", "1.1.0", "1.1.2"),
    "environment": ("2.1.1", "2.1.0", "2.1.2"),
    "events": ("1.1.1", "1.1.0", "1.1.2"),
    "physio": ("1.2.1", "1.2.0", "1.2.2"),
    "survey": ("2.1.2", "2.1.1", "2.1.3"),
}


def _stable(m):
    return REPO / "schemas" / "stable" / f"{m}.schema.json"


def _archive(m, v):
    return REPO / "schemas" / "archive" / m / f"{v}.schema.json"


@pytest.mark.parametrize("m", TABLE)
def test_stable_equals_pre_block_except_version_and_id(m):
    _, pre, new = TABLE[m]
    a, b = json.loads(_stable(m).read_text("utf-8")), json.loads(_archive(m, pre).read_text("utf-8"))
    for d in (a, b):
        d["version"] = d["$id"] = ""
    assert a == b
    la, lb = _stable(m).read_text("utf-8").splitlines(), _archive(m, pre).read_text("utf-8").splitlines()
    assert len(la) == len(lb)
    differing = [x for x, y in zip(la, lb) if x != y]
    assert len(differing) == 2
    assert sorted(l.strip().split('"')[1] for l in differing) == ["$id", "version"]


@pytest.mark.parametrize("m", TABLE)
def test_new_version_and_no_meaning_words(m):
    _, _, new = TABLE[m]
    text = _stable(m).read_text("utf-8")
    data = json.loads(text)
    assert data["version"] == new
    assert data["$id"].endswith(f"/v{new}")
    for word in ("IsAbout", "LevelIsAbout", "ValueMappings"):
        assert word not in text


@pytest.mark.parametrize("m", TABLE)
def test_block_version_is_archived_as_it_was_on_main(m):
    block = TABLE[m][0]
    r = subprocess.run(["git", "show", f"origin/main:schemas/stable/{m}.schema.json"], cwd=REPO, capture_output=True)
    if r.returncode:
        pytest.skip("origin/main is not available")
    assert _archive(m, block).read_bytes() == r.stdout


def test_meaning_files_are_gone():
    for p in ("scripts/meaning_block.py", "schemas/shared", "specs/meaning.md"):
        assert not (REPO / p).exists()
