"""Check every instrument template under library/survey/.

Usage: python scripts/check_library.py [--repo DIR]
Prints one line per problem (naming the file) and exits 1 when there is any.
Rules: (a) Study.License quotes the rights holder, (b) Study.Source is an absolute https URL,
(c) Study.LicenseChecked is YYYY-MM-DD, (d) Study.LicenseTerms is a list of short strings,
(e) only the languages Study.LicenseLanguages names (the languages the quoted licence covers), (f) no Study.ItemCount, Study.Subscales or item Reversed.
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


def _langs(value, path, allowed, out):
    """Report language keys of the text fields below value that are not in allowed."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k in TEXT_FIELDS:
                # Levels maps a level to a text object; the others are the text object itself
                for text in (v.values() if k == "Levels" and isinstance(v, dict) else [v]):
                    if isinstance(text, dict):
                        out += [f"{path}{k}: language {x!r} is not in Study.LicenseLanguages" for x in text if x not in allowed]
            else:
                _langs(v, f"{path}{k}.", allowed, out)


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
    used = ([tech] if tech is not None else []) + list((data.get("I18n") or {}).get("Languages") or [])
    out += [f"language {x!r} is not in Study.LicenseLanguages" for x in used if x not in langs]
    _langs(data, "", langs, out)
    for k in ("License", "Citation"):
        if isinstance(study.get(k), dict):
            out += [f"Study.{k}: language {x!r} is not in Study.LicenseLanguages" for x in study[k] if x not in langs]
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
