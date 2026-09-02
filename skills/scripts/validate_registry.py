#!/usr/bin/env python3
"""Validate the repository mathematical-modelling skill registry.

The validator is intentionally dependency-free and read-only.  It checks the
machine-readable registry, manifests, frontmatter, referenced resources and
legacy-entrypoint absence.  It does not execute a skill or any material-pack
code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


REGISTRY_NAME = "registry.json"
SCHEMA = "skill-registry/v2"
MANIFEST_SCHEMA = "skill-manifest/v2"
SOURCE_LEDGER_SCHEMA = "skill-source-ledger/v1"
NAME_RE = re.compile(r"^[a-z0-9-]+$")
SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", re.S)
FRONT_FIELD_RE = re.compile(r"^(name|description):\s*(.*)$")
LEGACY_MARKERS = (
    "skills/01-审题破题.md",
    "skills/02-模型选型与建模.md",
    "skills/03-求解与实现.md",
    "skills/04-验证与灵敏度分析.md",
    "skills/05-论文写作.md",
    "skills/06-论文评审与终检.md",
    "skills/07-范文精析.md",
    "skills/08-美赛专项.md",
    "skills/workflow-比赛主流程.md",
    "skills/workflow-赛前冲刺流程.md",
    "skills/math-modeling-mathematical-writing",
    "skills/mhagent-evidence-reconstruction",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _safe_rel(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and not value.startswith("/")


def _resolve(root: Path, value: str) -> Path:
    if not _safe_rel(value):
        raise ValueError(f"unsafe relative path: {value!r}")
    root_resolved = root.resolve()
    parts = PurePosixPath(value.replace("\\", "/")).parts
    raw_target = root_resolved.joinpath(*parts)
    cursor = root_resolved
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"symlinked registry resource is not allowed: {value!r}")
    target = raw_target.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"path escapes repository: {value!r}")
    return target


def _frontmatter(path: Path) -> Tuple[Dict[str, str], List[str]]:
    errors: List[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return {}, [f"{path}: unreadable: {exc}"]
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, [f"{path}: missing YAML frontmatter"]
    fields: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        field = FRONT_FIELD_RE.match(line.strip())
        if field:
            key, value = field.groups()
            fields[key] = value.strip().strip("\"'")
    for required in ("name", "description"):
        if not fields.get(required):
            errors.append(f"{path}: frontmatter missing {required}")
    name = fields.get("name", "")
    if name and (not NAME_RE.fullmatch(name) or len(name) > 64):
        errors.append(f"{path}: invalid skill name {name!r}")
    if "[TODO:" in fields.get("description", "") or "[TODO:" in text:
        errors.append(f"{path}: unfinished TODO placeholder")
    return fields, errors


def _load_json(path: Path, label: str, errors: List[str]) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{label}: invalid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label}: root must be an object")
        return {}
    return value


def _iter_entries(registry: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for section in ("skills", "workflows"):
        entries = registry.get(section, [])
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, dict):
                    yield item


def _hash_files(paths: Sequence[Path], root: Path) -> str:
    digest = hashlib.sha256()
    unique = list(dict.fromkeys(paths))
    for path in sorted(unique, key=lambda p: p.as_posix().lower()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate(root: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    skills_root = root / "skills"
    registry_path = skills_root / REGISTRY_NAME
    registry = _load_json(registry_path, str(registry_path), errors)

    # The source ledger is a small, repository-safe abstraction of the
    # external materials pack.  Validating it here prevents a manifest from
    # silently pointing at an invented or misspelled source id.
    ledger_path: Path | None = None
    source_ids: set[str] = set()
    ledger_value = registry.get("source_ledger")
    try:
        ledger_path = _resolve(root, ledger_value)
    except (TypeError, ValueError) as exc:
        errors.append(f"source_ledger: {exc}")
    if ledger_path is not None and not ledger_path.is_file():
        errors.append(f"source_ledger missing: {ledger_value}")
    elif ledger_path is not None:
        resource_files: List[Path] = [registry_path, ledger_path]
        ledger = _load_json(ledger_path, str(ledger_path), errors)
        if ledger.get("schema_version") != SOURCE_LEDGER_SCHEMA:
            errors.append(f"source ledger schema must be {SOURCE_LEDGER_SCHEMA!r}")
        sources = ledger.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append("source ledger sources must be a non-empty list")
            sources = []
        for index, source in enumerate(sources):
            if not isinstance(source, Mapping):
                errors.append(f"source ledger sources[{index}] must be an object")
                continue
            source_id = source.get("id")
            if not isinstance(source_id, str) or not NAME_RE.fullmatch(source_id.replace("_", "-")):
                errors.append(f"source ledger sources[{index}].id is invalid")
            elif source_id in source_ids:
                errors.append(f"duplicate source id: {source_id}")
            else:
                source_ids.add(source_id)
            digest = source.get("sha256")
            if not isinstance(digest, str) or not (SHA256_RE.fullmatch(digest) or digest.startswith(("materials-index:", "notes:"))):
                errors.append(f"source ledger sources[{index}].sha256 must be a digest or declared index reference")
            for key in ("kind", "label", "confidence", "supports", "limitations"):
                if key not in source:
                    errors.append(f"source ledger sources[{index}] missing {key}")
                elif key in {"supports", "limitations"} and not isinstance(source.get(key), list):
                    errors.append(f"source ledger sources[{index}].{key} must be a list")
        resource_files = list(dict.fromkeys(resource_files))
    else:
        resource_files = [registry_path]

    if registry.get("schema_version") != SCHEMA:
        errors.append(f"registry schema must be {SCHEMA!r}")
    if not isinstance(registry.get("version"), str):
        errors.append("registry.version must be a string")
    policy = registry.get("policy")
    if not isinstance(policy, dict):
        errors.append("registry.policy must be an object")
    else:
        for field in ("claim_classes", "statuses", "mandatory_invariants"):
            if not isinstance(policy.get(field), list) or not policy[field]:
                errors.append(f"registry.policy.{field} must be a non-empty list")

    entries = list(_iter_entries(registry))
    ids: set[str] = set()
    tracked_dirs: set[Path] = set()
    manifest_by_id: Dict[str, Mapping[str, Any]] = {}
    # Keep the ledger in the revision hash when it was available above.
    resource_files = list(dict.fromkeys(resource_files))
    for entry in entries:
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not NAME_RE.fullmatch(entry_id):
            errors.append(f"invalid registry entry id: {entry_id!r}")
            continue
        if entry_id in ids:
            errors.append(f"duplicate registry id: {entry_id}")
        ids.add(entry_id)
        if entry.get("status") not in {"ACTIVE", "DRAFT", "STALE", "BLOCKED"}:
            errors.append(f"{entry_id}: invalid registry status")
        path_value = entry.get("path")
        manifest_value = entry.get("manifest")
        try:
            entry_path = _resolve(root, path_value)
            manifest_path = _resolve(root, manifest_value)
        except (TypeError, ValueError) as exc:
            errors.append(f"{entry_id}: {exc}")
            continue
        if entry_path.name != "SKILL.md":
            errors.append(f"{entry_id}: path must end in SKILL.md")
        if not entry_path.exists():
            errors.append(f"{entry_id}: missing entrypoint {path_value}")
        else:
            resource_files.append(entry_path)
            fields, front_errors = _frontmatter(entry_path)
            errors.extend(front_errors)
            if fields.get("name") != entry_path.parent.name:
                errors.append(f"{entry_id}: frontmatter name must match folder {entry_path.parent.name!r}")
        if not manifest_path.exists():
            errors.append(f"{entry_id}: missing manifest {manifest_value}")
        else:
            resource_files.append(manifest_path)
            manifest = _load_json(manifest_path, str(manifest_path), errors)
            manifest_by_id[entry_id] = manifest
            if manifest.get("schema_version") != MANIFEST_SCHEMA:
                errors.append(f"{entry_id}: manifest schema must be {MANIFEST_SCHEMA!r}")
            if manifest.get("id") != entry_id:
                errors.append(f"{entry_id}: manifest id mismatch")
            if manifest.get("entrypoint") != path_value:
                errors.append(f"{entry_id}: manifest entrypoint mismatch")
            for key in ("inputs", "outputs", "depends_on", "gates", "source_ids"):
                if not isinstance(manifest.get(key), list):
                    errors.append(f"{entry_id}: manifest.{key} must be a list")
            if isinstance(manifest.get("source_ids"), list):
                for source_id in manifest["source_ids"]:
                    if not isinstance(source_id, str) or source_id not in source_ids:
                        errors.append(f"{entry_id}: unknown source_id {source_id!r}")
            for ref_key in ("references", "scripts"):
                values = manifest.get(ref_key, [])
                if not isinstance(values, list):
                    errors.append(f"{entry_id}: manifest.{ref_key} must be a list")
                    continue
                for ref in values:
                    try:
                        ref_path = _resolve(root, ref)
                    except (TypeError, ValueError) as exc:
                        errors.append(f"{entry_id}: {exc}")
                        continue
                    if not ref_path.exists():
                        errors.append(f"{entry_id}: missing {ref_key[:-1]} {ref}")
                    else:
                        resource_files.append(ref_path)
            for boundary in manifest.get("write_boundary", []) if isinstance(manifest.get("write_boundary"), list) else []:
                if not _safe_rel(boundary):
                    errors.append(f"{entry_id}: unsafe write_boundary {boundary!r}")
            if not isinstance(manifest.get("capabilities"), list) or not manifest.get("capabilities"):
                errors.append(f"{entry_id}: manifest.capabilities must be a non-empty list")
        tracked_dirs.add(entry_path.parent.resolve())

    # Dependencies are IDs, never paths.  Check both existence and acyclicity
    # so an adapter cannot start from a partially ordered skill graph.
    dependency_map: Dict[str, List[str]] = {}
    for entry_id, manifest in manifest_by_id.items():
        dependencies = manifest.get("depends_on", [])
        if not isinstance(dependencies, list):
            continue
        dependency_map[entry_id] = []
        for dependency in dependencies:
            if not isinstance(dependency, str) or dependency not in ids:
                errors.append(f"{entry_id}: unknown dependency {dependency!r}")
            elif dependency == entry_id:
                errors.append(f"{entry_id}: self dependency")
            else:
                dependency_map[entry_id].append(dependency)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"dependency cycle detected at {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in dependency_map.get(node, []):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for entry_id in dependency_map:
        visit(entry_id)

    # Every real skill folder must be registered.  This catches a half-deleted
    # legacy directory as well as an accidentally untracked new skill.
    if skills_root.exists():
        for entrypoint in skills_root.glob("*/SKILL.md"):
            if entrypoint.parent.resolve() not in tracked_dirs:
                errors.append(f"unregistered skill directory: {entrypoint.parent.relative_to(root)}")
        for marker in LEGACY_MARKERS:
            marker_path = root / Path(marker.replace("/", "\\"))
            # Empty cache directories left by a prior Python run are not
            # repository skills; only a legacy entrypoint or populated legacy
            # skill directory should fail the migration gate.
            legacy_entrypoint = marker_path / "SKILL.md" if marker_path.is_dir() else marker_path
            if legacy_entrypoint.is_file():
                errors.append(f"legacy skill entrypoint still exists: {marker}")

    # Active entrypoints must not instruct callers to use removed paths.
    for entrypoint in (p for p in resource_files if p.name == "SKILL.md" and p.exists()):
        text = entrypoint.read_text(encoding="utf-8", errors="replace")
        for marker in LEGACY_MARKERS:
            if marker in text:
                errors.append(f"{entrypoint}: active entrypoint contains legacy reference {marker}")

    result = {
        "schema_version": "skill-registry-validation/v1",
        "registry": str(registry_path.relative_to(root)).replace("\\", "/"),
        "entry_count": len(entries),
        "skill_count": len(registry.get("skills", [])) if isinstance(registry.get("skills"), list) else 0,
        "workflow_count": len(registry.get("workflows", [])) if isinstance(registry.get("workflows"), list) else 0,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "valid": not errors,
    }
    if registry_path.exists():
        try:
            result["registry_revision"] = "skill:" + _hash_files(resource_files, root.resolve())
        except OSError as exc:
            result["errors"].append(f"hash failed: {exc}")
            result["valid"] = False
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None, help="repository root")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    result = validate((args.root or _repo_root()).resolve())
    if args.strict and result["warnings"]:
        result["errors"].extend(result["warnings"])
        result["valid"] = False
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"registry valid={result['valid']} entries={result['entry_count']} revision={result.get('registry_revision','')}")
        for label in ("errors", "warnings"):
            for item in result[label]:
                print(f"{label[:-1].upper()}: {item}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
