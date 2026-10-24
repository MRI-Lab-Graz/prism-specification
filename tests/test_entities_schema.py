"""The entity rules file says which entities a modality's file names must carry."""

import json
import re
from pathlib import Path

ENTITIES = json.loads((Path(__file__).resolve().parents[1] / "schemas/stable/entities.schema.json").read_text())


def test_a_survey_file_name_must_carry_a_task():
    """A survey without a task cannot be matched to its template or sidecar."""
    task = ENTITIES["modalities"]["survey"]["requiredEntityValues"]["task"]
    assert all(re.fullmatch(task["pattern"], label) for label in ("brs", "wellbeing-multi", "phq9"))
    assert not re.fullmatch(task["pattern"], "")


def test_a_survey_file_name_may_carry_the_variant_and_run_entities():
    """Multi-version templates write ..._task-<t>_acq-<variant>[_run-<n>]_survey.tsv."""
    optional = ENTITIES["modalities"]["survey"]["optionalEntityValues"]
    assert {"acq", "run"} <= set(optional)
    assert re.fullmatch(optional["acq"]["pattern"], "10-likert")
