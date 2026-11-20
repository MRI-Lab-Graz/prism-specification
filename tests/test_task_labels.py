"""A task label is letters and digits only (BIDS): no separator can be part of it.

`_` splits the file-name parts, `-` joins a key to its value and `.` starts the extension. The readable
name (ECR-G-10) lives in Study.ShortName, never in the task label.
"""

import json
import re
from pathlib import Path

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parent.parent
LABEL = re.compile(r"[a-z0-9]+")  # IDs are lower case, and they are built from the task label
SCHEMA = json.loads((ROOT / "schemas" / "stable" / "survey.schema.json").read_text(encoding="utf-8"))


def test_the_survey_schema_rejects_a_hyphen_in_the_task_name():
    task_name = Draft7Validator(SCHEMA["properties"]["Study"]["properties"]["TaskName"])
    assert task_name.is_valid("ecrg10")
    assert not task_name.is_valid("ecr-g-10")


def test_every_library_template_has_an_alphanumeric_task_label():
    for path in sorted((ROOT / "library" / "survey").glob("survey-*.json")):
        task = json.loads(path.read_text(encoding="utf-8"))["Study"]["TaskName"]
        assert LABEL.fullmatch(task), f"{path.name}: TaskName {task!r}"
        assert path.name == f"survey-{task}.json"


def test_every_recipe_points_at_an_alphanumeric_task():
    for path in sorted((ROOT / "recipes" / "survey").glob("recipe-*.json")):
        survey = json.loads(path.read_text(encoding="utf-8")).get("Survey") or {}
        task = survey.get("TaskName")
        if task is not None:
            assert LABEL.fullmatch(task), f"{path.name}: TaskName {task!r}"
            assert survey.get("Reference") == f"survey-{task}.json", path.name


def test_every_survey_id_has_an_alphanumeric_task_part():
    for line in (ROOT / "ids" / "survey-ids.txt").read_text(encoding="utf-8").splitlines():
        task = line.removeprefix("prism:").split(".")[0]
        assert LABEL.fullmatch(task), line
