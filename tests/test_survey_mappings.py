"""The shipped survey mappings: DASS (item -> subscale) and the demo (ValueRules only)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_mappings  # noqa: E402

# The DASS authors' scoring template (https://www2.psy.unsw.edu.au/dass/Download%20files/Dass_template.pdf),
# read top to bottom: D depression, A anxiety, S stress, one letter per item of the 21-item form.
# For the 42-item form the same template is applied to both sides of the sheet (items 1-21, then 22-42).
TEMPLATE_21 = "SADADSASADSSDSADDSAAD"
SNOMED = {  # looked up on the HL7 terminology server (SNOMED International edition 2026-07-01)
    "D": "https://snomed.info/id/416954004",  # Depression anxiety stress scales depression score
    "A": "https://snomed.info/id/416619008",  # ... anxiety score
    "S": "https://snomed.info/id/416767005",  # ... stress score
}


def load(modality: str, family: str) -> dict:
    return json.loads((ROOT / "mappings" / modality / f"{family}.json").read_text(encoding="utf-8"))


def test_the_repository_mappings_pass_the_check():
    assert check_mappings.check(ROOT) == []


def _expected(family: str, template: str, keys: list[str]) -> dict[str, str]:
    return {f"prism:{family}.{key}": SNOMED[letter] for key, letter in zip(keys, template)}


def test_dass21_every_item_is_linked_to_its_subscale_score():
    keys = [f"dass21{n:02d}" for n in range(1, 22)]
    mapping = load("survey", "dass21")
    assert {k: v["Measures"][0]["URL"] for k, v in mapping.items()} == _expected("dass21", TEMPLATE_21, keys)


def test_dass42_every_item_is_linked_to_its_subscale_score():
    keys = [f"dass{n:02d}" for n in range(1, 43)]
    mapping = load("survey", "dass")
    assert {k: v["Measures"][0]["URL"] for k, v in mapping.items()} == _expected("dass", TEMPLATE_21 * 2, keys)


def test_dass_links_say_how_far_they_can_be_trusted():
    for family in ("dass", "dass21"):
        for key, entry in load("survey", family).items():
            (link,) = entry["Measures"]
            assert link["Match"] == "related", key  # an item contributes to a score, it is not the same thing
            assert link["Higher"] == "more", key
            assert link["Status"] == "unreviewed", key  # only a maintainer sets reviewed
            assert link["Checked"] == "2026-11-19", key
            assert "scoring template" in link["Source"], key


def test_demo_mapping_is_marked_as_a_demonstration():
    mapping = load("survey", "demo")
    assert set(mapping) == {"prism:demo.score-total"}
    (rules,) = mapping["prism:demo.score-total"]["ValueRules"]
    assert "emonstration" in rules["Source"]
    assert {r["State"] for r in rules["Rules"]} == {"high", "low"}
