"""terms/biometrics: shared measures; the columns of the PRISM fitness template are their aliases."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS = ROOT / "terms" / "biometrics"

FITNESS_COLUMNS = {  # official/library/biometrics/biometrics-fitness.json in PRISM Studio
    "resting_hr": "resting-heart-rate", "step_test_hr": "step-test-heart-rate",
    "grip_strength_left": "grip-strength.left", "grip_strength_right": "grip-strength.right",
    "plank_duration": "plank-duration", "sit_and_reach": "sit-and-reach",
    "vo2_max_estimated": "vo2max-estimated", "bmi": "bmi",
}


def _terms():
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in TERMS.glob("*.json")}


def test_every_fitness_column_names_its_term():
    terms = _terms()
    for column, stem in FITNESS_COLUMNS.items():
        assert terms[stem]["TermID"] == f"prism:{stem}"
        assert column == stem or column in terms[stem].get("Aliases", []), column
    assert set(terms) == set(FITNESS_COLUMNS.values()) | {"grip-strength"}


def test_biometrics_declares_terms_and_its_columns_may_name_one():
    entities = json.loads((ROOT / "schemas" / "stable" / "entities.schema.json").read_text(encoding="utf-8"))
    assert entities["modalities"]["biometrics"]["terms"] == {"nonTermColumns": ["subject_id", "session_id"]}
    schema = json.loads((ROOT / "schemas" / "stable" / "biometrics.schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"]["properties"]["Term"]["type"] == "string"
