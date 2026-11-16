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

# demo and kse are written here; dass and dass21 carry a Range corrected to their template (0-3 items)
# Open Test Archive batch 1: recipes written here from the archive pages (templates ship in library/)
ARCHIVE_RECIPES = ["csip", "dass-de", "ebi-am", "ecr-g-10", "efk", "icg-d", "lshs-g", "pdi", "pted-skala", "stars-d", "tsi-ger-13", "tsi-ger-4"]
WRITTEN_HERE = {"recipe-demo.json", "recipe-kse.json", "recipe-dass.json", "recipe-dass21.json", *(f"recipe-{t}.json" for t in ARCHIVE_RECIPES)}

need_source = pytest.mark.skipif(not SRC_RECIPES.is_dir(), reason=f"source copy {SRC_RECIPES} is missing")


def _en(value):
    return value.get("en") if isinstance(value, dict) else value


def _shipped_tasks() -> set:
    """Task names of the templates that ship in library/survey/ (their licence evidence is checked by check_library)."""
    return {(json.loads(p.read_text(encoding="utf-8")).get("Study") or {}).get("TaskName") for p in (ROOT / "library" / "survey").glob("survey-*.json")}


def _invert_ok(invert) -> bool:
    return isinstance(invert, dict) and isinstance(invert.get("Items"), list) and bool(invert["Items"])


def is_boilerplate(recipe: dict, shipped=None) -> bool:
    """Boilerplate only; a recipe whose template ships here may also carry Invert transforms and a score Note."""
    shipped = _shipped_tasks() if shipped is None else shipped
    task = (recipe.get("Survey") or {}).get("TaskName")
    if task is not None and not isinstance(task, str):
        return False
    own = task in shipped
    usage = recipe.get("Usage") or {}
    scoring = _en(usage.get("ScoringGuidelines"))
    interp = _en(usage.get("InterpretationGuidelines"))
    if scoring is not None and not str(scoring).startswith("Calculate total score by summing all items"):
        return False
    if interp is not None and "Refer to original publication" not in str(interp):
        return False
    if set(usage) - {"ScoringGuidelines", "InterpretationGuidelines"}:
        return False
    if any(k in recipe for k in ("References", "VersionedScores")):
        return False
    transforms = recipe.get("Transforms")
    if "Transforms" in recipe and not (own and isinstance(transforms, dict) and set(transforms) == {"Invert"} and _invert_ok(transforms["Invert"])):
        return False
    for score in recipe.get("Scores") or []:
        if ("Note" in score and not own) or not isinstance(score.get("Description", ""), str):
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
    assert not is_boilerplate({"Scores": [{"Note": "n"}]}, shipped=set())


def test_transforms_and_note_only_when_the_template_ships():
    invert = {"Invert": {"Items": ["DEMO06"], "Scale": {"min": 0, "max": 4}}}
    base = {"Survey": {"TaskName": "demo"}, "Scores": [{"Description": "x"}]}
    shipped = {"demo", "kse"}
    assert is_boilerplate({**base, "Transforms": invert}, shipped)
    assert is_boilerplate({**base, "Scores": [{"Description": "x", "Note": "n"}]}, shipped)
    other = {**base, "Survey": {"TaskName": "other"}}
    assert not is_boilerplate({**other, "Transforms": invert}, shipped)  # no shipped template
    assert not is_boilerplate({**other, "Scores": [{"Description": "x", "Note": "n"}]}, shipped)
    assert not is_boilerplate({**base, "Transforms": {**invert, "Derived": []}}, shipped)
    assert not is_boilerplate({**base, "Transforms": {}}, shipped)
    assert not is_boilerplate({**base, "Survey": {}, "Transforms": invert}, shipped)
    assert is_boilerplate(json.loads((ROOT / "recipes/survey/recipe-kse.json").read_text(encoding="utf-8")))


def test_is_boilerplate_does_not_raise_on_malformed_recipes():
    assert not is_boilerplate({"Survey": {"TaskName": ["kse"]}, "Scores": []}, {"kse"})
    assert not is_boilerplate({"Survey": {"TaskName": {"a": 1}}, "Scores": []}, {"kse"})
    assert not is_boilerplate({"Survey": {"TaskName": "kse"}, "Transforms": {"Invert": []}, "Scores": []}, {"kse"})
    assert not is_boilerplate({"Survey": {"TaskName": "kse"}, "Transforms": {"Invert": {"Items": [], "Scale": {"min": 1, "max": 4}}}, "Scores": []}, {"kse"})


