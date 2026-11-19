"""The shipped survey mappings: DASS (item -> subscale) and the demo (ValueRules only)."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_mappings  # noqa: E402

# Items of each subscale, as on the DASS authors' scoring template
# (https://www2.psy.unsw.edu.au/dass/Download%20files/Dass_template.pdf): D depression, A anxiety, S stress.
ITEMS_21 = {"D": (3, 5, 10, 13, 16, 17, 21), "A": (2, 4, 7, 9, 15, 19, 20), "S": (1, 6, 8, 11, 12, 14, 18)}
ITEMS_42 = {"D": (3, 5, 10, 13, 16, 17, 21, 24, 26, 31, 34, 37, 38, 42),
            "A": (2, 4, 7, 9, 15, 19, 20, 23, 25, 28, 30, 36, 40, 41),
            "S": (1, 6, 8, 11, 12, 14, 18, 22, 27, 29, 32, 33, 35, 39)}
SNOMED = {  # looked up on the HL7 terminology server (SNOMED International edition 2026-07-01)
    "D": "https://snomed.info/id/416954004",  # Depression anxiety stress scales depression score
    "A": "https://snomed.info/id/416619008",  # ... anxiety score
    "S": "https://snomed.info/id/416767005",  # ... stress score
}


def load(modality: str, family: str) -> dict:
    return json.loads((ROOT / "mappings" / modality / f"{family}.json").read_text(encoding="utf-8"))


def test_the_repository_mappings_pass_the_check():
    assert check_mappings.check(ROOT) == []


def _expected(family: str, items: dict[str, tuple[int, ...]]) -> dict[str, str]:
    return {f"prism:{family}.{family}{n:02d}": SNOMED[scale] for scale, numbers in items.items() for n in numbers}


def test_dass21_every_item_is_linked_to_its_subscale_score():
    mapping = load("survey", "dass21")
    assert {k: v["Measures"][0]["URL"] for k, v in mapping.items()} == _expected("dass21", ITEMS_21)


def test_dass42_every_item_is_linked_to_its_subscale_score():
    mapping = load("survey", "dass")
    assert {k: v["Measures"][0]["URL"] for k, v in mapping.items()} == _expected("dass", ITEMS_42)


def test_dass_links_say_how_far_they_can_be_trusted():
    for family in ("dass", "dass21"):
        for key, entry in load("survey", family).items():
            (link,) = entry["Measures"]
            assert link["Match"] == "related", key  # an item contributes to a score, it is not the same thing
            assert link["Higher"] == "more", key
            assert link["Status"] in ("unreviewed", "reviewed"), key
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", link["Checked"]), key
            assert "scoring template" in link["Source"], key


def test_demo_mapping_is_marked_as_a_demonstration():
    mapping = load("survey", "demo")
    assert set(mapping) == {"prism:demo.score-total"}
    (rules,) = mapping["prism:demo.score-total"]["ValueRules"]
    assert "emonstration" in rules["Source"]
    # no gap and no overlap: one threshold, high at or above it, low below it
    (high,), (low,) = ([r for r in rules["Rules"] if r["State"] == s] for s in ("high", "low"))
    assert (high["When"]["Op"], low["When"]["Op"]) == (">=", "<")
    assert high["When"]["Value"] == low["When"]["Value"]
