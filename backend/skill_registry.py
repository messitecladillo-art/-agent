"""Read-only loader and search adapter for the repository Skill Registry v2.

The registry is the single discovery source for the modelling skills.  This
module deliberately returns metadata and bounded documentation pointers only:
it never executes a Skill, follows a link, scans the external materials
directory, or grants a write capability.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


REGISTRY_SCHEMA = "skill-registry/v2"
MANIFEST_SCHEMA = "skill-manifest/v2"
MAX_QUERY_CHARS = 240
MAX_RESULTS = 50
MAX_DESCRIPTION_CHARS = 500
# Keep contiguous Han phrases intact.  Splitting every Chinese character made
# a short query such as ``模型`` match almost the entire catalogue and made
# the ranking hard to explain.  Substring matching still handles a query that
# is shorter than a registered phrase without manufacturing noisy tokens.
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*|[\u4e00-\u9fff]+")


class SkillRegistryError(ValueError):
    """Raised when the versioned registry is missing or unsafe."""


def _safe_rel(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.replace("\\", "/")
    path = PurePosixPath(candidate)
    return not path.is_absolute() and ".." not in path.parts and not candidate.startswith("/")


class SkillRegistry:
    """Load, validate and query skills without mutating the checkout."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.skills_root = self.root / "skills"
        self.registry_path = self.skills_root / "registry.json"
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_revision: Optional[str] = None

    def _resolve(self, relative: str) -> Path:
        if not _safe_rel(relative):
            raise SkillRegistryError(f"unsafe registry path: {relative!r}")
        # Build from POSIX path components after validation.  This avoids
        # platform-dependent string replacement and lets us reject symlinks
        # before resolution (``Path.resolve()`` would otherwise hide them).
        parts = PurePosixPath(relative.replace("\\", "/")).parts
        raw_target = self.root.joinpath(*parts)
        cursor = self.root
        for part in parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise SkillRegistryError(f"symlinked registry resource is not allowed: {relative!r}")
        target = raw_target.resolve()
        if target != self.root and self.root not in target.parents:
            raise SkillRegistryError(f"registry path escapes repository: {relative!r}")
        return target

    def _read_json(self, path: Path, label: str) -> Dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SkillRegistryError(f"{label} cannot be read: {exc}") from exc
        if not isinstance(value, dict):
            raise SkillRegistryError(f"{label} must be an object")
        return value

    @staticmethod
    def _entries(registry: Mapping[str, Any]) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for section in ("skills", "workflows"):
            values = registry.get(section)
            if isinstance(values, list):
                output.extend(dict(item) for item in values if isinstance(item, Mapping))
        return output

    def _load(self) -> Dict[str, Any]:
        registry = self._read_json(self.registry_path, "skills/registry.json")
        if registry.get("schema_version") != REGISTRY_SCHEMA:
            raise SkillRegistryError(f"unsupported registry schema: {registry.get('schema_version')!r}")
        ledger_value = registry.get("source_ledger")
        if not isinstance(ledger_value, str):
            raise SkillRegistryError("registry source_ledger is missing")
        ledger_path = self._resolve(ledger_value)
        ledger = self._read_json(ledger_path, "skills/source-provenance.json")
        if ledger.get("schema_version") != "skill-source-ledger/v1":
            raise SkillRegistryError("unsupported source ledger schema")
        source_rows = ledger.get("sources")
        if not isinstance(source_rows, list) or not source_rows:
            raise SkillRegistryError("source ledger has no sources")
        source_ids: set[str] = set()
        for row in source_rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("id"), str):
                raise SkillRegistryError("source ledger contains an invalid source row")
            source_id = str(row["id"])
            if source_id in source_ids:
                raise SkillRegistryError(f"duplicate source id: {source_id}")
            source_ids.add(source_id)
        entries = self._entries(registry)
        ids: set[str] = set()
        dependency_map: Dict[str, List[str]] = {}
        for entry in entries:
            entry_id = entry.get("id")
            if not isinstance(entry_id, str) or not re.fullmatch(r"[a-z0-9-]+", entry_id):
                raise SkillRegistryError(f"invalid skill id: {entry_id!r}")
            if entry_id in ids:
                raise SkillRegistryError(f"duplicate skill id: {entry_id}")
            ids.add(entry_id)
            for key in ("path", "manifest"):
                value = entry.get(key)
                if not isinstance(value, str):
                    raise SkillRegistryError(f"{entry_id} missing {key}")
                path = self._resolve(value)
                if not path.is_file():
                    raise SkillRegistryError(f"{entry_id} resource missing: {value}")
            manifest = self._read_json(self._resolve(str(entry["manifest"])), f"{entry_id} manifest")
            if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("id") != entry_id:
                raise SkillRegistryError(f"{entry_id} manifest schema or id mismatch")
            declared_sources = manifest.get("source_ids")
            if not isinstance(declared_sources, list) or any(
                not isinstance(source_id, str) or source_id not in source_ids
                for source_id in declared_sources
            ):
                raise SkillRegistryError(f"{entry_id} manifest has an unknown source id")
            dependencies = manifest.get("depends_on", [])
            if not isinstance(dependencies, list) or any(
                not isinstance(dependency, str) for dependency in dependencies
            ):
                raise SkillRegistryError(f"{entry_id} manifest has invalid depends_on")
            dependency_map[entry_id] = list(dependencies)
            for ref_key in ("references", "scripts"):
                values = manifest.get(ref_key, [])
                if not isinstance(values, list):
                    raise SkillRegistryError(f"{entry_id} manifest.{ref_key} must be a list")
                for value in values:
                    if not isinstance(value, str):
                        raise SkillRegistryError(f"{entry_id} manifest.{ref_key} contains a non-string path")
                    resource = self._resolve(value)
                    if not resource.is_file():
                        raise SkillRegistryError(f"{entry_id} resource missing: {value}")
        for entry_id, dependencies in dependency_map.items():
            for dependency in dependencies:
                if dependency not in ids:
                    raise SkillRegistryError(f"{entry_id} has unknown dependency: {dependency}")
                if dependency == entry_id:
                    raise SkillRegistryError(f"{entry_id} has a self dependency")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise SkillRegistryError(f"dependency cycle detected at {node}")
            if node in visited:
                return
            visiting.add(node)
            for dependency in dependency_map.get(node, []):
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for entry_id in dependency_map:
            visit(entry_id)
        return registry

    def _resource_paths(self, registry: Mapping[str, Any]) -> List[Path]:
        paths = [self.registry_path]
        ledger_value = registry.get("source_ledger")
        if isinstance(ledger_value, str):
            paths.append(self._resolve(ledger_value))
        for entry in self._entries(registry):
            for key in ("path", "manifest"):
                paths.append(self._resolve(str(entry[key])))
            manifest = self._read_json(self._resolve(str(entry["manifest"])), f"{entry['id']} manifest")
            for key in ("references", "scripts"):
                values = manifest.get(key, [])
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, str):
                            candidate = self._resolve(value)
                            if candidate.is_file():
                                paths.append(candidate)
        return list(dict.fromkeys(paths))

    def _hash_paths(self, paths: Sequence[Path]) -> str:
        digest = hashlib.sha256()
        for path in sorted(paths, key=lambda item: item.as_posix().lower()):
            # The caller supplies paths from one repository root.  Hashing a
            # relative POSIX name keeps the revision portable across Windows
            # checkouts and Linux CI runners.
            try:
                name = path.relative_to(self.root).as_posix()
            except ValueError as exc:
                raise SkillRegistryError(f"resource is outside repository: {path}") from exc
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def _snapshot_base(self) -> Dict[str, Any]:
        registry = self._load()
        revision = "skill:" + self._hash_paths(self._resource_paths(registry))
        snapshot = copy.deepcopy(registry)
        snapshot["registry_revision"] = revision
        snapshot["registry_schema"] = REGISTRY_SCHEMA
        # Expose only the small, already curated provenance ledger.  Full
        # external material paths and contents never enter the API response.
        ledger_path = self._resolve(str(snapshot["source_ledger"]))
        ledger = self._read_json(ledger_path, "skills/source-provenance.json")
        snapshot["source_provenance"] = {
            "schema_version": ledger.get("schema_version"),
            "inventory_revision": ledger.get("inventory_revision"),
            "source_manifest_sha256": ledger.get("source_manifest_sha256"),
            "source_count": len(ledger.get("sources", [])) if isinstance(ledger.get("sources"), list) else 0,
            "external_root": "OWNER_LOCAL_ONLY",
        }
        snapshot["counts"] = {
            "skills": len(snapshot.get("skills", [])) if isinstance(snapshot.get("skills"), list) else 0,
            "workflows": len(snapshot.get("workflows", [])) if isinstance(snapshot.get("workflows"), list) else 0,
            "method_families": len(snapshot.get("method_families", [])) if isinstance(snapshot.get("method_families"), list) else 0,
            "sources": snapshot["source_provenance"]["source_count"],
        }
        return snapshot

    def snapshot(self) -> Dict[str, Any]:
        """Return a detached, JSON-safe registry snapshot."""
        return self._snapshot_base()

    @staticmethod
    def _tokens(text: str) -> List[str]:
        return [token.lower() for token in TOKEN_RE.findall(text[:MAX_QUERY_CHARS]) if token.strip()]

    def search(self, query: str = "", *, limit: int = 12) -> Dict[str, Any]:
        snapshot = self._snapshot_base()
        query_text = str(query or "").strip()[:MAX_QUERY_CHARS]
        tokens = self._tokens(query_text)
        bounded_limit = max(1, min(int(limit), MAX_RESULTS))
        rows: List[Dict[str, Any]] = []
        for entry in self._entries(snapshot):
            haystack = " ".join(str(entry.get(key, "")) for key in ("id", "name", "phase", "trigger")).lower()
            score = 0
            matched: List[str] = []
            for token in tokens:
                if token in haystack:
                    score += 3 if token in str(entry.get("id", "")).lower() else 1
                    matched.append(token)
            if tokens and score == 0:
                continue
            row = {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "phase": entry.get("phase"),
                "trigger": entry.get("trigger"),
                "path": entry.get("path"),
                "manifest": entry.get("manifest"),
                "status": entry.get("status", "ACTIVE"),
                "score": score if tokens else 0,
                "matched_tokens": list(dict.fromkeys(matched)),
            }
            rows.append(row)
        rows.sort(key=lambda item: (-int(item["score"]), str(item.get("phase", "")), str(item.get("id", ""))))
        return {
            "schema_version": "skill-search/v1",
            "query": query_text,
            "registry_revision": snapshot["registry_revision"],
            "results": rows[:bounded_limit],
            "total_matches": len(rows),
        }

    def get(self, skill_id: str) -> Dict[str, Any]:
        candidate = str(skill_id or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9-]+", candidate):
            raise SkillRegistryError("invalid skill id")
        snapshot = self._snapshot_base()
        entry = next((item for item in self._entries(snapshot) if item.get("id") == candidate), None)
        if entry is None:
            raise KeyError(candidate)
        manifest = self._read_json(self._resolve(str(entry["manifest"])), f"{candidate} manifest")
        skill_path = self._resolve(str(entry["path"]))
        text = skill_path.read_text(encoding="utf-8", errors="replace")
        body = text.split("---", 2)[-1].strip() if "---" in text else text
        # The endpoint exposes only a bounded preview; callers should use the
        # repository catalog or a declared artifact for full text.
        preview = body[:MAX_DESCRIPTION_CHARS]
        return {
            "schema_version": "skill-detail/v1",
            "registry_revision": snapshot["registry_revision"],
            "entry": entry,
            "manifest": manifest,
            "preview": preview,
            "read_only": True,
            "execution": "not_performed",
        }


__all__ = ["REGISTRY_SCHEMA", "MANIFEST_SCHEMA", "SkillRegistry", "SkillRegistryError"]
