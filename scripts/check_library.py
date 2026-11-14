"""Check every instrument template under library/survey/.

Usage: python scripts/check_library.py [--repo DIR]
Prints one line per problem (naming the file) and exits 1 when there is any.
Rules: (a) Study.License quotes the rights holder, (b) Study.Source is an absolute https URL,
(c) Study.LicenseChecked is YYYY-MM-DD, (d) Study.LicenseTerms is a list of short strings,
(e) only languages named in Study.LicenseLanguages, (f) no Study.ItemCount, Study.Subscales or item Reversed.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

TEXT_FIELDS = ("Description", "Levels", "Instructions", "OriginalName")
LANG = re.compile(r"[a-z]{2,3}")
NON_ITEMS = ("Technical", "Metadata", "I18n", "Study", "Normative")
QUOTE = re.compile(r'["“][^"”]{10,}["”]')


def _langs(value, path, allowed, out, level_map=False):
    """Report language keys, in any dict below value whose keys all look like language codes, that are not allowed."""
    if isinstance(value, list):
        for i, v in enumerate(value):
            _langs(v, f"{path}{i}.", allowed, out)
    elif isinstance(value, dict):
        if value and not level_map and all(LANG.fullmatch(k) for k in value):
            out += [f"{path.rstrip('.')}: language {k!r} is not in Study.LicenseLanguages" for k in value if k not in allowed]
        for k, v in value.items():
            if not (path == "" and k in ("Technical", "I18n")):
                # keys of a Levels map are level codes (a level 'no' is not a language)
                _langs(v, f"{path}{k}.", allowed, out, level_map=(k == "Levels"))


def template_problems(data: dict) -> list[str]:
    study = data.get("Study") or {}
    out = []
    lic = study.get("License")
    lic = " ".join(map(str, lic.values())) if isinstance(lic, dict) else lic
    if not (isinstance(lic, str) and QUOTE.search(lic)):
        out.append("Study.License must quote the rights holder's statement")
    src = study.get("Source")
    u = urlparse(src) if isinstance(src, str) else None
    if not (u and u.scheme == "https" and u.netloc):
        out.append("Study.Source must be an absolute https URL")
    checked = study.get("LicenseChecked")
    try:
        ok = isinstance(checked, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked)
        ok = ok and datetime.date.fromisoformat(checked)
    except ValueError:
        ok = False
    if not ok:
        out.append("Study.LicenseChecked must be a date YYYY-MM-DD")
    terms = study.get("LicenseTerms")
    if not (isinstance(terms, list) and terms and all(isinstance(t, str) and 0 < len(t) <= 300 for t in terms)):
        out.append("Study.LicenseTerms must be a non-empty list of short strings")
    langs = study.get("LicenseLanguages")
    if not (isinstance(langs, list) and langs and all(isinstance(x, str) and LANG.fullmatch(x) for x in langs)):
        out.append("Study.LicenseLanguages must be a non-empty list of language codes such as ['en']")
        langs = []
    tech = (data.get("Technical") or {}).get("Language")
    i18n = (data.get("I18n") or {}).get("Languages")
    if not isinstance(tech, str):
        out.append("Technical.Language must be set (a string)")
    if not isinstance(i18n, list):
        out.append("I18n.Languages must be set and must be a list")
    used = ([tech] if isinstance(tech, str) else []) + (i18n if isinstance(i18n, list) else [])
    out += [f"language {x!r} is not in Study.LicenseLanguages" for x in used if x not in langs]
    _langs(data, "", langs, out)
    for key in ("ItemCount", "Subscales"):
        if key in study:
            out.append(f"Study.{key} must not be set")
    out += [f"{k}.Reversed must not be set" for k, v in data.items()
            if k not in NON_ITEMS and isinstance(v, dict) and "Reversed" in v]
    return out


def check(repo: Path) -> list[str]:
    lines = []
    for f in sorted((Path(repo) / "library" / "survey").glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            lines.append(f"{f.name}: not valid JSON ({exc})")
            continue
        lines += [f"{f.name}: {p}" for p in template_problems(data)]
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    lines = check(Path(ap.parse_args(argv).repo))
    print("\n".join(lines))
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
