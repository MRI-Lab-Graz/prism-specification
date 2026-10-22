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
  defines the concept); the slug is lowercase letters, digits and `-`; a child
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
