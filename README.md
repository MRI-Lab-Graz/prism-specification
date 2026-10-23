# PRISM specification

The machine-readable specification of [PRISM](https://github.com/MRI-Lab-Graz/prism-studio)
(Principled Research Information & Sidecar Model): the JSON schemas of every
modality, the term registry and the specification pages.

| Folder | Content |
| --- | --- |
| `schemas/stable/` | The current schema of each modality (`survey`, `biometrics`, `biosample`, `environment`, `events`, `physio`) plus `entities` (filename grammar) and `dataset_description` |
| `schemas/archive/` | Every released older version of a modality schema, frozen |
| `schemas/v0.1/`, `schemas/v0.2/` | Legacy schema bundles |
| `terms/<modality>/` | The term registry: one JSON file per metric (`prism:cortisol`, `prism:cortisol.saliva`) |
| `specs/` | The specification pages (human-readable; the field tables are generated from the schemas) |
| `scripts/` | The checks that CI runs (MIT licence) |

PRISM Studio and the `prism-validator` carry a copy of a tagged release of this
repository and never edit it. Changes are made here, released with a tag, and
synced into Studio.

## Proposing a metric or a change

Use the "Propose a Metric" issue form (or `python prism_tools.py terms propose` in PRISM Studio), or open a
pull request. See [CONTRIBUTING.md](CONTRIBUTING.md) for what a term file looks like, the rules, and the
checks CI runs.

## Licence

CC BY 4.0 for the specification, MIT for the scripts; see [LICENSE](LICENSE).
