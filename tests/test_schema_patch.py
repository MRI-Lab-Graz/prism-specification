"""scripts/schema_patch.py: additive patches to a modality schema (new enum values, new optional properties)."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("schema_patch", REPO / "scripts" / "schema_patch.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

SCHEMA = json.loads((REPO / "schemas" / "stable" / "biosample.schema.json").read_text(encoding="utf-8"))
ENUM = {"op": "add_enum_values", "path": "Technical.SpecimenType", "values": ["sweat"]}
PROP = {"op": "add_optional_properties", "path": "Technical",
        "properties": {"SweatRate": {"type": "number", "description": "Sweat rate in mg/min"}}}


def _patch(*ops):
    return {"operations": list(ops)}


def test_both_operations_are_applied_to_a_copy():
    before = copy.deepcopy(SCHEMA)
    new, notes = sp.apply_patch(SCHEMA, _patch(ENUM, PROP))
    technical = new["properties"]["Technical"]["properties"]
    assert technical["SpecimenType"]["enum"][-1] == "sweat" and "sweat" not in SCHEMA["properties"]["Technical"]["properties"]["SpecimenType"]["enum"]
    assert technical["SweatRate"] == {"type": "number", "description": "Sweat rate in mg/min"}
    assert SCHEMA == before and notes == []


def test_values_and_properties_the_schema_already_has_are_notes_not_errors():
    new, notes = sp.apply_patch(SCHEMA, _patch({**ENUM, "values": ["saliva", "sweat"]}))
    assert new["properties"]["Technical"]["properties"]["SpecimenType"]["enum"].count("saliva") == 1
    assert any("saliva" in n and "already" in n for n in notes) and "sweat" in new["properties"]["Technical"]["properties"]["SpecimenType"]["enum"]
    _, notes = sp.apply_patch(SCHEMA, _patch(PROP, {**PROP, "properties": {"Laboratory": {"type": "string"}, "Other": {"type": "string"}}}))
    assert any("Laboratory" in n for n in notes)


def test_a_patch_that_adds_nothing_is_an_error():
    with pytest.raises(sp.PatchError, match="nothing to add"):
        sp.apply_patch(SCHEMA, _patch({**ENUM, "values": ["saliva"]}))


def test_enum_fields_lists_the_extendable_enums():
    fields = sp.enum_fields(SCHEMA)
    assert {"Technical.SpecimenType", "Technical.CollectionMethod", "Technical.Anticoagulant"} <= set(fields)
    assert "Study.BiosampleName" not in fields


def _problems(patch):
    return sp.validate_patch(patch, SCHEMA)


@pytest.mark.parametrize(
    "patch",
    [
        None, [], "x", {}, {"operations": []}, {"operations": "x"}, {"operations": [ENUM], "extra": 1},
        {"operations": [ENUM] * 21},
        {"operations": ["x"]}, {"operations": [{"op": "remove_enum_values", "path": "Technical.SpecimenType", "values": ["serum"]}]},
        {"operations": [{**ENUM, "extra": 1}]}, {"operations": [{"path": "Technical.SpecimenType", "values": ["x"]}]},
        {"operations": [{**ENUM, "path": "Technical..SpecimenType"}]}, {"operations": [{**ENUM, "path": ""}]},
        {"operations": [{**ENUM, "path": "../x"}]}, {"operations": [{**ENUM, "path": "Technical.SpecimenType\n"}]},
        {"operations": [{**ENUM, "path": "$defs.x"}]}, {"operations": [{**ENUM, "path": "Technical.Nope"}]},
        {"operations": [{**ENUM, "path": "Technical.FastingRequired"}]},  # not an enum
        {"operations": [{**ENUM, "path": "Technical"}]},
        {"operations": [{**ENUM, "path": "a.b.c.d.e"}]},
        {"operations": [{**ENUM, "values": []}]}, {"operations": [{**ENUM, "values": "sweat"}]},
        {"operations": [{**ENUM, "values": [5]}]}, {"operations": [{**ENUM, "values": ["Sweat"]}]},
        {"operations": [{**ENUM, "values": ["sweat\n"]}]}, {"operations": [{**ENUM, "values": ["a" * 64]}]},
        {"operations": [{**ENUM, "values": ["sweat", "sweat"]}]}, {"operations": [{**ENUM, "values": [f"v{n}" for n in range(21)]}]},
        {"operations": [{**PROP, "path": "Technical.SpecimenType"}]},  # not an object with properties
        {"operations": [{**PROP, "properties": {}}]}, {"operations": [{**PROP, "properties": []}]},
        {"operations": [{**PROP, "properties": {"sweatrate": {"type": "number"}}}]},  # lowercase name
        {"operations": [{**PROP, "properties": {"A" * 64: {"type": "number"}}}]},
        {"operations": [{**PROP, "properties": {"Bad Name": {"type": "number"}}}]},
        {"operations": [{**PROP, "properties": {"X": "number"}}]},
        {"operations": [{**PROP, "properties": {"X": {"description": "no type"}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "object"}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "array"}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": ["string", "null"]}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "string", "$ref": "#/definitions/x"}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "string", "pattern": "(a+)+$"}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "string", "required": ["Y"]}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "string", "properties": {}}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "string", "description": "d" * 501}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "string", "description": 5}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "string", "enum": "a"}}}]},
        {"operations": [{**PROP, "properties": {"X": {"type": "string", "enum": [1]}}}]},
        {"operations": [{**PROP, "properties": {f"P{n}": {"type": "string"} for n in range(21)}}]},
    ],
)
def test_hostile_patches_are_problems_never_exceptions(patch):
    assert _problems(patch), patch
    with pytest.raises(sp.PatchError):
        sp.apply_patch(SCHEMA, patch)


def test_a_valid_patch_has_no_problems():
    assert _problems(_patch(ENUM, PROP)) == []


def test_a_property_enum_and_all_four_types_are_allowed():
    props = {"A": {"type": "string", "enum": ["x", "y"]}, "B": {"type": "integer"}, "C": {"type": "boolean"}, "D": {"type": "number", "description": "d"}}
    new, _ = sp.apply_patch(SCHEMA, _patch({**PROP, "properties": props}))
    assert new["properties"]["Technical"]["properties"]["A"]["enum"] == ["x", "y"]


def test_the_patch_never_touches_required_or_other_keys():
    new, _ = sp.apply_patch(SCHEMA, _patch(ENUM, PROP))
    assert new["required"] == SCHEMA["required"] and new["properties"]["Technical"]["required"] == SCHEMA["properties"]["Technical"]["required"]
    assert {k: v for k, v in new.items() if k != "properties"} == {k: v for k, v in SCHEMA.items() if k != "properties"}


def test_additions_lists_exactly_what_will_be_added_once():
    adds, notes = sp.additions(SCHEMA, _patch({**ENUM, "values": ["saliva", "sweat", "tears"]}, {**ENUM, "values": ["sweat", "wipe"]}, PROP))
    assert adds == [
        {"kind": "enum", "path": "Technical.SpecimenType", "values": ["sweat", "tears"]},
        {"kind": "enum", "path": "Technical.SpecimenType", "values": ["wipe"]},
        {"kind": "properties", "path": "Technical", "properties": PROP["properties"]},
    ]
    assert any("saliva" in n for n in notes) and any("sweat" in n for n in notes)
    with pytest.raises(sp.PatchError, match="nothing to add"):
        sp.additions(SCHEMA, _patch({**ENUM, "values": ["saliva"]}))
