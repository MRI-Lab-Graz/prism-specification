"""scripts/fingerprint.py: normalise an item text and hash it (specs/instrument-ids.md)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fingerprint  # noqa: E402

SAME = [
    "I felt stressed.",
    "  i FELT   stressed ",
    "I felt\nstressed!",
    "“I felt stressed”",
    "I fel\u00adt stres\u200bsed",  # soft hyphen and zero-width space (extraction artefacts)
]


def test_formatting_differences_give_the_same_fingerprint():
    assert len({fingerprint.fingerprint(t) for t in SAME}) == 1


def test_umlauts_compose_and_case_fold():
    assert fingerprint.fingerprint("Ich fühle mich WOHL") == fingerprint.fingerprint("ich fühle mich wohl")
    assert fingerprint.fingerprint("Straße") == fingerprint.fingerprint("STRASSE")


@pytest.mark.parametrize("other", ["I felt stress", "I did not feel stressed", ""])
def test_a_different_text_gives_a_different_fingerprint(other):
    assert fingerprint.fingerprint(other) != fingerprint.fingerprint(SAME[0])


def test_fingerprint_has_the_schema_form():
    import re
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint.fingerprint("x"))


def test_a_known_value_is_stable():
    # fixed so a change of the normalisation rules (which would invalidate every published fingerprint) is noticed
    assert fingerprint.fingerprint("I felt stressed.") == "sha256:d7820219a8da0926b8d79c459f6ed6af4c3eeb797c9334f119f52bbae84fe2a8"


def template(tmp_path, data):
    f = tmp_path / "survey-x.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return f


def test_template_items_are_fingerprinted_per_language(tmp_path):
    f = template(tmp_path, {
        "Technical": {"Language": "de"}, "I18n": {"Languages": ["de", "en"]}, "Study": {},
        "X01": {"Description": {"de": "Ich bin müde.", "en": "I am tired."}},
        "X02": {"Description": "Noch eine Frage", "Levels": {"0": "Nie"}},
        "X03": {"AliasOf": "X01"},
    })
    out = fingerprint.template_fingerprints(json.loads(f.read_text(encoding="utf-8")))
    assert set(out) == {"X01", "X02"}  # alias items have no text of their own
    assert set(out["X01"]) == {"de", "en"}
    assert out["X01"]["en"] == fingerprint.fingerprint("I am tired")
    assert out["X02"] == {"de": fingerprint.fingerprint("Noch eine Frage")}  # plain string: Technical.Language


def test_a_stub_has_nothing_to_fingerprint():
    assert fingerprint.template_fingerprints({"Study": {"ItemTextsIncluded": False}, "X01": {"Description": None}}) == {}


def test_command_line_prints_json(tmp_path):
    f = template(tmp_path, {"Technical": {"Language": "en"}, "Study": {}, "X01": {"Description": "Hello"}})
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "fingerprint.py"), str(f)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"X01": {"en": fingerprint.fingerprint("Hello")}}
