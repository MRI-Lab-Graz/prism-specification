import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_eyetracking_is_not_a_modality():
    entities = json.loads((ROOT / "schemas/stable/entities.schema.json").read_text())
    assert "eyetracking" not in entities["modalities"]


def test_no_live_eyetracking_files_but_the_archived_schema_stays():
    assert not (ROOT / "schemas/stable/eyetracking.schema.json").exists()
    assert not (ROOT / "schemas/v0.2/eyetracking.schema.json").exists()
    assert not (ROOT / "specs/eyetracking.md").exists()
    archived = json.loads((ROOT / "schemas/archive/eyetracking/1.1.0.schema.json").read_text())
    assert archived["version"] == "1.1.0"