def test_kse_template_is_the_archive_copy():
    src = Path("/Volumes/Evo/work/prism-local-library/batch1/library/survey/survey-kse.json")
    if src.is_file():
        assert (ROOT / "library/survey/survey-kse.json").read_bytes() == src.read_bytes()


def _template_and_recipe_pairs():
    for p in _shipped():
        recipe = json.loads(p.read_text(encoding="utf-8"))
        ref = ROOT / "library" / "survey" / recipe["Survey"]["Reference"]
        if recipe["Survey"]["TaskName"] in _shipped_tasks():
            yield p.name, recipe, ref


def test_recipes_of_shipped_templates_agree_with_their_template():
    pairs = list(_template_and_recipe_pairs())
    assert {n for n, _, _ in pairs} >= {"recipe-demo.json", "recipe-dass.json", "recipe-dass21.json", "recipe-kse.json"}
    for name, recipe, ref in pairs:
        assert ref.is_file(), name
        template = json.loads(ref.read_text(encoding="utf-8"))
        assert (template.get("Study") or {}).get("TaskName") == recipe["Survey"]["TaskName"], name
        for score in recipe["Scores"]:
            for key in score["Items"]:
                assert isinstance(template.get(key), dict), (name, key)
            if score["Method"] == "sum":
                lo = sum(template[k]["MinValue"] for k in score["Items"])
                hi = sum(template[k]["MaxValue"] for k in score["Items"])
                assert score["Range"] == {"min": lo, "max": hi}, (name, score["Name"])
        invert = (recipe.get("Transforms") or {}).get("Invert")
        if invert:
            scored = {k for s in recipe["Scores"] for k in s["Items"]}
            assert set(invert["Items"]) <= scored, name
            for key in invert["Items"]:
                assert invert["Scale"] == {"min": template[key]["MinValue"], "max": template[key]["MaxValue"]}, (name, key)


def test_kse_recipe():
    recipe = json.loads((ROOT / "recipes/survey/recipe-kse.json").read_text(encoding="utf-8"))
    assert recipe["Survey"] == {"Name": "KSE", "Reference": "survey-kse.json", "TaskName": "kse"}
    positive = ["KSE01", "KSE04", "KSE05", "KSE06", "KSE09", "KSE10", "KSE15", "KSE16", "KSE19", "KSE20"]
    assert recipe["Transforms"] == {"Invert": {"Items": positive, "Scale": {"min": 1, "max": 4}}}
    (total,) = recipe["Scores"]
    assert total["Items"] == [f"KSE{i:02d}" for i in range(1, 21)] and total["Method"] == "sum"
    assert total["Range"] == {"min": 20, "max": 80} and total["HigherMeans"] == "higher loneliness"
    assert "should be confirmed with the authors" in total["Note"]
    assert "Usage" not in recipe and "Psychometrics" not in recipe


def test_demo_recipe_scores_computed():
    """No scoring code lives in this repo: the recipe is checked structurally and its arithmetic worked by hand."""
    recipe = json.loads((ROOT / "recipes" / "survey" / "recipe-demo.json").read_text(encoding="utf-8"))
    assert recipe["Transforms"]["Invert"] == {"Items": ["DEMO06"], "Scale": {"min": 0, "max": 4}}
    scores = {s["Name"]: s for s in recipe["Scores"]}
    assert set(scores) == {"Total", "Routine"}
    assert scores["Total"]["Items"] == [f"DEMO0{i}" for i in range(1, 9)] and scores["Total"]["Method"] == "sum"
    assert scores["Routine"]["Items"] == [f"DEMO0{i}" for i in range(1, 5)]
    assert scores["Total"]["Range"] == {"min": 0, "max": 32} and scores["Routine"]["Range"] == {"min": 0, "max": 16}
    resp = {f"DEMO0{i}": v for i, v in enumerate([1, 2, 3, 4, 0, 1, 2, 3], 1)}
    lo, hi = recipe["Transforms"]["Invert"]["Scale"]["min"], recipe["Transforms"]["Invert"]["Scale"]["max"]
    for k in recipe["Transforms"]["Invert"]["Items"]:
        resp[k] = lo + hi - resp[k]
    assert sum(resp[k] for k in scores["Total"]["Items"]) == 1 + 2 + 3 + 4 + 0 + 3 + 2 + 3
    assert sum(resp[k] for k in scores["Routine"]["Items"]) == 10


