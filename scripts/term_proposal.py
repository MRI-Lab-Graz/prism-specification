"""Check and write a proposal for new terms (metrics).

A proposal is one JSON document, sent through the "Propose a metric" issue form or saved
to a file by `prism_tools.py terms propose` in PRISM Studio:

  {"modality": "biosample", "terms": [<parent term>, <child term>]}

The issue body is untrusted text: it is parsed as JSON only, size-capped, and every field
is checked against an allow-list before anything is written. File names are derived only
from IDs that passed the slug rule. Stdlib only; reuses scripts/check_terms.py.

Spec: docs/superpowers/specs/2026-10-23-metric-proposal-design.md in prism-studio
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

MAX_BYTES = 20_000
MAX_TERMS = 2
ALLOWED_FIELDS = frozenset(
    "TermID Level Label Aliases Description Parent SpecimenType Units AlternativeUnits "
    "MinValue WarnMaxValue LOINC Equivalents".split()
)
MODALITIES = ("biosample",)
_LOCAL = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)?$")
_SECTION = re.compile(r"^### (.+?)\s*$", re.M)
_FENCE = re.compile(r"```[A-Za-z]*\n(.*?)\n?```", re.S)
_CHECKBOX = re.compile(r"^- \[([ xX])\]", re.M)


class ProposalError(ValueError):
    """The issue does not hold a usable proposal."""


def _sibling(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_terms = _sibling("check_terms")


def _sections(body: str) -> dict[str, str]:
    parts = _SECTION.split(body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def extract_proposal(issue_body: str) -> dict:
    """Read the proposal out of an issue-form body; ProposalError says what is wrong."""
    sections = _sections(issue_body or "")
    boxes = _CHECKBOX.findall(sections.get("Agreements", ""))
    if len(boxes) < 2 or any(b == " " for b in boxes):
        raise ProposalError("Both agreements (licence, no personal data) must be ticked.")
    text = sections.get("Proposal", "").strip()
    fences = _FENCE.findall(text)
    if len(fences) > 1:
        raise ProposalError("The proposal field must hold exactly one JSON document.")
    if fences:
        text = fences[0].strip()
    if not text:
        raise ProposalError("The proposal field is empty.")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ProposalError(f"The proposal is larger than {MAX_BYTES} bytes.")
    try:
        proposal = json.loads(text)
    except ValueError as exc:
        raise ProposalError(f"The proposal is not valid JSON: {exc}") from exc
    if not isinstance(proposal, dict):
        raise ProposalError("The proposal must be a JSON object.")
    return proposal


def _shape_problems(proposal) -> list[str]:
    if not isinstance(proposal, dict):
        return ["the proposal must be a JSON object"]
    problems = []
    if proposal.get("modality") not in MODALITIES:
        problems.append(f"modality must be one of {', '.join(MODALITIES)}")
    terms = proposal.get("terms")
    if not isinstance(terms, list) or not terms:
        return problems + ["terms must be a non-empty list"]
    if len(terms) > MAX_TERMS:
        problems.append(f"a proposal has at most {MAX_TERMS} terms, found {len(terms)}")
    for i, term in enumerate(terms, 1):
        where = f"term {i}"
        if not isinstance(term, dict):
            problems.append(f"{where}: must be a JSON object")
            continue
        for key in sorted(set(term) - ALLOWED_FIELDS):
            hint = " (set by the maintainer's merge)" if key in ("Status", "ReplacedBy") else ""
            problems.append(f"{where}: field {key!r} is not allowed in a proposal{hint}")
        tid = term.get("TermID")
        prefix, _, local = tid.partition(":") if isinstance(tid, str) else ("", "", "")
        if prefix != "prism" or not _LOCAL.match(local):
            problems.append(f"{where}: TermID {tid!r} must be prism:<lowercase-slug>[.<specimen>]")
    return problems


def check_proposal(proposal: dict, registry: dict[str, dict], specimens: list[str]) -> tuple[list[dict], list[str]]:
    """Return (the new terms with Status "official", problems); checked together with the registry."""
    problems = _shape_problems(proposal)
    if problems:
        return [], problems
    terms = [{**t, "Status": "official"} for t in proposal["terms"]]
    merged = dict(registry)
    for term in terms:
        local = term["TermID"].partition(":")[2]
        if local in merged:
            problems.append(f"{term['TermID']} is already an official term")
        merged[local] = term
    if problems:
        return [], problems
    problems = check_terms.check_registry(merged, specimens)
    return ([] if problems else terms), problems
