"""scripts/check_library.py and the shipped templates (dass, dass21, demo)."""

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_library  # noqa: E402

LIB = ROOT / "library" / "survey"
GOOD = {
    "Technical": {"StimulusType": "Questionnaire", "FileFormat": "tsv", "Language": "en"},
    "I18n": {"Languages": ["en"]},
    "Study": {
        "TaskName": "x",
        "OriginalName": {"en": "X"},
        "License": 'The rights holder says: "Free to copy."',
        "Source": "https://example.org/x",
        "LicenseChecked": "2026-11-14",
        "LicenseTerms": ["Do not sell."],
        "LicenseLanguages": ["en"],
        "Authors": ["Doe, J."],
        "Year": 2020,
        "Citation": "Doe, J. (2020). X.",
    },
    "X01": {"Description": {"en": "Item"}, "Levels": {"0": {"en": "No"}}},
}


def problems(tmp_path, mutate):
    data = copy.deepcopy(GOOD)
    mutate(data)
    (tmp_path / "library" / "survey").mkdir(parents=True, exist_ok=True)
    (tmp_path / "library" / "survey" / "survey-x.json").write_text(json.dumps(data), encoding="utf-8")
    return check_library.check(tmp_path)


def test_good_template_passes(tmp_path):
    assert problems(tmp_path, lambda d: None) == []


HASH = "sha256:" + "a" * 64


def make_stub(d):
    d["Study"]["ItemTextsIncluded"] = False
    d["X01"] = {"Description": None, "Levels": {"0": None}, "Fingerprint": {"en": HASH}}


def test_stub_passes(tmp_path):
    assert problems(tmp_path, make_stub) == []


def test_stub_with_item_text_is_reported(tmp_path):
    def m(d):
        make_stub(d)
        d["X01"]["Description"] = {"en": "Item"}
    assert any("X01" in p and "stub" in p for p in problems(tmp_path, m))


def test_stub_level_label_is_reported(tmp_path):
    def m(d):
        make_stub(d)
        d["X01"]["Levels"]["0"] = {"en": "No"}
    assert any("X01" in p and "stub" in p for p in problems(tmp_path, m))


def test_stub_item_without_fingerprint_is_reported(tmp_path):
    def m(d):
        make_stub(d)
        del d["X01"]["Fingerprint"]
    assert any("X01" in p and "Fingerprint" in p for p in problems(tmp_path, m))


def test_normal_template_with_null_text_is_reported(tmp_path):
    assert any("X01" in p for p in problems(tmp_path, lambda d: d["X01"].update(Description=None)))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["Study"].update(License="Public domain, no quote."),  # a
        lambda d: d["Study"].update(Source="www.example.org"),  # b
        lambda d: d["Study"].update(LicenseChecked="14.11.2026"),  # c
        lambda d: d["Study"].update(LicenseTerms="Do not sell."),  # d
        lambda d: d["Study"].update(LicenseTerms=[]),  # d
        lambda d: d["X01"]["Levels"]["0"].update(de="Nein"),  # e
        lambda d: d["Study"]["OriginalName"].update(de="X"),  # e
        lambda d: d["Study"].pop("LicenseLanguages"),  # e-missing
        lambda d: d["Study"].update(LicenseLanguages=[]),  # e-empty
        lambda d: d["Study"].update(LicenseLanguages=["EN"]),  # e-bad code
        lambda d: d["Study"].update(LicenseLanguages="en"),  # e-not a list
        lambda d: d["Technical"].update(Language="de"),  # e-technical
        lambda d: d["I18n"].update(Languages=["en", "de"]),  # e-i18n
        lambda d: d["Study"].update(License={"en": 'He says: "Free to copy."', "de": "x"}),  # e-license dict
        lambda d: d["Study"].update(ItemCount=1),  # f
        lambda d: d["Study"].update(Subscales={}),  # f
        lambda d: d["X01"].update(Reversed=False),  # f
        lambda d: d["Study"].update(Authors=[]),  # g
        lambda d: d["Study"].update(Year=None),  # g
        lambda d: d["Study"].update(Year="1995"),  # g
        lambda d: d["Study"].update(Citation="Official webpage"),  # g
        lambda d: d["Study"].pop("Citation"),  # g
    ],
    ids=["a", "b", "c", "d-str", "d-empty", "e-levels", "e-name", "e-missing", "e-empty", "e-badcode",
         "e-notlist", "e-technical", "e-i18n", "e-license", "f-itemcount", "f-subscales", "f-reversed",
         "g-authors", "g-year", "g-year-str", "g-placeholder", "g-citation"],
)
def test_each_rule_refuses_and_names_the_file(tmp_path, mutate):
    out = problems(tmp_path, mutate)
    assert out and all("survey-x.json" in line for line in out)


