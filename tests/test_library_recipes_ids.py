"""library/, recipes/, ids/ and the recipe schema (Task 2 of the mappings-layer plan)."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path("/Volumes/Evo/work/prism-local-library/official")
SRC_RECIPES = SOURCE / "recipe" / "survey"
SRC_IDS = SOURCE / "library" / "survey" / "term-ids.txt"
HELD = {"recipe-psqi.json", "recipe-tipi.json", "recipe-wellbeing.json", "recipe-wellbeing-multi.json"}
SCHEMA_SHA256 = "6875a1da1a84b495ab866abdfdabd35c8c1602eef8636149290c12a54b1661e7"
ID_RE = re.compile(r"^prism:[a-z][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*)*$")

need_source = pytest.mark.skipif(not SRC_RECIPES.is_dir(), reason=f"source copy {SRC_RECIPES} is missing")


def _en(value):
    return value.get("en") if isinstance(value, dict) else value


def is_boilerplate(recipe: dict) -> bool:
    usage = recipe.get("Usage") or {}
    scoring = _en(usage.get("ScoringGuidelines"))
    interp = _en(usage.get("InterpretationGuidelines"))
    if scoring is not None and not str(scoring).startswith("Calculate total score by summing all items"):
        return False
    if interp is not None and "Refer to original publication" not in str(interp):
        return False
    if set(usage) - {"ScoringGuidelines", "InterpretationGuidelines"}:
        return False
    if any(recipe.get(k) for k in ("References", "Transforms", "VersionedScores")) or any(
        k in recipe for k in ("References", "Transforms", "VersionedScores")
    ):
        return False
    for score in recipe.get("Scores") or []:
        if "Note" in score or not isinstance(score.get("Description", ""), str):
            return False
    return True


def _source_recipes():
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(SRC_RECIPES.glob("recipe-*.json"))}


def _shipped():
    return sorted((ROOT / "recipes" / "survey").glob("recipe-*.json"))


def test_license_scope():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    head = text.split("PART 1", 1)[0]
    for folder in ("schemas/", "terms/", "specs/", "recipes/", "ids/", "mappings/"):
        assert folder in head
    assert re.search(r"(exclud|except|not cover)[^.]*library/", head, re.I | re.S)
    assert "library/NOTICE.md" in head


def test_notice():
    text = (ROOT / "library" / "NOTICE.md").read_text(encoding="utf-8")
    assert "<contact address to be set by the maintainers>" in text
    assert "if you hold rights to an instrument and want it removed, write to" in text.lower()
    for phrase in ("own terms", "no rights", "verified", "source URL", "retrieval date", "CC BY 4.0"):
        assert phrase.lower() in text.lower(), phrase
    assert (ROOT / "library" / "survey" / ".gitkeep").is_file()


def test_boilerplate_function_on_samples():
    ok = {"Usage": {"ScoringGuidelines": {"en": "Calculate total score by summing all items."}}, "Scores": [{"Description": "x"}]}
    assert is_boilerplate(ok)
    assert not is_boilerplate({**ok, "References": []})
    assert not is_boilerplate({"Usage": {"Other": 1}})
    assert not is_boilerplate({"Scores": [{"Note": "n"}]})


@need_source
def test_shipped_recipes_are_exactly_the_passing_ones():
    src = _source_recipes()
    passing = {n for n, r in src.items() if is_boilerplate(r)}
    assert len(passing) == 100
    assert set(src) - passing == HELD
    shipped = {p.name for p in _shipped()}
    assert len(shipped) == 100
    assert shipped == passing == set(src) - HELD
    for p in _shipped():
        assert p.read_bytes() == (SRC_RECIPES / p.name).read_bytes()
    assert not any((ROOT / "recipes").rglob(n) for n in HELD)


@need_source
def test_boilerplate_fails_for_each_held_recipe():
    src = _source_recipes()
    for name in HELD:
        assert not is_boilerplate(src[name]), name


def test_shipped_recipes_pass_boilerplate_test():
    assert len(_shipped()) == 100
    for p in _shipped():
        assert is_boilerplate(json.loads(p.read_text(encoding="utf-8"))), p.name


def test_held_list_names_every_held_recipe():
    text = (ROOT / "recipes" / "HELD.md").read_text(encoding="utf-8")
    for name in HELD:
        assert name in text


def _ids():
    return (ROOT / "ids" / "survey-ids.txt").read_text(encoding="utf-8").splitlines()


def test_ids_list():
    ids = _ids()
    assert len(ids) == 1478
    assert all(ID_RE.match(i) for i in ids)
    assert len(set(ids)) == len(ids)
    if SRC_IDS.is_file():
        assert (ROOT / "ids" / "survey-ids.txt").read_bytes() == SRC_IDS.read_bytes()
    readme = (ROOT / "ids" / "README.md").read_text(encoding="utf-8")
    assert "frozen" in readme.lower()


def test_recipes_agree_with_ids():
    ids = set(_ids())
    unresolved = []
    for p in _shipped():
        recipe = json.loads(p.read_text(encoding="utf-8"))
        task = recipe["Survey"]["TaskName"]
        if f"prism:{task}" not in ids:
            unresolved.append(f"{p.name}: prism:{task}")
        for score in recipe.get("Scores") or []:
            items = score.get("Items") or {}
            keys = items if isinstance(items, dict) else items
            for key in keys:
                iid = f"prism:{task}.{str(key).lower().replace('_', '-')}"
                if iid not in ids:
                    unresolved.append(f"{p.name}: {iid}")
    assert not unresolved, unresolved


def test_recipe_schema_is_the_studio_file():
    path = ROOT / "schemas" / "stable" / "recipe.survey.schema.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SCHEMA_SHA256


def test_shipped_recipes_validate_against_the_schema():
    validator = Draft7Validator(json.loads((ROOT / "schemas/stable/recipe.survey.schema.json").read_text(encoding="utf-8")))
    assert len(_shipped()) == 100
    for p in _shipped():
        errors = list(validator.iter_errors(json.loads(p.read_text(encoding="utf-8"))))
        assert not errors, (p.name, errors[0].message)


def test_check_schema_versions_governs_recipe_survey():
    import importlib.util

    spec = importlib.util.spec_from_file_location("csv_", ROOT / "scripts" / "check_schema_versions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stable = "schemas/stable/recipe.survey.schema.json"
    arch = "schemas/archive/recipe.survey/1.0.0.schema.json"
    doc = lambda v, x=0: json.dumps({"version": v, "x": x})

    def run(changes, base, head):
        return mod.check(changes, base.get, head.get, lambda p: p in head, mod.governed({"survey"}))

    assert any("bump" in e for e in run([("M", stable)], {stable: doc("1.0.0")}, {stable: doc("1.0.0", 1)}))
    assert any("archive" in e for e in run([("M", stable)], {stable: doc("1.0.0")}, {stable: doc("1.0.1")}))
    assert run([("M", stable), ("A", arch)], {stable: doc("1.0.0")}, {stable: doc("1.0.1", 1), arch: doc("1.0.0")}) == []


def test_codeowners_and_contributing():
    assert "/schemas/stable/recipe.survey.schema.json" in (ROOT / "CODEOWNERS").read_text(encoding="utf-8")
    assert "recipe schema is versioned and archived like the modality schemas" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_generate_schema_reference_knows_recipe_survey():
    spec = __import__("importlib.util").util.spec_from_file_location("gsr", ROOT / "scripts/generate_schema_reference.py")
    mod = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "recipe.survey" in mod.OTHER_DOCS
