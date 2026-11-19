# Mappings

PRISM data carries IDs and nothing else about meaning. What an ID is the same as, what it measures, which way
a value points and how a value is read as a state is written in a separate layer, `mappings/`. A mapping can be
added, corrected or removed without a new schema version, because it never touches the data or the ID.

PRISM keeps no list of symptoms or constructs of its own: a link points to an entry in an existing external
vocabulary. The URLs in the example below are placeholders (`example.org`), not real codes; the files under "Shipped mappings" use real ones.

## A mapping file

One file per ID family: `mappings/<modality>/<family>.json`. The file name is the local part of the family's ID:
`mappings/survey/phq9.json` holds the instrument, its items and its scores; `mappings/biosample/cortisol.json`
holds `prism:cortisol` and its specimen children. Keys are full IDs of that family.

```json
{
  "prism:example": {
    "SameAs": {"snomed": "https://example.org/placeholder"}
  },
  "prism:task.item01": {
    "Measures": [
      {"URL": "https://example.org/placeholder", "Match": "exact", "Higher": "more",
       "Source": "who made the link", "Checked": "2026-01-01", "Status": "reviewed"}
    ],
    "ValueRules": [
      {"Name": "task-present", "Source": "the manual",
       "Rules": [{"When": {"Op": ">=", "Value": 2}, "State": "present"},
                 {"When": {"Op": "<",  "Value": 2}, "State": "absent"}]}
    ],
    "Levels": {
      "3": {"Measures": [{"URL": "https://example.org/placeholder", "Match": "narrower"}]}
    }
  }
}
```

## The four fields

| Field | Meaning |
|---|---|
| `SameAs` | The ID is the same thing as that entry in another vocabulary: `{vocabulary: URL}`, one URL per vocabulary. |
| `Measures` | The item, score or variable measures that concept: a list of `{URL, Match, Higher, Source, Checked, Status}`. Only `URL` is required. `Match` is `exact`, `broader`, `narrower` or `related`; `Higher` is `more` or `less` (a higher value means more or less of the concept); `Checked` is a date `YYYY-MM-DD`; `Status` is `reviewed` or `unreviewed`. |
| `ValueRules` | Named rules that read a value as a state: a list of `{Name, Source, Rules}`; each rule is `{When: {Op, Value}, State}`. `Op` is one of `==`, `!=`, `>=`, `>`, `<=`, `<`, `in` (`in` takes a list). `Name` and `State` are slugs. Several rules may exist and disagree; none is the truth, a consumer picks one by name. |
| `Levels` | The same `Measures` and `ValueRules` for one answer value or category, keyed by the level code as written in the data. |

A mapping file holds no free text except `Source` (and the slug `Name`). It never quotes item wording.

## The rules

`python scripts/check_mappings.py` checks that:

* every key is a released ID of the file's modality: a term of `terms/<modality>/` (or a child of an existing
  analyte), or for survey an ID in `ids/survey-ids.txt`; the IDs derived from `library/` and `recipes/` must all
  be in that list too;
* the family of the key is the file name;
* every `SameAs` name is a vocabulary in `mappings/vocabularies.json`, and every URL matches the pattern of its
  vocabulary (a `Measures` URL must match one of them). The patterns are data, not code; the patterns check the
  shape of a URL, not that the entry exists, so the author looks every link up;
* every `Levels` code exists in the definition of the ID (the term's or the template's `Levels`); an ID without
  `Levels` takes none;
* the types are right (a wrong type is a message, not a crash), and no ID is in two files.

A specimen child (`prism:cortisol.serum`) inherits the links of its analyte; no check is needed for that.

## Who reviews links

An author adds a link as `unreviewed`, looks the URL up in the vocabulary and writes `Source` and `Checked`. A
maintainer who has checked it sets `Status` to `reviewed`. Content arrives by pull request, like terms.

## Shipped mappings

* **DASS and DASS-21** (`mappings/survey/dass.json`, `dass21.json`): every item is linked to the SNOMED CT score of
  the subscale it counts towards (depression, anxiety or stress), as `Measures` with `Match` `related`, `Higher`
  `more`. The assignment is the one on the DASS authors' own scoring template; the three codes were looked up on a
  SNOMED CT terminology server (edition 2026-07-01). Links are `unreviewed` until a maintainer has checked them.
  The templates define no subscale scores, so there are no links for scores.
* **Demo** (`mappings/survey/demo.json`): one `ValueRules` entry on the demo total score. It is invented, to show the
  format, and is not a research rule.
