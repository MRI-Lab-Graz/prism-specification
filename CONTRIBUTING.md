# Contributing

Thank you for helping to extend PRISM. By contributing you agree that your
contribution is licensed as stated in [LICENSE](LICENSE): CC BY 4.0 for
`schemas/`, `terms/` and `specs/`, MIT for `scripts/` and `tests/`.

## Proposing a metric with PRISM Studio or the issue form

The easiest way is the command in PRISM Studio, which builds the proposal from a column of your
sidecar and opens the issue form with the field filled in:

```bash
python prism_tools.py terms propose --sidecar <your sidecar.json> --column <column> --open
```

Without `--open` it only prints the proposal. You can also open the
["Propose a Metric" issue form](https://github.com/MRI-Lab-Graz/prism-specification/issues/new?template=propose-metric.yml) and paste a proposal by hand.
A proposal is one JSON document of at most 50,000 bytes (a GitHub form field holds 65,536 characters),
in **format v2**: the files it adds, each under its repository path.

```json
{"format": "prism-proposal/2",
 "files": {"terms/biosample/dhea-s.json": <parent term>,
           "terms/biosample/dhea-s.saliva.json": <child term>}}
```

* Up to 40 files. Each key is a repository path of the form `terms/<modality>/<id>.json` (nothing else is
  accepted), and the file name must equal the local part of the term's `TermID`.
* A child term's `Parent` is either an official term or in the same proposal.
* The older format `{"modality": "biosample", "terms": [...]}` is still accepted, limited to two terms.
* A proposal too long for the prefilled link is pasted into the form's text field; nothing is attached.
* Only `prism:` IDs, and none of the fields `Status` and `ReplacedBy` (the maintainer's merge sets them).
* A bot checks it against the current registry (the same rules as below). For trusted authors it opens a
  draft pull request; for everyone else a maintainer takes over. The maintainers may choose a different
  ID or name; your own column name is kept as an alias.
* No GitHub account: save the proposal with `--out proposal.json` (the same command, add `--out`) and send the
  file to a maintainer, who can run
  `python scripts/term_proposal.py check --file proposal.json --terms terms/biosample --schema schemas/stable/biosample.schema.json --out bundle`.

## Proposing an addition to a modality (schema patch)

Sometimes your data needs something an existing modality does not allow yet: a specimen type that is not
in the list, or an extra optional field. A proposal can carry a **patch** for that, as the file
`patches/<modality>.json` of a format v2 document (only `biosample` has patches so far):

```json
{"operations": [
  {"op": "add_enum_values", "path": "Technical.SpecimenType", "values": ["sweat"]},
  {"op": "add_optional_properties", "path": "Technical",
   "properties": {"SweatRate": {"type": "number", "description": "Sweat rate in mg/min"}}}]}
```

* Only additions, with tight limits: at most 20 operations; `add_enum_values` takes at most 20 values
  (lowercase letters, digits and `-`); `add_optional_properties` takes at most 20 properties named like
  `SweatRate`, each with a `type` (`string`, `number`, `integer` or `boolean`) and optionally a
  `description` and an `enum`. Nothing else is accepted, and nothing is ever removed or made required.
* `path` is the dotted name of the field in a sidecar (`Technical.SpecimenType`).
* Values or properties the schema already has are skipped; a patch that adds nothing is refused.
* A term that uses a specimen added by the patch in the same proposal is checked against the extended list.
* The bot prepares the schema release for the maintainer: the previous schema is copied unchanged to
  `schemas/archive/`, the stable schema gets the additions and a bumped minor version (and `$id`), and the
  field tables of the spec page are regenerated. The stable schema file is edited in place, so its diff
  shows only the new version, the new `$id` and the additions. CI then runs the same version check as for
  any schema change.
* Check a patch yourself with `python scripts/term_proposal.py check --file proposal.json --terms
  terms/biosample --schema schemas/stable/biosample.schema.json --out bundle`.

## Proposing a new metric (term)

A term is one JSON file in `terms/<modality>/`, named after the local part of its ID.

* **Parent term** (the analyte), e.g. `terms/biosample/cortisol.json`:
  `TermID` (`prism:cortisol`), `Level` (`analyte`), `Label`, `Aliases`,
  `Description`, `Status` (`official`).
* **Child term** (the analyte in one specimen), e.g.
  `terms/biosample/cortisol.saliva.json`: `TermID` (`prism:cortisol.saliva`),
  `Level` (`analyte-specimen`), `Parent`, `SpecimenType`, `Units` (UCUM,
  e.g. `nmol/L`), optional `AlternativeUnits`, `MinValue`, `WarnMaxValue`,
  `LOINC`, `Equivalents`, `Status`.

Rules (CI enforces them with `python scripts/check_terms.py`):

* IDs are `prism:<slug>` (or `bids:<name>` when the BIDS specification already
  defines the concept); the slug is lowercase letters, digits and `-` (at most 63 characters, also for the specimen part); a child
  is `<parent>.<specimen>`.
* **An ID is frozen once released.** A wrong name is fixed by changing the
  `Label`, or by deprecating the term (`Status: deprecated`, `ReplacedBy`),
  never by renaming the ID.
* A user's own column name goes into `Aliases`, never into the ID.
* Do not invent clinical ranges or LOINC codes; leave them out unless you can
  cite them in the pull request.

Check your files:

```bash
python scripts/check_terms.py --terms terms/biosample --schema schemas/stable/biosample.schema.json
```

## Proposing a new kind of data

If PRISM has no kind of data (modality) for your data yet, open the issue form
"Propose a new kind of data" (or let PRISM Studio fill it in). Give:

- a description: what is measured, with which device or method, how the files are organised;
- a small made-up sample file, pasted as text (at most 50,000 bytes, no real participant data);
- optionally, the existing kind of data that is closest.

A bot checks that the description and sample are there and the agreements are ticked. Then a
maintainer builds the schema, the file-name entry (`entities`) and the specification page in a
normal pull request. PRISM cannot validate this kind of data locally until that pull request is
merged and part of a PRISM release.

## Changing a schema

1. Copy the current `schemas/stable/<name>.schema.json` unchanged to
   `schemas/archive/<name>/<old version>.schema.json`.
2. Edit the stable file and bump its `version` and the version suffix of its `$id`.
3. Run `python scripts/generate_schema_reference.py` to refresh the field tables in `specs/`.

CI (`scripts/check_schema_versions.py`) enforces: files under `schemas/archive/`
are never modified or deleted; a changed stable modality schema carries a bumped
`version`; a bumped version needs the previous version archived as an exact copy.
Run it before opening the pull request:
`python scripts/check_schema_versions.py origin/main HEAD`.

Some changes also need a change in the PRISM validator (prism-studio). Open that
pull request there and mention it here; schema releases are tagged `vX.Y.Z` and
Studio adopts a tag with its sync script.

## Core review

`schemas/stable/entities.schema.json` (filename grammar) and
`schemas/stable/dataset_description.schema.json` need a core maintainer's
approval (see `CODEOWNERS`).