def test_refusal_names_the_language(tmp_path):
    out = problems(tmp_path, lambda d: d["X01"]["Levels"]["0"].update(de="Nein"))
    assert any("'de'" in line and "survey-x.json" in line for line in out)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(Extra=[{"Description": {"de": "x"}}]),
        lambda d: d["X01"].update(Description=[{"de": "x"}]),
        lambda d: d["X01"].update(Levels=[{"de": "x"}]),
        lambda d: d["X01"]["Levels"].update({"1": [{"de": "x"}]}),
        lambda d: d["Study"].update(RecallPeriod={"en": "week", "de": "Woche"}),
        lambda d: d["Study"].update(Construct={"en": "a", "de": "b"}),
        lambda d: d["X01"].update(Unit={"en": "s", "de": "s"}),
    ],
    ids=["extra-list", "desc-list", "levels-list", "level-list", "recall", "construct", "unit"],
)
def test_language_objects_anywhere_are_checked(tmp_path, mutate):
    out = problems(tmp_path, mutate)
    assert any("'de'" in line for line in out)


def test_level_codes_that_look_like_languages_are_not_languages(tmp_path):
    def f(d):
        d["X01"]["Levels"] = {"no": "No", "yes": "Yes"}
        d["Study"]["LicenseTerms"] = ["ok"]
    assert problems(tmp_path, f) == []


def test_message_names_the_level_path(tmp_path):
    out = problems(tmp_path, lambda d: d["X01"]["Levels"]["0"].update(de="Nein"))
    assert any("X01.Levels.0" in line for line in out)


def test_i18n_languages_string_is_one_clear_message(tmp_path):
    out = problems(tmp_path, lambda d: d["I18n"].update(Languages="en"))
    assert len([x for x in out if "I18n.Languages" in x]) == 1 and any("must be a list" in x for x in out)


@pytest.mark.parametrize("drop", [("Technical", "Language"), ("I18n", "Languages")])
def test_untagged_template_is_refused(tmp_path, drop):
    out = problems(tmp_path, lambda d: d[drop[0]].pop(drop[1]))
    assert any(".".join(drop) in line for line in out)


def german(d):
    d["Technical"]["Language"] = "de"
    d["I18n"]["Languages"] = ["de"]
    d["Study"]["LicenseLanguages"] = ["de"]
    d["Study"]["OriginalName"] = {"de": "X"}
    d["X01"] = {"Description": {"de": "Punkt"}, "Levels": {"0": {"de": "Nein"}}}


def test_german_only_template_with_german_evidence_passes(tmp_path):
    assert problems(tmp_path, german) == []


def test_plain_string_german_template_passes(tmp_path):
    def f(d):
        german(d)
        d["X01"] = {"Description": "Punkt"}
    assert problems(tmp_path, f) == []


def test_german_key_in_english_template_is_refused(tmp_path):
    assert problems(tmp_path, lambda d: d["X01"]["Description"].update(de="Punkt"))


@pytest.mark.parametrize("key,val", [
    ("AdministrationTime", {"min": 5, "max": 10}),
    ("ScoringTime", {"min": 5, "max": 10}),
    ("AgeRange", {"min": 18, "max": 65}),
    ("AgeRange", {"max": 1}),
])
def test_min_max_objects_are_not_language_objects(tmp_path, key, val):
    assert problems(tmp_path, lambda d: d["Study"].update({key: val})) == []


def test_levels_map_with_no_key_passes(tmp_path):
    assert problems(tmp_path, lambda d: d["X01"].update(Levels={"no": "Nein", "yes": "Ja"})) == []


@pytest.mark.parametrize("val", [{"de": "Punkt"}, {"en": "a", "de": "b"}, {"deu": "x"}])
def test_real_language_objects_outside_license_are_refused(tmp_path, val):
    assert problems(tmp_path, lambda d: d["X01"].update(Description=val))


@pytest.mark.parametrize("val", [{"xx": "a"}, {"gsw": "a"}, {"DE": "a"}, {"de": "x", "foo": "y"}, {"en": "x", "min": 1}])
def test_unknown_uppercase_and_mixed_language_objects_are_refused(tmp_path, val):
    assert problems(tmp_path, lambda d: d["X01"].update(Description=val))


