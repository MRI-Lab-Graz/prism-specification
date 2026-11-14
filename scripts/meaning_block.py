"""Add the shared meaning block (schemas/shared/meaning-block.json) to a modality schema, in place as text.

The block is defined once; schemas/shared/meaning-locations.json names, per modality, the schema objects
whose `properties` receive it (column definitions get IsAbout, LevelIsAbout where Levels exist,
ValueMappings and TermURL; file-level objects get IsAbout). The schema files are hand-formatted, so the
script edits the text (the diff shows additions only) and refuses rather than re-dumping the file.
Stdlib only.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


def _sibling(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_patch = _sibling("release_patch")
ReleaseError = release_patch.ReleaseError
_TERMURL_LOOSE_KEYS = {"type", "description", "format"}


def load_block(shared_dir: Path) -> dict:
    return json.loads((Path(shared_dir) / "meaning-block.json").read_text(encoding="utf-8"))


def load_locations(shared_dir: Path) -> dict:
    return json.loads((Path(shared_dir) / "meaning-locations.json").read_text(encoding="utf-8"))


def fields(block: dict) -> dict:
    """{"column": {...}, "file": {...}} with every "<link>" placeholder written out in full."""
    def expand(value):
        if value == "<link>":
            return copy.deepcopy(block["link"])
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        return value
    return {"column": expand(block["column"]), "file": expand(block["file"])}


def _plan(schema: dict, modality: str, block: dict, locations: dict):
    """([(path, name, definition, replace)], problems): what stamp adds or replaces, and why it cannot."""
    where = locations.get("modalities", {}).get(modality)
    if where is None:
        reason = locations.get("pending", {}).get(modality)
        return [], [f"{modality}: pending ({reason})" if reason else f"{modality}: no meaning-block locations"]
    edits, problems, defs = [], [], fields(block)
    for kind in ("column", "file"):
        for path in where.get(kind, []):
            obj = schema
            try:
                for key in path:
                    obj = obj[key]
            except (KeyError, IndexError, TypeError):
                obj = None
            props = obj.get("properties") if isinstance(obj, dict) else None
            if not isinstance(props, dict):
                problems.append(f"{modality} {path}: not an object with properties")
                continue
            for name, definition in defs[kind].items():
                if name == "LevelIsAbout" and "Levels" not in props:
                    continue
                if name not in props:
                    edits.append((path, name, definition, False))
                elif props[name] == definition:
                    continue
                elif (name == "TermURL" and isinstance(props[name], dict) and props[name].get("type") == "string"
                      and set(props[name]) <= _TERMURL_LOOSE_KEYS):
                    edits.append((path, name, definition, True))
                else:
                    problems.append(f"{modality} {path}: {name} already has a different definition")
    return edits, problems


def _replace_in_style(text: str, keys: list, definition: dict) -> str:
    """Replace the value at `keys` with `definition`, indented like the line it sits on."""
    start, _ = release_patch._span(text, keys)
    line = text[text.rfind("\n", 0, start) + 1 : start]
    indent = line[: len(line) - len(line.lstrip())]
    newline = "\r\n" if "\r\n" in text else "\n"
    dumped = json.dumps(definition, indent=2, ensure_ascii=False).replace("\n", newline + indent)
    return release_patch._replace_value(text, keys, dumped)


def stamp(text: str, modality: str, block: dict, locations: dict) -> tuple[str, list[str]]:
    """The schema text with the missing block properties added, and the problems (text unchanged if any)."""
    schema = json.loads(text)
    edits, problems = _plan(schema, modality, block, locations)
    if problems or not edits:
        return text, problems
    expected, new = copy.deepcopy(schema), text
    try:
        for path, name, definition, replace in edits:
            target = expected
            for key in path:
                target = target[key]
            target["properties"][name] = definition
            if replace:
                new = _replace_in_style(new, [*path, "properties", name], definition)
        adds: dict = {}
        for path, name, definition, replace in edits:
            if not replace:
                adds.setdefault(tuple(path), {})[name] = definition
        for path, properties in adds.items():
            new = release_patch._extend_object(new, [*path, "properties"], properties)
    except (ValueError, IndexError):
        new = None
    if new is None or json.loads(new) != expected:
        return text, [f"{modality}: unusual layout, the text cannot be edited in place"]
    return new, []


def missing(text: str, modality: str, block: dict, locations: dict) -> list[str]:
    """One line per block property stamp would still add or replace (and per problem); empty: carries the block."""
    edits, problems = _plan(json.loads(text), modality, block, locations)
    return [f"{modality} {path}: {name}" + (" (replace)" if replace else "") for path, name, _, replace in edits] + problems


def release(source_root, dest_root, modality: str) -> list[str]:
    """Release `modality` with the block: archive the old schema, stamp, bump MINOR and $id, regenerate the page."""
    if not isinstance(modality, str) or not release_patch._MODALITY.fullmatch(modality):
        raise ReleaseError(f"{modality!r} is not a modality name")
    source, dest = Path(source_root), Path(dest_root)
    stable_rel = f"schemas/stable/{modality}.schema.json"
    if not (source / stable_rel).is_file():
        raise ReleaseError(f"no schema for modality {modality!r}")
    original = (source / stable_rel).read_bytes()
    text = original.decode("utf-8")
    schema = json.loads(text)

    match = release_patch._VERSION.fullmatch(str(schema.get("version")))
    if not match:
        raise ReleaseError(f"{stable_rel}: version {schema.get('version')!r} is not major.minor.patch")
    old = schema["version"]
    new = f"{match[1]}.{int(match[2]) + 1}.0"
    if not str(schema.get("$id", "")).endswith(f"/v{old}"):
        raise ReleaseError(f"{stable_rel}: $id {schema.get('$id')!r} does not end with /v{old}")
    archive_rel = f"schemas/archive/{modality}/{old}.schema.json"
    if (source / archive_rel).exists():
        raise ReleaseError(f"{archive_rel} is already archived")

    shared = source / "schemas" / "shared"
    block, locations = load_block(shared), load_locations(shared)
    if not missing(text, modality, block, locations):
        raise ReleaseError(f"{stable_rel} already carries the meaning block")
    stamped, problems = stamp(text, modality, block, locations)
    if problems:
        raise ReleaseError("; ".join(problems))
    new_id = schema["$id"][: -len(old)] + new
    try:
        edited = release_patch._replace_value(stamped, ["version"], json.dumps(new))
        edited = release_patch._replace_value(edited, ["$id"], json.dumps(new_id))
    except (ValueError, IndexError):
        raise ReleaseError(f"{stable_rel}: unusual layout, the version cannot be edited in place") from None
    expected = json.loads(stamped)
    expected["version"], expected["$id"] = new, new_id
    if json.loads(edited) != expected:
        raise ReleaseError(f"{stable_rel}: unusual layout, the version cannot be edited in place")

    written = [archive_rel, stable_rel]
    (dest / archive_rel).parent.mkdir(parents=True, exist_ok=True)
    (dest / archive_rel).write_bytes(original)
    (dest / stable_rel).parent.mkdir(parents=True, exist_ok=True)
    (dest / stable_rel).write_text(edited, encoding="utf-8", newline="")

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
