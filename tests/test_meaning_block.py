"""scripts/meaning_block.py: the shared meaning block, added to a modality schema in place as text."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "schemas" / "shared"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mb = _load("meaning_block")
stamp, missing = mb.stamp, mb.missing
BLOCK = mb.load_block(SHARED)
# the real locations file names real modalities; the synthetic schema below is modality "demo"
LOCATIONS = {"modalities": {"demo": {"column": [["additionalProperties"], ["properties", "onset"]],
                                     "file": [["properties", "Study"]]}}}

TERMURL_OLD = '"TermURL": {"type": "string", "description": "URL of a definition"}'
SYNTH = """{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://prism.org/schemas/demo/v1.0.0",
  "version": "1.0.0",
  "type": "object",
  "properties": {
    "Study": {
      "type": "object",
      "properties": {
        "Name": {"type": "string"}
      }
    },
    "onset": {
      "type": "object",
      "properties": {
        "Description": { "type": "string" }
      }
    }
  },
  "additionalProperties": {
    "type": "object",
    "properties": {
      "Description": {"type": "string"},
      "Levels": {"type": "object"},
      %s
    }
  }
}
""" % TERMURL_OLD
TERMURL_OLD_LINES = {line for line in SYNTH.splitlines() if '"TermURL"' in line}


def _no_comma(lines):
    return {line.rstrip(",") for line in lines}


def test_stamp_adds_the_block_at_column_and_file_locations_and_nothing_else_changes():
    new, problems = stamp(SYNTH, "demo", BLOCK, LOCATIONS)
    assert problems == []
    doc = json.loads(new)
    col = doc["additionalProperties"]["properties"]
    assert {"IsAbout", "LevelIsAbout", "ValueMappings", "TermURL"} <= set(col)
    assert "IsAbout" in doc["properties"]["Study"]["properties"]
    assert col["IsAbout"]["items"]["required"] == ["Concept"]
    assert {"IsAbout", "ValueMappings", "TermURL"} <= set(doc["properties"]["onset"]["properties"])
    # every original line is still there (the diff is additions only, a comma after the former last
    # property, plus the TermURL replacement)
    assert _no_comma(SYNTH.splitlines()) - _no_comma(new.splitlines()) <= TERMURL_OLD_LINES
    # nothing outside the locations changed
    old = json.loads(SYNTH)
    for d in (doc, old):
        del d["additionalProperties"]["properties"], d["properties"]["Study"]["properties"]
        del d["properties"]["onset"]["properties"]
    assert doc == old


def test_level_is_about_only_where_levels_exist():
    doc = json.loads(stamp(SYNTH, "demo", BLOCK, LOCATIONS)[0])
    assert "LevelIsAbout" in doc["additionalProperties"]["properties"]
    assert "LevelIsAbout" not in doc["properties"]["onset"]["properties"]
    assert "LevelIsAbout" not in doc["properties"]["Study"]["properties"]  # a file location gets IsAbout only
    assert set(doc["properties"]["Study"]["properties"]) == {"Name", "IsAbout"}


def test_stamp_is_idempotent_and_missing_is_empty_afterwards():
    assert missing(SYNTH, "demo", BLOCK, LOCATIONS) != []
    once, _ = stamp(SYNTH, "demo", BLOCK, LOCATIONS)
    twice, problems = stamp(once, "demo", BLOCK, LOCATIONS)
    assert once == twice and problems == [] and missing(once, "demo", BLOCK, LOCATIONS) == []


def test_missing_names_each_property_stamp_would_add():
    lines = missing(SYNTH, "demo", BLOCK, LOCATIONS)
    assert len(lines) == 4 + 3 + 1  # column with Levels, column without, file
    assert any("TermURL" in line and "additionalProperties" in line for line in lines)


SYNTH_WITH_OWN_ISABOUT = SYNTH.replace('"Name": {"type": "string"}', '"Name": {"type": "string"},\n        "IsAbout": {"type": "string"}')


def test_a_conflicting_existing_property_is_a_problem_and_changes_nothing():
    text = SYNTH_WITH_OWN_ISABOUT  # IsAbout declared as {"type": "string"}
    new, problems = stamp(text, "demo", BLOCK, LOCATIONS)
    assert new == text and any("IsAbout" in p for p in problems)
    assert any("IsAbout" in line for line in missing(text, "demo", BLOCK, LOCATIONS))


SYNTH_WITH_PATTERNED_TERMURL = SYNTH.replace(TERMURL_OLD, '"TermURL": {"type": "string", "pattern": "^https://"}')


def test_a_stricter_termurl_is_a_problem():
    text = SYNTH_WITH_PATTERNED_TERMURL  # type string plus a pattern
    new, problems = stamp(text, "demo", BLOCK, LOCATIONS)
    assert new == text and any("TermURL" in p for p in problems)


@pytest.mark.parametrize("old", ['{"type": "string", "description": "URL of a definition"}',
                                 '{ "type": "string", "format": "uri" }'])
def test_a_plain_string_termurl_is_replaced_by_the_one_of_form(old):
    text = SYNTH.replace(TERMURL_OLD, f'"TermURL": {old}')
    before = Draft7Validator(json.loads(text)["additionalProperties"])
    new, problems = stamp(text, "demo", BLOCK, LOCATIONS)
    assert problems == []
    column = json.loads(new)["additionalProperties"]
    assert column["properties"]["TermURL"] == mb.fields(BLOCK)["column"]["TermURL"]
    after = Draft7Validator(column)
    string_doc = {"TermURL": "https://example.org/def"}
    assert before.is_valid(string_doc) and after.is_valid(string_doc)
    assert after.is_valid({"TermURL": {"snomed": "http://snomed.info/id/1"}})
    assert not after.is_valid({"TermURL": {"snomed": "not a url"}})


def test_an_unusual_layout_is_a_problem_never_a_rewrite():
    text = SYNTH.replace('"properties": {\n        "Name": {"type": "string"}\n      }', '"properties": {"Name": {"type": "string"}}')
    new, problems = stamp(text, "demo", BLOCK, LOCATIONS)
    assert new == text and problems


def test_an_unknown_or_pending_modality_is_a_problem():
    real = mb.load_locations(SHARED)
    for modality in ("nosuch", *real["pending"]):
        new, problems = stamp(SYNTH, modality, BLOCK, real)
        assert new == SYNTH and problems


def test_the_repository_block_and_locations_are_consistent():
    locations = mb.load_locations(SHARED)
    kinds = {name: m["kind"] for name, m in
             json.loads((REPO / "schemas/stable/entities.schema.json").read_text())["modalities"].items()}
    named = set(locations["modalities"]) | set(locations["pending"])
    assert named <= {name for name, kind in kinds.items() if kind == "prism"}
    assert named == {name for name, kind in kinds.items() if kind == "prism"}  # every prism modality is named
    for modality, where in locations["modalities"].items():
        schema = json.loads((REPO / f"schemas/stable/{modality}.schema.json").read_text())
        for path in where["column"] + where["file"]:
            obj = schema
            for key in path:
                obj = obj[key]
            assert isinstance(obj.get("properties"), dict), (modality, path)


def test_the_block_itself_is_a_valid_draft7_schema_fragment():
    fields = mb.fields(BLOCK)
    assert "<link>" not in json.dumps(fields) and "$ref" not in json.dumps(fields)
    assert set(fields["column"]) == {"IsAbout", "LevelIsAbout", "ValueMappings", "TermURL"}
    assert set(fields["file"]) == {"IsAbout"}
    for kind in ("column", "file"):
        for definition in fields[kind].values():
            Draft7Validator.check_schema(definition)
    link = Draft7Validator(fields["column"]["IsAbout"])
    assert link.is_valid([{"Concept": "prism:anxiety", "Match": "broader", "Higher": "more", "Checked": "2026-11-14"}])
    assert not link.is_valid([{"Concept": "anxiety"}]) and not link.is_valid([])


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "repo"
    for folder in ("schemas", "specs", "scripts"):
        shutil.copytree(REPO / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def test_release_archives_bumps_and_regenerates(tree):
    stable = tree / "schemas/stable/biosample.schema.json"
    old_bytes = stable.read_bytes()
    old = json.loads(old_bytes)["version"]
    major, minor, _ = map(int, old.split("."))
    written = mb.release(tree, tree, "biosample")
    archive = f"schemas/archive/biosample/{old}.schema.json"
    assert set(written) == {archive, "schemas/stable/biosample.schema.json", "specs/biosample.md"}
    assert (tree / archive).read_bytes() == old_bytes
    new = json.loads(stable.read_text())
    assert new["version"] == f"{major}.{minor + 1}.0" and new["$id"].endswith(f"/v{major}.{minor + 1}.0")
    assert mb.missing(stable.read_text(), "biosample", BLOCK, mb.load_locations(SHARED)) == []
    gsr = _load("generate_schema_reference")
    assert gsr.sync(write=False, schemas=tree / "schemas/stable", specs=tree / "specs",
                    pages={"biosample": "biosample.md"}) == []
    assert "IsAbout" in (tree / "specs/biosample.md").read_text()
    with pytest.raises(ValueError):
        mb.release(tree, tree, "biosample")  # nothing missing any more
    assert (tree / archive).read_bytes() == old_bytes


def test_release_refuses_an_existing_archive_and_an_odd_version(tree):
    stable = tree / "schemas/stable/biosample.schema.json"
    text = stable.read_text()
    old = json.loads(text)["version"]
    archive = tree / f"schemas/archive/biosample/{old}.schema.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"frozen")
    with pytest.raises(ValueError, match="archived"):
        mb.release(tree, tree, "biosample")
    assert archive.read_bytes() == b"frozen" and stable.read_text() == text
    archive.unlink()
    stable.write_text(text.replace(f'"version": "{old}"', '"version": "1.1"'))
    with pytest.raises(ValueError, match="major.minor.patch"):
        mb.release(tree, tree, "biosample")


def test_cli_check_exit_code(tmp_path, capsys):
    source = tmp_path / "repo"
    shutil.copytree(REPO / "schemas", source / "schemas")
    shared = source / "schemas" / "shared"
    locations = json.loads((shared / "meaning-locations.json").read_text(encoding="utf-8"))
    block = json.loads((shared / "meaning-block.json").read_text(encoding="utf-8"))
    block["column"]["Extra"] = {"type": "string"}  # no schema carries it, stamped or not
    (shared / "meaning-block.json").write_text(json.dumps(block), encoding="utf-8")
    assert mb.main(["check", "--source", str(source)]) == 1
    assert "biosample" in capsys.readouterr().out
    pending = {n: "later" for n in locations["modalities"]} | locations["pending"]
    (shared / "meaning-locations.json").write_text(json.dumps({"modalities": {}, "pending": pending}), encoding="utf-8")
    assert mb.main(["check", "--source", str(source)]) == 0
    assert capsys.readouterr().out == ""


def test_cli_release_writes_into_dest(tree, tmp_path, capsys):
    dest = tmp_path / "out"
    assert mb.main(["release", "--modality", "biosample", "--source", str(tree), "--dest", str(dest)]) == 0
    assert "schemas/stable/biosample.schema.json" in capsys.readouterr().out
    assert (dest / "schemas" / "stable" / "biosample.schema.json").is_file()
    assert mb.main(["release", "--modality", "nope", "--source", str(tree), "--dest", str(dest)]) == 1


def test_the_meaning_page_documents_every_block_field():
    page = (REPO / "specs" / "meaning.md").read_text(encoding="utf-8")
    link = BLOCK["link"]["items"]["properties"]
    vm = BLOCK["column"]["ValueMappings"]["items"]
    rule = vm["properties"]["Rules"]["items"]
    names = [*BLOCK["column"], *BLOCK["file"], *link, *vm["properties"], *rule["properties"],
             *rule["properties"]["When"]["properties"], "State"]
    assert [n for n in names if f"`{n}`" not in page] == []


# ---- backward compatibility of the five real releases -----------------------------------------------------

META = {"SchemaVersion": "1.0.0", "CreationDate": "2026-11-14"}
LINK = [{"Concept": "prism:anxiety", "Match": "broader", "Higher": "more", "Checked": "2026-11-14", "Status": "reviewed"}]
NEW = {"IsAbout": LINK, "LevelIsAbout": {"1": LINK}, "TermURL": {"snomed": "http://snomed.info/id/1"}}
# one tiny valid document per modality; the "meaning" variant adds the new fields (a hand-written fixture
# because the repository has none for most modalities; environment's real fixture is in test_environment_schema.py)
OLD_DOCS = {
    "biometrics": [{"Technical": {"Type": "t", "FileFormat": "tsv", "Equipment": "e"},
                    "Study": {"BiometricName": "b", "OriginalName": "o", "Description": "d"},
                    "Metadata": META, "weight": {"Description": "w", "Units": "kg", "Levels": {"1": "a"}, "TermURL": "https://x.org/d"}}],
    "biosample": [{"Technical": {"SpecimenType": "saliva"}, "Study": {"BiosampleName": "cortisol"}, "Metadata": META,
                   "cort": {"Description": "c", "Units": "nmol/L", "Levels": {"1": "a"}}}],
    "environment": [{"Technical": {"Source": "open-meteo"}, "Study": {"EnvironmentName": "weather"}, "Metadata": META,
                     "temp": {"Term": "prism:air-temperature", "Window": {"Start": "P3D", "End": "PT0S"}, "Statistic": "max"}}],
    "events": [{"StimulusPresentation": {"SoftwareName": "PsychoPy"}, "trial_type": {"Description": "d", "Levels": {"1": "a"}},
                "onset": {"Description": "o"}, "Metadata": META, "TermURL": "https://x.org/d"}],
    "physio": [{"Technical": {"SamplingFrequency": 100, "Columns": ["ecg"]}, "Metadata": META,
                "Channels": {"ecg": {"Description": "ecg", "Type": "ECG", "Levels": {"1": "a"}}}}],
}
NEW_DOCS = {
    "biometrics": {"Technical": OLD_DOCS["biometrics"][0]["Technical"], "Study": {**OLD_DOCS["biometrics"][0]["Study"], "IsAbout": LINK},
                   "Metadata": META, "weight": {"Description": "w", "Levels": {"1": "a"}, **NEW}},
    "biosample": {"Technical": OLD_DOCS["biosample"][0]["Technical"], "Study": {"BiosampleName": "c", "IsAbout": LINK}, "Metadata": META,
                  "cort": {"Description": "c", "Levels": {"1": "a"}, **NEW}},
    "environment": {"Technical": OLD_DOCS["environment"][0]["Technical"], "Study": {"EnvironmentName": "w", "IsAbout": LINK}, "Metadata": META,
                    "temp": {**OLD_DOCS["environment"][0]["temp"], **NEW}},
    "events": {"StimulusPresentation": {"SoftwareName": "PsychoPy"}, "Metadata": META,
               "trial_type": {"Description": "d", "Levels": {"1": "a"}, **NEW}, "onset": {"Description": "o", "IsAbout": LINK}},
    "physio": {"Technical": OLD_DOCS["physio"][0]["Technical"], "Metadata": META, "Recording": {"IsAbout": LINK},
               "Channels": {"ecg": {"Description": "ecg", "Type": "ECG", "Levels": {"1": "a"}, **NEW}}},
}
STAMPED = sorted(mb.load_locations(SHARED)["modalities"])


def _version(text):
    return tuple(int(n) for n in text.split("."))


def _archived(modality):
    files = sorted((REPO / "schemas" / "archive" / modality).glob("*.schema.json"),
                   key=lambda p: _version(p.name[:-len(".schema.json")]))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


@pytest.mark.parametrize("modality", STAMPED)
def test_every_existing_document_still_validates_after_the_release(modality):
    new = json.loads((REPO / "schemas/stable" / f"{modality}.schema.json").read_text(encoding="utf-8"))
    old = _archived(modality)
    assert old is not None and _version(old["version"]) < _version(new["version"])
    assert _version(old["version"])[0] == _version(new["version"])[0]  # a minor release, never a major
    old_v, new_v = Draft7Validator(old), Draft7Validator(new)
    for doc in OLD_DOCS[modality]:
        assert old_v.is_valid(doc), [e.message for e in old_v.iter_errors(doc)]
        assert new_v.is_valid(doc), [e.message for e in new_v.iter_errors(doc)]
    assert new_v.is_valid(NEW_DOCS[modality]), [e.message for e in new_v.iter_errors(NEW_DOCS[modality])]


def test_the_modality_check_passes_with_survey_pending():
    assert _load("check_modalities").main([]) == 0


@pytest.mark.parametrize("modality", STAMPED)
def test_five_schemas_carry_the_block(modality):
    text = (REPO / "schemas/stable" / f"{modality}.schema.json").read_text(encoding="utf-8")
    assert missing(text, modality, BLOCK, mb.load_locations(SHARED)) == []
