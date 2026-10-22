"""Turn a schema patch into a reviewable schema release.

The release procedure CONTRIBUTING.md describes, done by a script: archive the current stable schema
unchanged, apply the patch to the stable schema, bump its MINOR version (and the `$id` suffix), and
regenerate the field tables of the modality's spec page. The result passes scripts/check_schema_versions.py.
Reads from `source_root`, writes only what changed to `dest_root` (the same folder, or a bundle).
Stdlib only.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

_MODALITY = re.compile(r"[a-z][a-z0-9]*")
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _sibling(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schema_patch = _sibling("schema_patch")
PatchError = schema_patch.PatchError


class ReleaseError(ValueError):
    """The release cannot be prepared; the message says why."""


def release(source_root, dest_root, modality: str, patch) -> list[str]:
    """Prepare the release; returns the repository-relative paths written under `dest_root`."""
    if not isinstance(modality, str) or not _MODALITY.fullmatch(modality):
        raise ReleaseError(f"{modality!r} is not a modality name")
    source, dest = Path(source_root), Path(dest_root)
    stable_rel = f"schemas/stable/{modality}.schema.json"
    stable_path = source / stable_rel
    if not stable_path.is_file():
        raise ReleaseError(f"no schema for modality {modality!r}")
    original = stable_path.read_bytes()
    schema = json.loads(original.decode("utf-8"))

    patched, _notes = schema_patch.apply_patch(schema, patch)  # PatchError: invalid, or nothing to add

    match = _VERSION.fullmatch(str(schema.get("version")))
    if not match:
        raise ReleaseError(f"{stable_rel}: version {schema.get('version')!r} is not major.minor.patch")
    old = schema["version"]
    new = f"{match[1]}.{int(match[2]) + 1}.0"
    if not str(schema.get("$id", "")).endswith(f"/v{old}"):
        raise ReleaseError(f"{stable_rel}: $id {schema.get('$id')!r} does not end with /v{old}")
    patched["version"] = new
    patched["$id"] = schema["$id"][: -len(old)] + new

    archive_rel = f"schemas/archive/{modality}/{old}.schema.json"
    if (source / archive_rel).exists():
        raise ReleaseError(f"{archive_rel} is already archived")

    written = [archive_rel, stable_rel]
    (dest / archive_rel).parent.mkdir(parents=True, exist_ok=True)
    (dest / archive_rel).write_bytes(original)
    (dest / stable_rel).parent.mkdir(parents=True, exist_ok=True)
    (dest / stable_rel).write_text(json.dumps(patched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    page_rel = f"specs/{modality}.md"
    if (source / page_rel).is_file():
        (dest / page_rel).parent.mkdir(parents=True, exist_ok=True)
        if dest != source:
            (dest / page_rel).write_bytes((source / page_rel).read_bytes())
        _sibling("generate_schema_reference").sync(
            write=True, schemas=dest / "schemas" / "stable", specs=dest / "specs", pages={modality: f"{modality}.md"}
        )
        written.append(page_rel)
    return written
