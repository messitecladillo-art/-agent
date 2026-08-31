"""Read-only catalogue and lexical search over the collaboration workspace.

The catalogue is intentionally separate from :mod:`knowledge_base`: it mounts
only versioned repository context (skills, notes, docs, workflows, and the
project control files) into an Agent prompt.  It never follows links, opens
the user's external materials directory, executes a file, or returns absolute
paths.  Every response carries a deterministic manifest digest and source refs
so an Agent can acknowledge exactly which workspace revision it saw.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union


REPO_CATALOG_SCHEMA = "workspace-catalog/v1"
DEFAULT_ALLOWED_FILES = frozenset({
    "README.md", "TASKS.md", "AGENTS.md", "app.js", "index.html", "styles.css",
    "docker-compose.yml",
})
DEFAULT_ALLOWED_DIRS = frozenset({
    "docs", "skills", "notes", "workflows", "models", "paper", "viz",
    "scripts", "experiments", "backend", "assets",
})
DEFAULT_EXCLUDED_NAMES = frozenset({".git", ".collab", "runtime", ".env", ".venv", "__pycache__"})
# A repository directory may contain source code and still be unsafe to mount
# wholesale.  Filename-level secrets are rejected in addition to dotfiles so
# a mistakenly committed credential helper cannot become prompt context.
SENSITIVE_NAME_RE = re.compile(
    r"(?:^|[._-])(secret|secrets|credential|credentials|password|passwd|token|api[_-]?key|private[_-]?key)(?:[._-]|$)",
    flags=re.IGNORECASE,
)
TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".rst", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".csv", ".tsv", ".py", ".js", ".ts", ".tsx",
    ".jsx", ".css", ".html", ".htm", ".tex", ".ltx", ".sql", ".sh", ".ps1",
    ".bat", ".m", ".r", ".rmd", ".xml", ".log",
})
MAX_ITEMS = 5000
MAX_QUERY_CHARS = 240
MAX_TEXT_BYTES = 1 * 1024 * 1024
MAX_HASH_BYTES = 16 * 1024 * 1024
MAX_SNIPPET_CHARS = 320
MAX_SOURCE_REFS = 5000
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class CatalogPathError(ValueError):
    """Raised when a caller attempts to leave the allowlisted workspace."""


def _safe_rel_path(raw: str) -> PurePosixPath:
    """Validate a user-supplied relative POSIX path without resolving it."""

    if not isinstance(raw, str) or not raw.strip():
        raise CatalogPathError("path must be a non-empty relative path")
    value = raw.strip().replace("\\", "/")
    if "\x00" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise CatalogPathError("absolute or NUL paths are not allowed")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise CatalogPathError("path traversal is not allowed")
    return path


def _contains_allowed_root(path: PurePosixPath, allowed_files: Sequence[str], allowed_dirs: Sequence[str]) -> bool:
    first = path.parts[0] if path.parts else ""
    return first in allowed_files or first in allowed_dirs


class WorkspaceCatalog:
    """Bounded metadata index over the repository itself."""

    def __init__(
        self,
        root: Optional[Union[str, os.PathLike]] = None,
        *,
        allowed_files: Iterable[str] = DEFAULT_ALLOWED_FILES,
        allowed_dirs: Iterable[str] = DEFAULT_ALLOWED_DIRS,
        excluded_names: Iterable[str] = DEFAULT_EXCLUDED_NAMES,
        max_items: int = MAX_ITEMS,
    ) -> None:
        self.root = Path(root or Path(__file__).resolve().parents[1]).resolve()
        self.allowed_files = frozenset(str(name) for name in allowed_files)
        self.allowed_dirs = frozenset(str(name) for name in allowed_dirs)
        self.excluded_names = frozenset(str(name) for name in excluded_names)
        self.max_items = max(1, min(int(max_items), MAX_ITEMS))

    def _is_safe_file(self, path: Path) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        if SENSITIVE_NAME_RE.search(path.name):
            return False
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.root)
        except (OSError, ValueError):
            return False
        rel = PurePosixPath(path.relative_to(self.root).as_posix())
        if not rel.parts or not _contains_allowed_root(rel, self.allowed_files, self.allowed_dirs):
            return False
        return not any(part in self.excluded_names or part.startswith(".") for part in rel.parts)

    @staticmethod
    def _kind(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in TEXT_EXTENSIONS:
            return "text"
        if suffix in {".pdf"}:
            return "pdf"
        if suffix in {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}:
            return "office"
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
            return "asset"
        return "binary"

    @staticmethod
    def _hash_file(path: Path, size: int) -> tuple[str, str]:
        if size > MAX_HASH_BYTES:
            return "", "SKIPPED_SIZE"
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            return "", "UNREADABLE"
        return digest.hexdigest(), "HASHED"

    def _iter_files(self) -> tuple[List[Path], List[str]]:
        files: List[Path] = []
        warnings: List[str] = []
        if not self.root.is_dir():
            return files, ["workspace root is unavailable"]
        try:
            children = sorted(self.root.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            return files, ["workspace root cannot be listed"]
        for child in children:
            if child.name in self.excluded_names or child.name.startswith("."):
                continue
            if child.is_symlink():
                continue
            if child.is_file() and child.name in self.allowed_files:
                if self._is_safe_file(child):
                    files.append(child)
                continue
            if not child.is_dir() or child.name not in self.allowed_dirs:
                continue
            try:
                for path in sorted(child.rglob("*"), key=lambda item: item.as_posix().lower()):
                    if len(files) >= self.max_items:
                        warnings.append(f"item limit reached ({self.max_items})")
                        return files, warnings
                    if path.name in self.excluded_names or path.name.startswith("."):
                        continue
                    if self._is_safe_file(path):
                        files.append(path)
            except OSError:
                warnings.append(f"directory could not be fully listed: {child.name}")
        return files, warnings

    def _item(self, path: Path) -> Dict[str, Any]:
        rel = PurePosixPath(path.relative_to(self.root).as_posix())
        try:
            stat = path.stat()
            size = int(stat.st_size)
            mtime_ns = int(stat.st_mtime_ns)
        except OSError:
            size, mtime_ns = 0, 0
        file_hash, hash_status = self._hash_file(path, size)
        kind = self._kind(path)
        source_ref = f"repo:{rel.as_posix()}"
        return {
            "path": rel.as_posix(),
            "path_rel": rel.as_posix(),
            "name": path.name,
            "extension": path.suffix.lower(),
            "kind": kind,
            "size_bytes": size,
            "hash": file_hash,
            "hash_status": hash_status,
            "text_searchable": kind == "text" and size <= MAX_TEXT_BYTES,
            "source_ref": source_ref,
            "claim_class": "observed",
            "mtime_ns": mtime_ns,
        }

    @staticmethod
    def _manifest(items: Sequence[Mapping[str, Any]]) -> str:
        rows = [
            {
                "path": row.get("path_rel", ""),
                "size_bytes": row.get("size_bytes", 0),
                "hash": row.get("hash", ""),
                "hash_status": row.get("hash_status", ""),
                "mtime_ns": row.get("mtime_ns", 0),
            }
            for row in items
        ]
        payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def catalog(self) -> Dict[str, Any]:
        files, warnings = self._iter_files()
        items = [self._item(path) for path in files]
        items.sort(key=lambda row: str(row["path_rel"]).lower())
        manifest_sha = self._manifest(items)
        source_refs = [str(row["source_ref"]) for row in items[:MAX_SOURCE_REFS]]
        counts: Dict[str, int] = {"items": len(items), "text": 0, "binary": 0, "pdf": 0, "office": 0, "asset": 0, "searchable": 0}
        for row in items:
            counts[str(row["kind"])] = counts.get(str(row["kind"]), 0) + 1
            if row.get("text_searchable"):
                counts["searchable"] += 1
        return {
            "schema_version": REPO_CATALOG_SCHEMA,
            "manifest_sha": f"sha256:{manifest_sha}",
            "manifest_sha256": f"sha256:{manifest_sha}",
            "root": ".",
            "allowlist": {"files": sorted(self.allowed_files), "directories": sorted(self.allowed_dirs)},
            "excluded": sorted(self.excluded_names),
            "items": items,
            "counts": counts,
            "source_refs": source_refs,
            "warnings": warnings,
        }

    def _read_text(self, path: Path) -> str:
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                return ""
            return path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError):
            return ""

    @staticmethod
    def _snippet(text: str, query: str) -> str:
        folded = text.casefold()
        needle = query.casefold()
        position = folded.find(needle)
        if position < 0:
            return text[:MAX_SNIPPET_CHARS].strip()
        start = max(0, position - 100)
        end = min(len(text), position + len(query) + 180)
        snippet = text[start:end].replace("\r", " ").replace("\n", " ")
        return snippet[:MAX_SNIPPET_CHARS].strip()

    def search(self, query: str = "", *, top_k: int = 20, path: Optional[str] = None) -> Dict[str, Any]:
        query = (query or "").strip()[:MAX_QUERY_CHARS]
        limit = max(1, min(int(top_k), 50))
        catalog = self.catalog()
        path_filter: Optional[PurePosixPath] = None
        if path is not None:
            path_filter = _safe_rel_path(path)
            if not _contains_allowed_root(path_filter, self.allowed_files, self.allowed_dirs):
                raise CatalogPathError("path is outside the workspace allowlist")
        candidates = [row for row in catalog["items"] if path_filter is None or PurePosixPath(str(row["path_rel"])).is_relative_to(path_filter)]
        results: List[Dict[str, Any]] = []
        query_folded = query.casefold()
        for row in candidates:
            path_obj = self.root / str(row["path_rel"])
            metadata = " ".join(str(row.get(key, "")) for key in ("name", "path_rel", "kind", "extension"))
            metadata_match = not query or query_folded in metadata.casefold()
            body_match = False
            snippet = ""
            if query and row.get("text_searchable"):
                body = self._read_text(path_obj)
                body_match = query_folded in body.casefold()
                if body_match:
                    snippet = self._snippet(body, query)
            if not query or metadata_match or body_match:
                hit = dict(row)
                hit.update({"match_source": "body" if body_match else ("metadata" if query else "browse"), "snippet": snippet})
                results.append(hit)
            if len(results) >= limit:
                break
        return {
            "schema_version": "workspace-search/v1",
            "manifest_sha": catalog["manifest_sha"],
            "manifest_sha256": catalog["manifest_sha"],
            "query": query,
            "path": path_filter.as_posix() if path_filter else None,
            "items": results,
            "results": results,
            "returned_count": len(results),
            "total_candidates": len(candidates),
            "counts": catalog["counts"],
            "source_refs": [row["source_ref"] for row in results],
            "warnings": catalog["warnings"],
            "retrieval_boundary": {
                "max_query_chars": MAX_QUERY_CHARS,
                "max_text_bytes": MAX_TEXT_BYTES,
                "top_k_limit": 50,
                "allowlist_only": True,
            },
        }


__all__ = ["CatalogPathError", "WorkspaceCatalog", "REPO_CATALOG_SCHEMA"]