def test_licensed_language_object_passes(tmp_path):
    def f(d):
        german(d)
        d["X01"]["Description"] = {"de": "x"}
    assert problems(tmp_path, f) == []


def test_language_object_nested_in_list_is_refused(tmp_path):
    assert problems(tmp_path, lambda d: d["X01"].update(Extra=[{"de": "x"}]))


def test_min_max_in_list_passes(tmp_path):
    assert problems(tmp_path, lambda d: d["X01"].update(Extra=[{"min": 1, "max": 2}])) == []


def test_reference_with_doi_field_is_not_a_language_object(tmp_path):
    assert problems(tmp_path, lambda d: d["Study"].update(References=[{"Type": "x", "Citation": "y", "DOI": "z"}])) == []


def test_root_level_item_named_like_a_language_code_is_fine(tmp_path):
    def f(d):
        for k in ("age", "sex", "id", "bmi"):
            d[k] = copy.deepcopy(d["X01"])
    assert problems(tmp_path, f) == []


def test_cli_exit_code(tmp_path):
    problems(tmp_path, lambda d: d["Study"].update(ItemCount=1))
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_library.py"), "--repo", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "survey-x.json" in r.stdout


def test_every_shipped_template_passes():
    assert check_library.check(ROOT) == []


def derived(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    task = path.stem.removeprefix("survey-")
    items = [k for k, v in data.items() if k not in ("Technical", "Metadata", "I18n", "Study") and isinstance(v, dict)]
    return {f"prism:{task}.{k.lower().replace('_', '-')}" for k in items}


def released(task):
    # score IDs (prism:<task>.score-...) come from the recipes, not from template items
    ids = (ROOT / "ids" / "survey-ids.txt").read_text(encoding="utf-8").split()
    return {i for i in ids if i.startswith(f"prism:{task}.") and not i.startswith(f"prism:{task}.score-")}


@pytest.mark.parametrize("task", ["dass", "dass21", "demo"])
def test_real_template(task):
    path = LIB / f"survey-{task}.json"
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert derived(path) == released(task) and len(derived(path)) == {"dass": 42, "dass21": 21, "demo": 8}[task]
    schema = json.loads((ROOT / "schemas" / "stable" / "survey.schema.json").read_text(encoding="utf-8"))
    project_only = schema["x-prism"]["projectOnlyRequired"]["Technical"]  # optional in a library template
    errs = [e.message for e in Draft7Validator(schema).iter_errors(data)
            if not any(f"'{f}' is a required property" in e.message for f in project_only)]
    assert errs == []
    other = r'"(?!en")[a-z]{2}"\s*:\s*"' if task != "dass21" else r'"(?!en"|de")[a-z]{2}"\s*:\s*"'
    assert not re.search(other, text)  # no other language key (dass21 also carries the German version)
    assert data["Study"]["Source"] == {"demo": "https://github.com/MRI-Lab-Graz/prism-specification"}.get(task, "https://www2.psy.unsw.edu.au/dass/")
    assert data["Study"]["LicenseChecked"] == "2026-11-14"
    assert data["I18n"]["Languages"] == (["en", "de"] if task == "dass21" else ["en"])


DASS_ITEMS_SHA256 = {  # sha256 of the items block (sorted-key JSON) at the commit before the metadata fix
    "dass": "174e18ee277cc40b07c202865fba79d2e743cac08f0059291b0e7b4d834c6f48",
    "dass21": "25ef2599f97c08524c0b8b30a8b6962dee27b218031173d5674703c906adf197",
}


@pytest.mark.parametrize("task", ["dass", "dass21"])
def test_dass_bibliographic_metadata(task):
    import hashlib

    data = json.loads((LIB / f"survey-{task}.json").read_text(encoding="utf-8"))
    study = data["Study"]
    assert study["Authors"] == ["Lovibond, S. H.", "Lovibond, P. F."]
    assert study["Year"] == 1995
    assert study["Citation"] != "Official webpage" and "Lovibond" in study["Citation"]
    assert len(study["References"]) >= 2 and study["References"][0]["Type"] == "primary"
    assert study["DOI"] == ""
    items = {k: v for k, v in data.items() if k not in ("Technical", "Metadata", "I18n", "Study")}
    if task == "dass21":  # the English text is unchanged: strip the German next to it
        def english(v):
            if isinstance(v, dict):
                return english(v["en"]) if "en" in v and set(v) == {"en", "de"} else {k: english(x) for k, x in v.items()}
            return v
        items = english(items)
    blob = json.dumps(items, sort_keys=True, ensure_ascii=False).encode()
    assert hashlib.sha256(blob).hexdigest() == DASS_ITEMS_SHA256[task]


@pytest.mark.parametrize("path", sorted(LIB.glob("*.json")), ids=lambda p: p.stem)
def test_every_shipped_template_is_bibliographically_complete(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert not [p for p in check_library.template_problems(data) if "Authors" in p or "Year" in p or "Citation" in p]


SBID = LIB / "survey-sbi-d.json"
SOURCE_SBID = Path("/Volumes/Evo/work/prism-local-library/research/sbi-d-source.json")


def test_sbid_template_shape():
    data = json.loads(SBID.read_text(encoding="utf-8"))
    problems_ = check_library.template_problems(data)
    assert problems_ == []
    items = {k: v for k, v in data.items() if k not in ("Technical", "Metadata", "I18n", "Study")}
    assert list(items) == [f"SBID{i:02d}" for i in range(1, 25)]
    for v in items.values():
        assert (v["MinValue"], v["MaxValue"], v["DataType"], v["ScaleType"]) == (1, 7, "integer", "likert")
        assert list(v["Levels"]) == ["1", "7"]
    assert data["Technical"]["Language"] == "de" and data["Study"]["LicenseLanguages"] == ["de"]
    assert "Reversed" not in SBID.read_text(encoding="utf-8")
    assert derived(SBID) == released("sbi-d") and len(derived(SBID)) == 24
    ids = (ROOT / "ids" / "survey-ids.txt").read_text(encoding="utf-8").split()
    assert {i for i in ids if i == "prism:sbi-d" or i.startswith("prism:sbi-d.")} == {"prism:sbi-d"} | {f"prism:sbi-d.sbid{i:02d}" for i in range(1, 25)}


@pytest.mark.skipif(not SOURCE_SBID.is_file(), reason="local source file not available (CI)")
def test_sbid_wording_is_the_source_wording():
    src = json.loads(SOURCE_SBID.read_text(encoding="utf-8"))
    data = json.loads(SBID.read_text(encoding="utf-8"))
    assert {f"SBID{int(i):02d}": t for i, t in src["Items"].items()} == {k: data[k]["Description"] for k in data if k.startswith("SBID")}
    assert len(src["Items"]) == 24 and data["Study"]["Instructions"] == src["Instruction"]
    assert data["SBID01"]["Levels"] == src["ScaleAnchors"]


DE_TEXTS = [
    "Der Fragebogen erfasst die subjektive Belastung durch depressive Symptome, Angst und Stress und wird in der "
    "klinischen Praxis sowie in der Forschung eingesetzt. Die Probanden beantworten die Aussagen auf einer vierstufigen "
    "Skala und es wird ein Summenwert für jede Skala gebildet, der nicht von der Anzahl der Items abhängt.",
    "Die interne Konsistenz der Skalen ist mit Werten zwischen .80 und .92 als gut bis sehr gut zu bewerten. Die "
    "Retest-Reliabilität über einen Zeitraum von vier Wochen liegt bei .75, und die Ergebnisse sind auch bei "
    "klinischen Stichproben stabil, wobei die Werte für Männer und Frauen sich nicht unterscheiden.",
    "Die faktorielle Validität wurde mit einer konfirmatorischen Faktorenanalyse geprüft, die ein dreifaktorielles "
    "Modell bestätigt hat. Die Skalen korrelieren mit anderen Verfahren zur Erfassung der Depressivität und es gibt "
    "Hinweise auf die Kriteriumsvalidität, die jedoch nur an einer kleinen Stichprobe untersucht wurde.",
    "Dieses Verfahren wurde von den Autoren aus dem Englischen übersetzt und für den deutschen Sprachraum angepasst. "
    "Die Bewertung der Items erfolgt nicht umgekehrt, und die Auswertung ist für Erwachsene ab 18 Jahren geeignet, "
    "die über ausreichende Deutschkenntnisse verfügen, um die Aussagen zu verstehen und zu beantworten.",
    "Die Normierung erfolgte an einer repräsentativen Stichprobe der deutschen Bevölkerung mit mehr als 2000 "
    "Personen. Für die Auswertung stehen Prozentränge und T-Werte nach Alter und Geschlecht zur Verfügung, die "
    "von den Autoren auf der Webseite des Testarchivs veröffentlicht wurden und frei zugänglich sind.",
]
EN_TEXTS = [
    "The questionnaire measures the subjective burden of depressive symptoms, anxiety and stress and is used in "
    "clinical practice and in research. Participants answer the statements on a four-point scale and a sum score "
    "is formed for each scale, which does not depend on the number of items in the questionnaire.",
    "The internal consistency of the scales is good to very good, with values between .80 and .92. The test-retest "
    "reliability over a period of four weeks is .75, and the results are also stable in clinical samples, with no "
    "difference between the values for men and women in any of the studies that were reviewed.",
    "Factorial validity was tested with a confirmatory factor analysis, which confirmed a three-factor model. The "
    "scales correlate with other measures of depression and there is evidence for criterion validity, which has "
    "however only been examined in a small sample of adults from one university.",
]


def _with(field, text):
    return lambda d: d["Study"].update({field: text})


@pytest.mark.parametrize("i,field", [(0, "Description"), (1, "Reliability"), (2, "Validity"), (3, "Notes"),
                                     (4, "Norming"), (0, "Construct")])
def test_german_descriptive_field_is_refused(tmp_path, i, field):
    out = problems(tmp_path, _with(field, DE_TEXTS[i]))
    assert any(f"Study.{field}: text looks German" in x for x in out)


def test_german_in_archive_metadata_keywords_and_terms_is_refused(tmp_path):
    assert problems(tmp_path, _with("ArchiveMetadata", {"Abstract": {"x": [DE_TEXTS[0]]}}))
    assert problems(tmp_path, _with("Keywords", ["depression", DE_TEXTS[1]]))
    assert problems(tmp_path, _with("LicenseTerms", [DE_TEXTS[2]]))


@pytest.mark.parametrize("field", ["Description", "Reliability", "Validity", "Notes"])
def test_english_descriptive_field_passes(tmp_path, field):
    for t in EN_TEXTS:
        assert problems(tmp_path, _with(field, t)) == []
        assert problems(tmp_path, _with(field, {"en": t})) == []


def test_german_object_or_other_language_key_in_description_is_refused(tmp_path):
    assert problems(tmp_path, _with("Description", {"de": DE_TEXTS[0]}))
    assert problems(tmp_path, _with("Description", {"en": "ok", "fr": "ok"}))


def test_instrument_text_and_license_quotes_may_be_german(tmp_path):
    def f(d):
        german(d)
        d["X01"]["Description"] = DE_TEXTS[3]
        d["Study"]["Instructions"] = DE_TEXTS[0]
        d["Study"]["OriginalName"] = "Fragebogen zur Erfassung der Persönlichkeit und Stimmung"
        d["Study"]["License"] = '"' + DE_TEXTS[4] + '"'
        d["Study"]["Citation"] = DE_TEXTS[1]
    assert problems(tmp_path, f) == []


def test_english_object_passes_when_licence_covers_only_german(tmp_path):
    def f(d):
        german(d)
        d["Study"]["Description"] = {"en": EN_TEXTS[0]}
    assert problems(tmp_path, f) == []


@pytest.mark.parametrize("v", ["Adults", "Paper-pencil", "5 minutes"])
def test_short_english_strings_pass(tmp_path, v):
    assert problems(tmp_path, _with("AgeRange", v)) == []
    assert problems(tmp_path, _with("Keywords", [v])) == []


def test_english_with_german_title_and_names_passes(tmp_path):
    t = ("The German adaptation, titled Fragebogen zur Erfassung der Depressivität, was published by Müller and "
         "Schröder in Göttingen. It measures the burden of depressive symptoms in adults and is used in clinical "
         "practice and in research, where it has been applied to samples from several countries.")
    assert problems(tmp_path, _with("Description", t)) == []


SHORT_DE = [
    "Die Skala wurde an einer Stichprobe von Studierenden validiert und zeigt eine gute Reliabilität.",
    "Der Test ist für Kinder und Jugendliche geeignet.",
    "Es handelt sich um ein Selbstbeurteilungsverfahren, das nicht von Experten ausgewertet werden muss.",
    "Die Durchführung dauert etwa zehn Minuten und kann einzeln oder in der Gruppe erfolgen.",
    "Der Gesamtwert wird durch Addition der Itemwerte berechnet, wobei die Items 3 und 7 umgepolt werden müssen.",
    "Erwachsene", "Fragebogen", "Kinder und Jugendliche", "Selbstbeurteilung", "Fragebogen zur Erfassung von Angst",
    "Dauer etwa 10 Minuten", "Für Erwachsene ab 18 Jahren", "Wird vom Testleiter vorgelesen",
    "Nicht für den klinischen Einsatz geeignet", "Das Verfahren ist kostenlos und frei verfügbar",
    "Auswertung mit Schablone oder am Computer", "Nur zur Forschung", "Selbstbeurteilung und Fremdbeurteilung",
]
SHORT_EN = [
    "Adults", "Paper-pencil", "5 minutes", "Self-report questionnaire for adults", "Takes about ten minutes to complete.",
    "Anxiety and depression in children", "Original German version", "Adapted from Bryant (2003).",
    "German version of the Beck Depression Inventory", "Scores are summed; higher means more severe.",
    "Items 3 and 7 are reverse coded.",     "Translated by two bilingual psychologists in Vienna.", "Online, in groups or individually", "Screening in primary care",
    "Persönlichkeit", "Zürich", "Adolescents aged 12 to 18",
]


@pytest.mark.parametrize("t", SHORT_DE)
def test_short_german_is_flagged(t):
    assert check_library.looks_german(t), t


@pytest.mark.parametrize("t", SHORT_EN)
def test_short_english_is_not_flagged(t):
    assert not check_library.looks_german(t), t


def test_short_german_keyword_and_note_are_refused_in_a_template(tmp_path):
    assert problems(tmp_path, _with("Keywords", ["anxiety", "Selbstbeurteilung"]))
    assert problems(tmp_path, _with("Notes", "Der Test ist für Kinder und Jugendliche geeignet."))


ARCHIVE_EXEMPT = ["Durchführung/Instruktion", "Wichtige neuere Publikationen", "Rezensionen",
                  "Orginalfassung/Anderssprachlige Fassungen"]


def _archive(section_or_field, key, text=None):
    text = text or DE_TEXTS[0]
    return _with("ArchiveMetadata", {section_or_field: {key: [text]}})


@pytest.mark.parametrize("key", ARCHIVE_EXEMPT)
def test_german_in_exempt_archive_sections_passes(tmp_path, key):
    assert problems(tmp_path, _archive("sections", key)) == []
    assert problems(tmp_path, _archive("sections", key, DE_TEXTS[1])) == []


@pytest.mark.parametrize("section,key", [
    ("sections", "Kurzabstract"), ("sections", "Testkonzept/Theoretischer Hintergrund"),
    ("fields", "Reliabilität"), ("fields", "Durchführung/Instruktion"),
    ("sections", "Durchführung/Instruktion (Entwurf)"), ("sections", "Rezensionen und mehr"),
    ("other", "Rezensionen"),
])
def test_german_elsewhere_in_archive_metadata_is_refused(tmp_path, section, key):
    assert problems(tmp_path, _archive(section, key))


def test_exempt_archive_section_does_not_hide_a_sibling(tmp_path):
    out = problems(tmp_path, _with("ArchiveMetadata", {"sections": {"Rezensionen": [DE_TEXTS[0]],
                                                                    "Kurzabstract": [DE_TEXTS[1]]}}))
    assert len(out) == 1


def test_german_description_still_refused_next_to_exempt_sections(tmp_path):
    def f(d):
        d["Study"]["ArchiveMetadata"] = {"sections": {"Rezensionen": [DE_TEXTS[0]]}}
        d["Study"]["Description"] = DE_TEXTS[0]
    assert problems(tmp_path, f)


EBI = ('The Fragebogen zur Wahrnehmung der Psychologie als Wissenschaft (= Epistemic Beliefs Inventory - '
       'Absolutism-Multiplism, abbr.: EBI-AM; ...) is used to assess discipline-specific epistemic beliefs. '
       'Epistemic beliefs are defined as "individuelle subjektive Ansichten, Auffassungen und Theorien über die '
       'Genese, Ontologie, Bedeutung, Rechtfertigung und Gültigkeit von Wissen in den Wissenschaften" '
       '(Priemer, 2006, p. 160).')
DE_DEF = ("individuelle subjektive Ansichten, Auffassungen und Theorien über die Genese, Ontologie, Bedeutung, "
          "Rechtfertigung und Gültigkeit von Wissen in den Wissenschaften")
DE_LONG = ("Die Durchführung dauert etwa zehn Minuten und kann einzeln oder in der Gruppe erfolgen. Der Gesamtwert "
           "wird durch Addition der Itemwerte berechnet, wobei die Items 3 und 7 umgepolt werden müssen. Das "
           "Verfahren ist kostenlos und frei verfügbar und eignet sich für Erwachsene sowie Jugendliche in der Praxis "
           "und in der Forschung.")


def test_short_quoted_german_is_a_quote_not_flagged():
    assert not check_library.looks_german(EBI)
    assert not check_library.looks_german('"Papier und Bleistift"')
    assert not check_library.looks_german("It is called „Papier und Bleistift“ and “Fragebogen zur Angst”.")


def test_unquoted_or_long_quoted_german_is_still_flagged():
    assert check_library.looks_german(f"Epistemic beliefs are defined as {DE_DEF} (Priemer, 2006).")
    assert len(DE_LONG) > 300
    assert check_library.looks_german(f'"{DE_LONG}"')


# --- rule (h): no extraction artefacts -------------------------------------------------------------------------

@pytest.mark.parametrize("char", ["ﬀ", "ﬁ", "ﬂ", "ﬃ", "ﬄ", "ﬅ", "ﬆ",
                                  "­", "​", "‌", "‍", "﻿"])
@pytest.mark.parametrize("where", ["item", "level", "instructions"])
def test_rule_h_refuses_extraction_characters(tmp_path, char, where):
    def mutate(d):
        if where == "item":
            d["X01"]["Description"]["en"] = f"Item{char}text"
        elif where == "level":
            d["X01"]["Levels"]["0"]["en"] = f"No{char}"
        else:
            d["Study"]["Instructions"] = {"en": f"Read{char}this"}

    out = problems(tmp_path, mutate)
    assert any(f"U+{ord(char):04X}" in line and "survey-x.json" in line for line in out), out


def test_rule_h_names_the_field(tmp_path):
    out = problems(tmp_path, lambda d: d["X01"]["Description"].update(en="ofﬁce"))
    assert any("X01.Description.en" in line for line in out)


def test_rule_h_lets_normal_text_pass(tmp_path):
    text = "Schön, Straße, Ärger – „quoted“, ‘x’ and so on…"
    assert problems(tmp_path, lambda d: d["X01"]["Description"].update(en=text)) == []


def test_shipped_templates_pass_the_library_check():
    assert check_library.check(ROOT) == []
    assert {p.name for p in LIB.glob("survey-*.json")} >= {"survey-dass.json", "survey-dass21.json", "survey-demo.json",
                                                            "survey-sbi-d.json", "survey-kse.json"}


def test_archive_templates_state_who_holds_which_rights():
    archive = [d for d in (json.loads(p.read_text(encoding="utf-8")) for p in LIB.glob("survey-*.json"))
               if "testarchiv.eu" in json.dumps(d["Study"].get("LicenseTerms", []))]
    assert len(archive) >= 20
    for d in archive:
        terms = " ".join(d["Study"]["LicenseTerms"])
        assert "authors of this version" in terms and "original instrument" in terms and "not covered" in terms, d["Study"]["TaskName"]
        assert d["Study"]["LicenseLanguages"] == ["de"], d["Study"]["TaskName"]


# --- Study.LicenseByLanguage: a per-language licence entry overrides the template-level one for that language ---

DE_ENTRY = {
    "License": '"Copyright Autor(-Innen); CC-BY-SA 4.0" "Die Nutzung ist erlaubt."',
    "LicenseID": "CC-BY-SA-4.0",
    "Source": "https://example.org/de",
    "LicenseChecked": "2026-11-14",
    "LicenseTerms": ["Released under CC BY-SA 4.0."],
}


def bilingual(d):
    d["I18n"]["Languages"] = ["en", "de"]
    d["Study"]["LicenseLanguages"] = ["en", "de"]
    d["Study"]["LicenseByLanguage"] = {"de": copy.deepcopy(DE_ENTRY)}
    d["X01"]["Description"]["de"] = "Punkt"


def test_bilingual_template_with_a_german_entry_passes(tmp_path):
    assert problems(tmp_path, bilingual) == []


def test_template_level_licence_covers_languages_without_an_entry(tmp_path):
    def f(d):
        bilingual(d)
        d["Study"]["LicenseLanguages"] = ["en", "de", "fr"]
        d["Study"]["LicenseByLanguage"] = {}
    assert problems(tmp_path, f) == []


def test_every_language_with_its_own_entry_needs_no_template_level_licence(tmp_path):
    def f(d):
        bilingual(d)
        d["Study"]["LicenseByLanguage"]["en"] = {**DE_ENTRY, "License": '"Free to copy as stated."'}
        for k in ("License", "Source", "LicenseChecked", "LicenseTerms"):
            del d["Study"][k]
    assert problems(tmp_path, f) == []


def test_missing_template_licence_is_refused_for_a_language_without_an_entry(tmp_path):
    def f(d):
        bilingual(d)
        for k in ("License", "Source", "LicenseChecked", "LicenseTerms"):
            del d["Study"][k]
    out = problems(tmp_path, f)
    assert any("Study.License must quote" in p for p in out)  # the English side is left without a licence


@pytest.mark.parametrize(
    "mutate,needle",
    [
        (lambda e: e.update(License="no quote here"), "Study.LicenseByLanguage.de.License must quote"),  # a
        (lambda e: e.update(Source="www.example.org"), "Study.LicenseByLanguage.de.Source must be an absolute https URL"),  # b
        (lambda e: e.update(LicenseChecked="14.11.2026"), "Study.LicenseByLanguage.de.LicenseChecked must be a date"),  # c
        (lambda e: e.pop("LicenseChecked"), "Study.LicenseByLanguage.de.LicenseChecked must be a date"),  # c
        (lambda e: e.update(LicenseTerms="Do not sell."), "Study.LicenseByLanguage.de.LicenseTerms must be a non-empty list"),  # d
        (lambda e: e.update(LicenseTerms=[]), "Study.LicenseByLanguage.de.LicenseTerms must be a non-empty list"),  # d
        (lambda e: e.update(LicenseTerms=["Die Nutzung ist nicht erlaubt und wird auch nicht für die Forschung verwendet."]),
         "Study.LicenseByLanguage.de.LicenseTerms: text looks German"),  # English-metadata rule
        (lambda e: e.update(License={"en": '"Free to copy."', "fr": "x"}), "language 'fr' is not in Study.LicenseLanguages"),
    ],
)
def test_each_licence_rule_applies_per_language_entry(tmp_path, mutate, needle):
    def f(d):
        bilingual(d)
        mutate(d["Study"]["LicenseByLanguage"]["de"])
    assert any(needle in p for p in problems(tmp_path, f)), problems(tmp_path, f)


def test_licence_by_language_key_must_be_a_licence_language(tmp_path):
    def f(d):
        bilingual(d)
        d["Study"]["LicenseByLanguage"]["fr"] = copy.deepcopy(DE_ENTRY)
    assert any("LicenseByLanguage" in p and "'fr'" in p and "LicenseLanguages" in p for p in problems(tmp_path, f))


@pytest.mark.parametrize("value", ["CC-BY-SA-4.0", ["de"], {"DE": copy.deepcopy(DE_ENTRY)}])
def test_licence_by_language_must_be_a_map_of_entries(tmp_path, value):
    def f(d):
        bilingual(d)
        d["Study"]["LicenseByLanguage"] = value
    assert any("LicenseByLanguage" in p for p in problems(tmp_path, f))


def test_dass21_carries_the_german_version_and_dass_de_is_gone():
    d = json.loads((LIB / "survey-dass21.json").read_text(encoding="utf-8"))
    assert not (LIB / "survey-dass-de.json").exists()
    assert d["I18n"]["Languages"] == ["en", "de"] and d["Study"]["LicenseLanguages"] == ["en", "de"]
    items = [k for k in d if k.startswith("DASS21")]
    assert len(items) == 21
    for k in items:
        assert set(d[k]["Description"]) == {"en", "de"} and d[k]["Description"]["de"].strip()
        assert set(d[k]["Levels"]["0"]) == {"en", "de"} and d[k]["Levels"]["3"]["de"].startswith("Traf sehr stark")
    assert d["DASS2101"]["Description"]["de"] == "Ich fand es schwer, mich zu beruhigen."
    assert d["DASS2121"]["Description"]["de"] == "Ich empfand das Leben als sinnlos."
    assert d["DASS2108"]["Description"]["de"] == "Ich fand alles anstrengend."
    assert set(d["Study"]["Instructions"]) == {"en", "de"}
    study = d["Study"]
    assert "Public domain" not in study["License"] and "public domain" in study["License"]  # template level stays English
    de = study["LicenseByLanguage"]["de"]
    assert de["LicenseID"] == "CC-BY-SA-4.0" and de["LicenseChecked"] == "2026-11-14"
    assert "authors of this version" in " ".join(de["LicenseTerms"]) and "not covered" in " ".join(de["LicenseTerms"])
    assert "item 8" in study["Notes"].lower()
    assert any("Nilges" in r["Citation"] for r in study["References"])
    assert not [p for p in check_library.template_problems(d)]


def test_no_two_library_templates_share_an_item_key():
    # the Studio converter refuses duplicate item IDs across templates
    seen = {}
    for p in sorted(LIB.glob("survey-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for k, v in d.items():
            if k not in check_library.NON_ITEMS and isinstance(v, dict):
                assert k not in seen, f"item key {k} is in both {seen[k]} and {p.name}"
                seen[k] = p.name