@need_source
def test_shipped_recipes_are_exactly_the_passing_ones():
    src = _source_recipes()
    passing = {n for n, r in src.items() if is_boilerplate(r)}
    assert len(passing) == 100
    assert set(src) - passing == HELD
    shipped = {p.name for p in _shipped()} - {n for n in WRITTEN_HERE if n not in ("recipe-dass.json", "recipe-dass21.json")}  # written here, not copied
    assert len(shipped) == 100
    assert shipped == passing == set(src) - HELD
    for p in _shipped():
        if p.name not in WRITTEN_HERE:
            assert p.read_bytes() == (SRC_RECIPES / p.name).read_bytes()
    assert not [n for n in HELD if list((ROOT / "recipes").rglob(n))]


@need_source
def test_boilerplate_fails_for_each_held_recipe():
    src = _source_recipes()
    for name in HELD:
        assert not is_boilerplate(src[name]), name


def test_shipped_recipes_pass_boilerplate_test():
    assert len(_shipped()) == 114
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
    assert len(ids) == 1478 + 1 + 8 + 2 + 25 + 1 + 20 + 1 + 686 + 52  # + Open Test Archive batch 1 (templates + recipe scores)
    assert all(ID_RE.match(i) for i in ids)
    assert len(set(ids)) == len(ids)
    if SRC_IDS.is_file():  # the released list only grew by the IDs of the instruments written here (demo, SBI-d, archive batches)
        src = SRC_IDS.read_text(encoding="utf-8").splitlines()
        new_heads = {f"prism:{t}" for t in _shipped_tasks()} - {i.split(".")[0] for i in src}
        assert [i for i in ids if i.split(".")[0] not in new_heads] == src
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


def test_recipe_schema_1_0_0_is_the_studio_file():
    path = ROOT / "schemas" / "archive" / "recipe.survey" / "1.0.0.schema.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SCHEMA_SHA256


def test_shipped_recipes_validate_against_the_schema():
    validator = Draft7Validator(json.loads((ROOT / "schemas/stable/recipe.survey.schema.json").read_text(encoding="utf-8")))
    assert len(_shipped()) == 114
    for p in _shipped():
        errors = list(validator.iter_errors(json.loads(p.read_text(encoding="utf-8"))))
        assert not errors, (p.name, errors[0].message)


def test_recipe_schema_is_1_0_1_and_1_0_0_is_archived():
    stable = json.loads((ROOT / "schemas/stable/recipe.survey.schema.json").read_text(encoding="utf-8"))
    assert stable["version"] == "1.0.1"
    assert stable["$id"].endswith("/v1.0.1")
    archived = ROOT / "schemas/archive/recipe.survey/1.0.0.schema.json"
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == SCHEMA_SHA256


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
    assert "recipe schema (`recipe.survey.schema.json`) is versioned and archived like the modality schemas" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_generate_schema_reference_knows_recipe_survey():
    spec = __import__("importlib.util").util.spec_from_file_location("gsr", ROOT / "scripts/generate_schema_reference.py")
    mod = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "recipe.survey" in mod.OTHER_DOCS


def test_archive_batch1_recipes_say_what_they_know_about_reverse_coding():
    """A reverse-coded item list is only written when the archive text names the items; otherwise the recipe says so."""
    for task in ARCHIVE_RECIPES:
        recipe = json.loads((ROOT / f"recipes/survey/recipe-{task}.json").read_text(encoding="utf-8"))
        assert recipe["Survey"]["TaskName"] == task
        if "Transforms" not in recipe:
            notes = " ".join(s.get("Note", "") for s in recipe["Scores"])
            assert "reverse" in notes and "archive documentation" in notes, task
    for task in ("cpaq-d", "esrd-scl-tm", "febo", "bfas-g", "pmerq"):  # held back: decision or scoring data missing
        assert not (ROOT / f"recipes/survey/recipe-{task}.json").exists(), task
