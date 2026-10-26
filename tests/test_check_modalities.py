"""scripts/check_modalities.py: entities entries and modality schema conventions."""

import importlib.util
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "schemas" / "stable"

_spec = importlib.util.spec_from_file_location("check_modalities", REPO / "scripts" / "check_modalities.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _entities():
    return json.loads((SCHEMAS / "entities.schema.json").read_text(encoding="utf-8"))


def test_the_repository_passes():
    assert mod.main([]) == 0


def test_an_unknown_entry_key_is_reported():
    entities = _entities()
    entities["modalities"]["biosample"]["colour"] = "red"
    assert any("biosample" in p and "colour" in p for p in mod.check(entities, SCHEMAS))


def test_a_prism_entry_needs_described_columns_but_a_bids_entry_does_not():
    entities = _entities()
    del entities["modalities"]["biosample"]["describedColumns"]
    problems = mod.check(entities, SCHEMAS)
    assert any("biosample" in p and "describedColumns" in p for p in problems)
    assert not any(p.startswith("anat") for p in problems)


def test_a_prism_modality_without_a_schema_file_is_reported():
    entities = _entities()
    entities["modalities"]["skin"] = {"kind": "prism", "description": "x", "suffixes": ["skin"],
                                      "extensions": ["tsv"], "describedColumns": True}
    assert any(p.startswith("skin") and "schema" in p for p in mod.check(entities, SCHEMAS))


def test_a_schema_whose_id_does_not_match_its_version_is_reported(tmp_path):
    shutil.copytree(SCHEMAS, tmp_path / "s")
    path = tmp_path / "s" / "biosample.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["$id"] = "https://example.org/biosample/v9.9.9"
    path.write_text(json.dumps(schema), encoding="utf-8")
    problems = mod.check(_entities(), tmp_path / "s")
    assert any("biosample" in p and "$id" in p for p in problems)


def test_terms_folder_and_declaration_agree(tmp_path):
    shutil.copytree(SCHEMAS, tmp_path / "s")
    (tmp_path / "terms" / "events").mkdir(parents=True)  # a folder without a declaration
    problems = mod.check(_entities(), tmp_path / "s", tmp_path / "terms")
    assert len([p for p in problems if "events" in p and "terms" in p]) == 1
    # the reverse: biosample declares terms but the folder is absent
    (tmp_path / "terms" / "events").rmdir()
    problems = mod.check(_entities(), tmp_path / "s", tmp_path / "terms")
    assert len([p for p in problems if "biosample" in p and "terms" in p]) == 1


def test_context_field_must_be_an_enum():
    entities = _entities()
    entities["modalities"]["biosample"]["terms"]["contextField"] = "Technical.Nope"
    assert any("Technical.Nope" in p for p in mod.check(entities, SCHEMAS, REPO / "terms"))


def test_shipped_entities_pass():
    assert mod.check(_entities(), SCHEMAS, REPO / "terms") == []
