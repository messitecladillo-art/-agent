"""Small local API for the G-CUP MAS prototype.

This is intentionally an offline-first development server. It demonstrates the
event contract and state gates without pretending to authenticate external
vendors or call paid model APIs. Production deployment should replace the
in-memory store with Postgres/SQLite WAL + an append-only event repository and
add OIDC/RBAC, signed relay packets, a sandbox, and a real ModelGateway.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Set

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:  # Works both as ``backend.app`` and as ``app`` from the backend folder.
    from .orchestrator import acceptance_blocked, canonical_path, validate_dependency_graph, write_sets_conflict
    from .model_gateway import ModelGateway, ModelRequest, default_profiles
    from .knowledge_base import KnowledgeBase, MAX_OPEN_FILE_BYTES
    from .capability_catalog import (
        BUILTIN_ARCHETYPES,
        BUILTIN_BLOCKS,
        BUILTIN_METHODS,
        BUILTIN_PRESETS,
        REQUIRED_BLOCK_IDS,
        composition_diff,
        compose_workflow,
        metadata_snapshot_to_catalog,
    )
    from .problem_contract import build_problem_contract
    from .repo_catalog import CatalogPathError, WorkspaceCatalog
except ImportError:  # pragma: no cover - exercised by the documented launch command
    from orchestrator import acceptance_blocked, canonical_path, validate_dependency_graph, write_sets_conflict
    from model_gateway import ModelGateway, ModelRequest, default_profiles
    from knowledge_base import KnowledgeBase, MAX_OPEN_FILE_BYTES
    from capability_catalog import (
        BUILTIN_ARCHETYPES,
        BUILTIN_BLOCKS,
        BUILTIN_METHODS,
        BUILTIN_PRESETS,
        REQUIRED_BLOCK_IDS,
        composition_diff,
        compose_workflow,
        metadata_snapshot_to_catalog,
    )
    from problem_contract import build_problem_contract
    from repo_catalog import CatalogPathError, WorkspaceCatalog


ROOT = Path(__file__).resolve().parents[1]
# Keep the API identity aligned with the collaboration charter.  The former
# prototype used a shorter demo id (HGC-2026-A), which made a screenshot or
# approval look as if it belonged to a different run.  A single identity is
# now shared by the backend, the UI fixture, and the evidence packet.
PROJECT_ID = "HGC-MF-2026-001"
RUN_ID = "RUN-MF-2026-0831"
LOCAL_AGENT_IDS = {"owner", "user", "coordinator", "codex/root", "scope", "data", "routeA", "routeB", "critic", "validator"}
REVISION_PATTERN = re.compile(r"^(?:manifest|source):[0-9a-fA-F]{64}$")

# The repository itself is a bounded, read-only context source.  Instantiate it
# before loading the runtime revision so the advertised input hash can be
# derived from the current checkout rather than from a stale ignored evidence
# file left by an earlier run.
workspace_catalog = WorkspaceCatalog(ROOT)


def _declared_manifest_revision() -> Optional[str]:
    """Read the optional local evidence declaration without trusting it."""
    manifest = ROOT / ".collab" / "manifest.sha256"
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        declared = re.search(r"Manifest digest.*?:\s*([0-9a-fA-F]{64})", line, flags=re.IGNORECASE)
        if declared:
            return declared.group(1).lower()
    for line in lines:
        candidate = line.strip().split(maxsplit=1)[0]
        if re.fullmatch(r"[0-9a-fA-F]{64}", candidate):
            return candidate.lower()
    return None


def _runtime_workspace_revision() -> Optional[str]:
    """Return a manifest-shaped digest of the current allowlisted checkout."""
    try:
        digest = str(workspace_catalog.catalog().get("manifest_sha", ""))
        if digest.startswith("sha256:") and len(digest.split(":", 1)[1]) == 64:
            return digest.split(":", 1)[1].lower()
    except Exception:  # pragma: no cover - defensive startup fallback
        return None
    return None


def load_input_revision() -> str:
    """Read the frozen source manifest when available.

    This is intentionally a read-only bootstrap hint, not a replacement for
    a production artifact registry.  If the manifest is unavailable, derive a
    stable source revision from the project id and report that fact in the
    snapshot rather than inventing a short hash.
    """
    # Prefer the current checkout digest.  The ignored .collab declaration is
    # useful evidence, but it must never make a changed source tree look
    # current.  Keeping the ``manifest:`` shape preserves the existing API
    # contract while making the value auditable at runtime.
    current = _runtime_workspace_revision()
    if current:
        return f"manifest:{current}"
    serialized = json.dumps({"project_id": PROJECT_ID, "run_id": RUN_ID, "source": "unavailable"}, sort_keys=True, separators=(",", ":"))
    return "source:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


INPUT_REVISION = os.getenv("COLLAB_INPUT_REVISION") or load_input_revision()
# The knowledge base is a read-only, local index over the user's explicitly
# supplied materials directory.  It is intentionally separate from the
# collaboration event store and never copies source files into this project.
knowledge_base = KnowledgeBase()

# The capability layer is a read-only projection of the current KB snapshot.
# It intentionally keeps the curated playbook separate from source-text facts:
# a card can suggest a route, but only a problem contract + independent
# validation can promote it into a paper claim.
CAPABILITY_SCHEMA_VERSION = "capability-catalog/v1"
CONTENT_PACK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
CONTENT_PACK_EVIDENCE_REF_PATTERN = re.compile(r"^kbdoc:kbdoc_[0-9a-f]{16}(?:#p\d+)?$", flags=re.IGNORECASE)
CONTENT_PACK_COVERAGE_SCHEMA = "content-pack-coverage/v1"


def _safe_content_pack_id(value: Any) -> Optional[str]:
    """Return a canonical built-in content-pack id, or ``None``.

    Content-pack ids are catalogue references, never filesystem paths.  The
    explicit allow-list shape also prevents encoded separators, ``..`` and
    arbitrary strings from being fed into the resolver.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    if not CONTENT_PACK_ID_PATTERN.fullmatch(candidate):
        return None
    return candidate


def _normalise_content_pack_evidence_refs(raw: Any) -> List[str]:
    """Keep only bounded document-level refs emitted by the KB adapter."""
    if not isinstance(raw, (list, tuple, set)):
        return []
    refs: List[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if CONTENT_PACK_EVIDENCE_REF_PATTERN.fullmatch(candidate) and candidate not in refs:
            refs.append(candidate)
        if len(refs) >= 60:
            break
    return sorted(refs, key=str.lower)


def _content_pack_coverage(summary: Mapping[str, Any], *, state: str = "PENDING_RESOLUTION",
                           returned_count: int = 0, evidence_ref_count: int = 0,
                           truncated: bool = False, extract_status_counts: Optional[Mapping[str, int]] = None,
                           query: Optional[str] = None) -> Dict[str, Any]:
    """Build a bounded, source-only coverage projection for a content pack.

    A catalogue row has not been resolved yet, so it carries a conservative
    pending state.  The resolver replaces this projection with counts from a
    bounded KB search.  No absolute source path or file bytes are included.
    """
    try:
        indexed_count = max(0, int(summary.get("indexed_count", summary.get("valid_count", 0)) or 0))
    except (TypeError, ValueError):
        indexed_count = 0
    try:
        temporary_count = max(0, int(summary.get("temporary_count", 0) or 0))
    except (TypeError, ValueError):
        temporary_count = 0
    payload: Dict[str, Any] = {
        "schema_version": CONTENT_PACK_COVERAGE_SCHEMA,
        "state": state,
        "mode": "metadata_plus_bounded_lexical",
        "index_revision": summary.get("index_revision"),
        "source_status": summary.get("source_status", "UNAVAILABLE"),
        "indexed_count": indexed_count,
        "temporary_count": temporary_count,
        "returned_count": max(0, int(returned_count or 0)),
        "evidence_ref_count": max(0, int(evidence_ref_count or 0)),
        "truncated": bool(truncated),
        "page_chunks": 0,
        "extract_status_counts": dict(extract_status_counts or {}),
        "note": "内容包是检索与审查清单；返回项仍需核对原文件，当前没有页级 kbchunk。",
    }
    if query is not None:
        payload["query"] = str(query)[:240]
    return payload


def _decorate_content_pack(pack: Mapping[str, Any], summary: Mapping[str, Any], project_id: str) -> Dict[str, Any]:
    """Expose safe, auditable metadata for one catalogue content pack."""
    pack_id = _safe_content_pack_id(pack.get("id")) or "unknown"
    source_status = str(summary.get("source_status", "UNAVAILABLE"))
    if source_status == "UNAVAILABLE":
        state = "SOURCE_UNAVAILABLE"
    elif not int(summary.get("indexed_count", summary.get("valid_count", 0)) or 0):
        state = "NO_INDEX"
    elif int(summary.get("temporary_count", 0) or 0):
        state = "PARTIAL_PENDING"
    else:
        state = "PENDING_RESOLUTION"
    coverage = _content_pack_coverage(summary, state=state, query=pack.get("query"))
    row = dict(pack)
    row.update({
        "claim_class": "hypothesis",
        "usage": "retrieval_recipe",
        "usage_note": "用于生成受限检索查询和审查清单，不是论文事实或适配性证明。",
        "evidence_refs": [],
        "source_refs": [],
        "coverage": coverage,
        "coverage_state": state,
        "resolve_endpoint": f"/api/projects/{project_id}/capabilities/content-packs/{pack_id}/resolve",
    })
    return row


def capability_catalog_snapshot(force_refresh: bool = False) -> Dict[str, Any]:
    """Return a small, serialisable capability catalogue for the UI/agents.

    ``metadata_snapshot_to_catalog`` never opens source files.  We add only
    derived inventory signals here (module/kind/extension counts and an
    explicit coverage warning), so the endpoint remains fast and honest while
    the full extraction/OCR queue is still a future slice.
    """
    summary = knowledge_base.summary(force_refresh=force_refresh)
    catalog = metadata_snapshot_to_catalog(summary)
    source = catalog.setdefault("source", {})
    facets = source.get("facets") or {}
    kinds = facets.get("kinds") or {}
    modules = facets.get("modules") or {}
    extensions = facets.get("extensions") or {}
    source["schema_version"] = CAPABILITY_SCHEMA_VERSION
    source["coverage"] = "metadata_plus_curated_playbook"
    source["coverage_note"] = (
        "能力卡是候选路线；资料盘当前以 metadata snapshot 为主，正文/OCR/页级证据仍需按需抽取。"
    )
    source["asset_signals"] = {
        "paper_candidates": int(kinds.get("paper", 0) or 0),
        "problem_candidates": int(kinds.get("problem", 0) or 0),
        "code_candidates": int(kinds.get("code", 0) or 0),
        "template_candidates": int(kinds.get("template", 0) or 0),
        "course_candidates": int(kinds.get("course", 0) or 0),
        "tool_candidates": int(kinds.get("tool", 0) or 0),
        "module_count": len(modules),
        "extension_count": len(extensions),
    }
    source["evidence_policy"] = {
        "source_claims": "observed_only_after_document_or_chunk_check",
        "method_cards": "curated/inferred; verify against current problem",
        "paper_claims": "only VERIFIED/ACCEPTED with artifact + validation gates",
    }
    # Content packs are first-class catalogue objects, but their source
    # bindings are resolved lazily.  Keep the catalogue useful and honest by
    # exposing an explicit pending/partial coverage state and a read-only
    # resolver route instead of pretending that the fixed query is a citation.
    decorated_packs = [
        _decorate_content_pack(item, summary, PROJECT_ID)
        for item in (catalog.get("content_packs") or [])
    ]
    catalog["content_packs"] = decorated_packs
    source["content_pack_resolution"] = {
        "mode": "on_demand_bounded_search",
        "resolver": f"/api/projects/{PROJECT_ID}/capabilities/content-packs/{{pack_id}}/resolve",
        "pending_count": sum(1 for item in decorated_packs if item.get("coverage_state") == "PENDING_RESOLUTION"),
        "evidence_refs_bound": 0,
        "page_chunks": 0,
        "note": "调用 resolver 后才会绑定当前 index_revision 下的 kbdoc 引用。",
    }
    serial = json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    catalog["capability_revision"] = "cap:" + hashlib.sha256(serial.encode("utf-8")).hexdigest()
    return catalog


def _capability_suggestions(query: str, catalog: Mapping[str, Any], limit: int = 8) -> Dict[str, Any]:
    """Rank archetypes/method cards using transparent cue matches only."""
    text = str(query or "").strip().lower()
    archetype_rows: List[Dict[str, Any]] = []
    for archetype in catalog.get("problem_archetypes", []):
        cues = [str(cue) for cue in archetype.get("cues", [])]
        matched = [cue for cue in cues if cue.lower() in text]
        score = len(matched) / max(1, len(cues))
        archetype_rows.append({**archetype, "matched_cues": matched, "score": round(score, 3), "claim_class": "inferred"})
    archetype_rows.sort(key=lambda row: (-row["score"], row.get("id", "")))
    if not text:
        archetype_rows = [{**row, "score": 0.0, "matched_cues": []} for row in archetype_rows]
    selected = [row for row in archetype_rows if row["score"] > 0][:3] or archetype_rows[:1]
    preferred_blocks: List[str] = []
    validation_kinds: List[str] = []
    for row in selected:
        for block_id in row.get("preferred_blocks", []):
            if block_id not in preferred_blocks:
                preferred_blocks.append(block_id)
        for check_kind in row.get("validation_kinds", []):
            if check_kind not in validation_kinds:
                validation_kinds.append(check_kind)
    method_rows: List[Dict[str, Any]] = []
    selected_text = " ".join(str(row.get("title", "")) for row in selected).lower()
    for method in catalog.get("methods", []):
        haystack = " ".join([
            str(method.get("title", "")), str(method.get("family", "")),
            " ".join(str(item) for item in method.get("applicability", [])),
        ]).lower()
        cue_hits = sum(1 for token in text.split() if token and token in haystack)
        family_bonus = 1 if str(method.get("family", "")).lower() in selected_text else 0
        score = cue_hits + family_bonus
        method_rows.append({**method, "suggestion_score": score, "claim_class": "hypothesis", "selection_note": "候选；需按题面/数据/验证门复核"})
    method_rows.sort(key=lambda row: (-row["suggestion_score"], row.get("id", "")))
    return {
        "query": str(query or ""),
        "archetypes": selected,
        "recommended_blocks": preferred_blocks,
        "validation_kinds": validation_kinds,
        "methods": method_rows[:max(1, min(20, int(limit)))],
        "warnings": [
            "这是透明 cue-match 建议，不是自动选模，也不代表资料中的模型正确或适合当前题目。",
            "没有题面、数据契约和独立验证时，建议状态保持 HYPOTHESIS/UNVERIFIED。",
        ],
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def revision_for(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "manifest:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def lease_expired(lease: Optional[Dict[str, Any]]) -> bool:
    if not lease:
        return True
    expires_at = lease.get("expires_at")
    if not expires_at:
        return False
    try:
        parsed = datetime.fromisoformat(str(expires_at))
        if parsed.tzinfo is None:
            return True
        return parsed <= datetime.now(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return True


def new_lease(previous: Optional[Dict[str, Any]], ttl_seconds: int, agent_id: str) -> Dict[str, Any]:
    try:
        previous_epoch = int((previous or {}).get("fencing_epoch", 0))
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=409, detail={"code": "INVALID_FENCING_STATE"}) from error
    return {
        "ttl_seconds": ttl_seconds,
        "fencing_epoch": previous_epoch + 1,
        "holder": agent_id,
        "issued_at": utc_now(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat(timespec="seconds"),
    }


def renew_lease(previous: Dict[str, Any], ttl_seconds: int) -> Dict[str, Any]:
    renewed = dict(previous)
    renewed.update({
        "ttl_seconds": ttl_seconds,
        "issued_at": utc_now(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat(timespec="seconds"),
    })
    return renewed


def is_external_agent(agent_id: str) -> bool:
    normalized = agent_id.strip().lower()
    return normalized not in {item.lower() for item in LOCAL_AGENT_IDS} and not normalized.startswith("local/")


def validate_revision(value: str, field_name: str = "revision") -> str:
    if not REVISION_PATTERN.fullmatch(value):
        raise HTTPException(status_code=422, detail={"code": "INVALID_REVISION", "field": field_name, "message": "expected manifest:<64 hex> or source:<64 hex>"})
    return value


def validate_target_revision(value: str, field_name: str = "target_revision", *, allow_wildcard: bool = False) -> str:
    if allow_wildcard and value == "*":
        return value
    return validate_revision(value, field_name)


def valid_evidence_ref(value: str) -> bool:
    # KB references are source pointers, not a shortcut around the artifact or
    # numerical validation gates.  ``#pN`` is reserved for a future page-level
    # chunk adapter; the current MVP emits document-level ``kbdoc`` refs.
    candidate = str(value).strip()
    pattern = r"(?:artifact|run|claim|file):[^\s]{2,300}|kbdoc:kbdoc_[0-9a-f]{16}(?:#p\d+)?|kbchunk:kbchunk_kbdoc_[0-9a-f]{16}_\d+(?:#p\d+)?"
    if re.fullmatch(pattern, candidate, flags=re.IGNORECASE):
        return True
    # Workspace refs are bounded source pointers emitted by WorkspaceCatalog.
    # They are evidence of where a prompt/skill came from, not proof that a
    # mathematical claim is verified.  Keep the same allowlist and traversal
    # rules as the catalog so an arbitrary local path can never be smuggled
    # into a message, task result, or review record.
    if not candidate.lower().startswith("repo:"):
        return False
    rel = candidate[5:]
    if not rel or len(rel) > 300 or "\\" in rel or "\x00" in rel or rel.startswith("/"):
        return False
    parts = PurePosixPath(rel).parts
    allowed_roots = {
        "README.md", "TASKS.md", "AGENTS.md", "app.js", "index.html", "styles.css", "docker-compose.yml",
        "docs", "skills", "notes", "workflows", "models", "paper", "viz", "scripts", "experiments", "backend", "assets",
    }
    if not parts or parts[0] not in allowed_roots:
        return False
    sensitive = re.compile(r"(?:^|[._-])(secret|secrets|credential|credentials|password|passwd|token|api[_-]?key|private[_-]?key)(?:[._-]|$)", flags=re.IGNORECASE)
    return all(part not in {"", ".", ".."} and not part.startswith(".") and not sensitive.search(part) for part in parts)


def _collect_evidence_refs(value: Any) -> Set[str]:
    """Collect exact evidence references from a task/event projection.

    Finding closure must not turn a syntactically valid, arbitrary string into
    proof.  The local adapter has no external evidence registry, so the safe
    compatibility boundary is an exact reference already present in this task's
    result/previous result or an associated event payload.  Free-form prose is
    intentionally ignored; only fields whose values are structured evidence
    pointers are traversed.
    """
    refs: Set[str] = set()
    container_keys = {
        "evidence_ref", "evidence_refs", "artifact_ref", "artifact_refs", "citation_ref",
        "ref", "source_ref", "manifest_ref", "artifact_manifest", "paper_claims",
        "result", "previous_result", "task", "payload",
    }

    def visit(node: Any, *, field: Optional[str] = None) -> None:
        if isinstance(node, str):
            candidate = node.strip()
            if field in container_keys and valid_evidence_ref(candidate):
                refs.add(candidate)
            return
        if isinstance(node, Mapping):
            for key, child in node.items():
                key_text = str(key)
                # Traverse structured containers; do not inspect arbitrary
                # summary/note text for strings that merely resemble a ref.
                if key_text in container_keys:
                    visit(child, field=key_text)
            return
        if isinstance(node, (list, tuple, set)):
            for child in node:
                visit(child, field=field)

    visit(value)
    return refs


def _known_finding_evidence_refs(task_id: str) -> Set[str]:
    """Return exact refs already registered for one task in local state."""
    refs: Set[str] = set()
    task = store.tasks.get(task_id) if "store" in globals() else None
    if isinstance(task, Mapping):
        refs.update(_collect_evidence_refs(task))
    for event in getattr(store, "events", []):
        event_task_id = event.task_id
        if event_task_id is None and isinstance(event.payload, Mapping):
            # MESSAGE events keep the task link in their payload (the event
            # envelope remains channel-scoped), while task transitions use the
            # envelope field.  Treat either explicit form as task-scoped; do
            # not make evidence from an unrelated channel globally reusable.
            event_task_id = event.payload.get("task_id")
            if event_task_id is None and isinstance(event.payload.get("task"), Mapping):
                event_task_id = event.payload["task"].get("id") or event.payload["task"].get("task_id")
        if str(event_task_id or "") == task_id:
            refs.update(_collect_evidence_refs(event.payload))
    return refs


# Result manifests are deliberately stricter than ordinary evidence refs.
# A ref in a chat message can point at an external/future artifact, whereas a
# manifest is the assertion that a concrete, reproducible file exists.  Keep
# that assertion inside explicit local output roots and verify the bytes before
# allowing it to participate in a paper/release gate.  ``.collab`` is hidden
# from the static server, but is an intentional local evidence store; it is
# listed explicitly here rather than opening all hidden paths.
ARTIFACT_ALLOWED_PREFIXES = (
    PurePosixPath("artifacts"),
    PurePosixPath("models"),
    PurePosixPath("experiments"),
    PurePosixPath("paper"),
    PurePosixPath("viz"),
    PurePosixPath("runtime", "artifacts"),
    PurePosixPath(".collab", "artifacts"),
    PurePosixPath(".collab", "evidence"),
    PurePosixPath(".collab", "reviews"),
)
ARTIFACT_MAX_BYTES = 256 * 1024 * 1024

# A task's write set is a capability grant, not just a display label.  Keep it
# narrower than the general repository/catalog allow-list: workers may create
# outputs in the explicit artifact roots only, never source, control, runtime
# journal, hidden, or credential-looking paths.  The optional ``.collab``
# roots are for evidence/review artifacts; the rest of that control directory
# remains coordinator-owned.
WRITE_SET_ALLOWED_PREFIXES = ARTIFACT_ALLOWED_PREFIXES
WRITE_SET_CONTROL_NAMES = frozenset({
    ".git", ".collab", ".env", ".env.example", "agents.md", "tasks.md", "readme.md",
    "docker-compose.yml", "backend", "docs", "skills", "notes", "workflows", "scripts",
    "data", "assets", "manifest.sha256", "charter.yaml", "tasks.yaml",
    "events.jsonl", "collab-state.json", "app.py", "app.js", "index.html", "styles.css",
})
WRITE_SET_SENSITIVE_PART = re.compile(
    r"(?:^|[._-])(secret|secrets|credential|credentials|password|passwd|token|api[_-]?key|private[_-]?key)(?:[._-]|$)",
    flags=re.IGNORECASE,
)


def _normalise_write_set_path(raw_path: Any) -> str:
    """Validate and canonicalise one worker write-set capability.

    ``canonical_path`` provides the common traversal/absolute-path checks used
    by the orchestrator.  This second fence binds the result to an explicit
    output root and rejects control files.  A trailing ``/**`` is accepted as
    the protocol's directory notation and reduced to the directory prefix so
    conflict detection and artifact-manifest matching have the same semantics.
    """
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("write path must be a non-empty string")
    if raw_path != raw_path.strip():
        raise ValueError("leading/trailing whitespace is not allowed in a write set")
    raw_value = raw_path
    if len(raw_value) > 500 or any(ord(char) < 32 or ord(char) == 127 for char in raw_value):
        raise ValueError("write path contains a control character or is too long")
    # A colon in a descendant component can address an NTFS alternate data
    # stream (for example ``artifacts/result.json:secret``) even though the
    # apparent path remains under an approved root.  Reject it everywhere;
    # artifact names do not need drive letters or stream syntax.
    if ":" in raw_value:
        raise ValueError("alternate data stream or drive syntax is not allowed")
    normalized = canonical_path(raw_value)
    if normalized.endswith("/**"):
        normalized = normalized[:-3].rstrip("/")
    if not normalized:
        raise ValueError("write path must not be empty")
    path = PurePosixPath(normalized)
    parts = list(path.parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path traversal is not allowed")
    if any("*" in part or "?" in part for part in parts):
        raise ValueError("only a trailing /** wildcard is allowed")

    folded = tuple(part.casefold() for part in parts)
    matched_prefix = None
    for prefix in WRITE_SET_ALLOWED_PREFIXES:
        candidate = tuple(part.casefold() for part in prefix.parts)
        if len(folded) >= len(candidate) and folded[: len(candidate)] == candidate:
            matched_prefix = prefix
            break
    if matched_prefix is None:
        raise ValueError(
            "write path must be under an approved artifact root: "
            "artifacts/, models/, experiments/, paper/, viz/, runtime/artifacts/, "
            ".collab/{artifacts,evidence,reviews}/"
        )

    for index, part in enumerate(parts):
        folded_part = part.casefold()
        # Windows silently trims trailing dots/spaces from path components;
        # refusing them prevents an apparently harmless artifact name from
        # aliasing a different control file on disk.
        if part != part.rstrip(" ."):
            raise ValueError("trailing dots/spaces are not allowed in a write set")
        # ``.collab`` is allowed only as the first component of the three
        # explicit evidence roots.  Every other dot-prefixed component is
        # hidden/control state and is therefore denied.
        if part.startswith(".") and not (index == 0 and folded_part == ".collab"):
            raise ValueError("hidden/control paths are not allowed in a write set")
        if folded_part in WRITE_SET_CONTROL_NAMES and not (index == 0 and folded_part == ".collab"):
            raise ValueError("control paths are not allowed in a write set")
        if WRITE_SET_SENSITIVE_PART.search(part):
            raise ValueError("sensitive-looking paths are not allowed in a write set")
        # Windows device names are not ordinary artifact files and can make a
        # nominally relative path address a console/device instead of the
        # worker's output directory.
        device_name = part.rstrip(" .").split(".", 1)[0].casefold()
        if device_name in {"con", "prn", "aux", "nul"} or (len(device_name) == 4 and device_name[:3] in {"com", "lpt"} and device_name[3].isdigit()):
            raise ValueError("reserved device names are not allowed in a write set")

    # Existing symlink/junction components are rejected.  Non-existent output
    # directories are fine; the worker may create them inside its lease.
    current = ROOT
    for part in parts:
        current = current / part
        try:
            if current.is_symlink():
                raise ValueError("symlink paths are not allowed in a write set")
        except OSError as error:
            raise ValueError("write path could not be inspected") from error

    # Canonicalise the approved root spelling (important on Windows where the
    # filesystem is case-insensitive) while preserving user-facing descendant
    # names.  This keeps ``ARTIFACTS/foo`` and ``artifacts/foo`` in one scope.
    prefix_parts = list(matched_prefix.parts)
    parts[: len(prefix_parts)] = prefix_parts
    return "/".join(parts)


def _safe_artifact_path(raw_path: Any) -> Optional[Path]:
    """Resolve a manifest path under an explicit local artifact root.

    This helper never creates or opens a file.  It rejects drive-qualified,
    traversal, hidden (outside the explicit ``.collab`` roots), symlinked and
    oversized paths.  The caller still hashes the returned path immediately
    before accepting the manifest, so a changed file fails closed.
    """
    if not isinstance(raw_path, str):
        return None
    value = raw_path.strip()
    if not value or len(value) > 500 or "\x00" in value:
        return None
    # Backslashes are rejected rather than normalised here.  A manifest is a
    # portable protocol envelope; accepting both separators would make the
    # displayed path and the verified path ambiguous on Windows.
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    if any(part.startswith(".") for part in path.parts if part != ".collab"):
        return None
    if not any(path == prefix or prefix in path.parents for prefix in ARTIFACT_ALLOWED_PREFIXES):
        return None
    candidate = ROOT.joinpath(*path.parts)
    current = ROOT
    for part in path.parts:
        current = current / part
        try:
            if current.is_symlink():
                return None
        except OSError:
            return None
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(ROOT)
        stat = resolved.stat()
    except (OSError, ValueError):
        return None
    if not resolved.is_file() or stat.st_size > ARTIFACT_MAX_BYTES:
        return None
    return resolved


def _hash_local_file(path: Path) -> Optional[str]:
    """Return a ``sha256:`` digest, or ``None`` when the file changes/read fails."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, PermissionError):
        return None
    return "sha256:" + digest.hexdigest()


def modeling_provenance(message: MessageIn) -> Dict[str, Any]:
    """Project message provenance without guessing missing claims or evidence."""
    complete = bool(message.claim_class and message.evidence_refs and message.target_revision)
    return {
        "claim_class": message.claim_class or "unknown",
        "evidence_refs": list(message.evidence_refs),
        "target_revision": message.target_revision,
        "provenance_status": "RECEIVED" if complete else "UNVERIFIED",
    }


def artifact_provenance_gate(result_record: Dict[str, Any], *, task_record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Check that result/evidence/claim refs resolve to a frozen manifest.

    This is intentionally separate from the numerical validation gate: a
    result can be useful for review while its files are still unregistered,
    but it must not become a paper or release claim until the two gates agree.
    """
    entries = result_record.get("artifact_manifest") or []
    refs = set(result_record.get("artifact_refs") or []) | set(result_record.get("evidence_refs") or [])
    target_revision = result_record.get("target_revision")
    reasons: List[str] = []
    entry_checks: List[Dict[str, Any]] = []
    if not entries:
        reasons.append("artifact_manifest_missing")
    entry_refs: Set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            reasons.append("manifest_entry_must_be_object")
            continue
        ref = str(entry.get("ref", "")).strip()
        entry_refs.add(ref)
        entry_result: Dict[str, Any] = {
            "ref": ref,
            "path": str(entry.get("path", "")),
            "status": "UNVERIFIED",
            "path_status": "UNVERIFIED",
            "hash_status": "UNVERIFIED",
        }
        if not valid_evidence_ref(ref):
            reasons.append("manifest_ref_invalid")
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(entry.get("sha256", ""))):
            reasons.append("manifest_hash_invalid")
        expected_hash = str(entry.get("sha256", "")).lower()
        local_path = _safe_artifact_path(entry.get("path"))
        if local_path is None:
            reasons.append("manifest_path_untrusted")
            entry_result["path_status"] = "UNTRUSTED"
        else:
            entry_result["path_status"] = "LOCAL_FILE"
            actual_hash = _hash_local_file(local_path)
            if actual_hash is None:
                reasons.append("manifest_file_unreadable")
                entry_result["hash_status"] = "UNREADABLE"
            elif actual_hash.lower() != expected_hash:
                reasons.append("manifest_hash_mismatch")
                entry_result["hash_status"] = "MISMATCH"
                entry_result["actual_sha256"] = actual_hash
            else:
                entry_result["hash_status"] = "MATCH"
                entry_result["actual_sha256"] = actual_hash
            # A worker may only claim files inside its declared write set.  An
            # empty write set is allowed for a legacy/read-only task, but an
            # explicitly bounded set is enforced here as another provenance
            # fence (not merely a UI convention).
            write_set = list((task_record or {}).get("write_set") or [])
            if write_set:
                path_text = PurePosixPath(str(entry.get("path"))).as_posix().rstrip("/")
                try:
                    in_write_set = any(
                        path_text == canonical_path(item).rstrip("/")
                        or path_text.startswith(canonical_path(item).rstrip("/") + "/")
                        for item in write_set
                    )
                except (TypeError, ValueError):
                    in_write_set = False
                if not in_write_set:
                    reasons.append("manifest_path_outside_write_set")
                    entry_result["path_status"] = "OUTSIDE_WRITE_SET"
        if entry.get("exit_code") != 0:
            reasons.append("manifest_exit_code_nonzero")
        if target_revision and entry.get("target_revision") != target_revision:
            reasons.append("manifest_target_revision_mismatch")
        if (
            entry_result.get("path_status") == "LOCAL_FILE"
            and entry_result.get("hash_status") == "MATCH"
            and entry.get("exit_code") == 0
            and valid_evidence_ref(ref)
            and (not target_revision or entry.get("target_revision") == target_revision)
        ):
            entry_result["status"] = "VERIFIED_BYTES"
        entry_checks.append(entry_result)
    if refs and not refs.issubset(entry_refs):
        reasons.append("result_ref_not_in_manifest")
    # A syntactically valid KB citation is still unresolved until the current
    # local index can locate the document.  ``kbchunk`` is reserved for the
    # page-level adapter and therefore remains fail-closed in this MVP.
    for ref in refs:
        if str(ref).startswith("kbdoc:"):
            doc_id = str(ref).split(":", 1)[1].split("#", 1)[0]
            doc = knowledge_base.document(doc_id, include_preview=False)
            if not doc or doc.get("source_status") != "LOCAL_INDEXED":
                reasons.append("kb_ref_unresolved")
        elif str(ref).startswith("kbchunk:"):
            reasons.append("kb_chunk_adapter_not_ready")
    for claim in result_record.get("paper_claims") or []:
        if not isinstance(claim, dict):
            reasons.append("paper_claim_must_be_object")
            continue
        claim_refs = set(claim.get("evidence_refs") or [])
        if not claim_refs or not claim_refs.issubset(entry_refs):
            reasons.append("paper_claim_evidence_unlinked")
        for ref in claim_refs:
            if str(ref).startswith("kbdoc:"):
                doc_id = str(ref).split(":", 1)[1].split("#", 1)[0]
                doc = knowledge_base.document(doc_id, include_preview=False)
                if not doc or doc.get("source_status") != "LOCAL_INDEXED":
                    reasons.append("kb_ref_unresolved")
            elif str(ref).startswith("kbchunk:"):
                reasons.append("kb_chunk_adapter_not_ready")
        if claim.get("status") in {"VERIFIED", "ACCEPTED"} and claim.get("claim_class") == "hypothesis":
            reasons.append("hypothesis_claim_cannot_be_verified")
        if target_revision and claim.get("target_revision") != target_revision:
            reasons.append("paper_claim_target_revision_mismatch")
        metric = claim.get("metric_definition") or {}
        if claim.get("status") in {"VERIFIED", "ACCEPTED"} and not all(metric.get(key) not in (None, "") for key in ("unit", "denominator", "scope")):
            reasons.append("paper_claim_metric_definition_incomplete")
    reasons = list(dict.fromkeys(reasons))
    return {
        "status": "READY" if not reasons else "UNVERIFIED",
        "ready": not reasons,
        "manifest_count": len(entries),
        "linked_ref_count": len(refs.intersection(entry_refs)),
        "entry_checks": entry_checks,
        "reasons": reasons,
    }


def validation_gate(result_record: Dict[str, Any], *, task_record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compute a read-only, fail-closed validation gate for a task result.

    A legacy result with no modeling fields is represented as UNVERIFIED.  It
    remains readable for migration, but is not eligible for review acceptance.
    """
    checks = result_record.get("validation_checks") or []
    problem_type = result_record.get("problem_type")
    kinds = {str(item.get("check_kind", "")).strip() for item in checks if isinstance(item, dict)}
    reasons: List[str] = []
    if not problem_type:
        reasons.append("problem_type_missing")
    if len(checks) < 2:
        reasons.append("at_least_two_checks_required")
    if len(kinds) < 2:
        reasons.append("check_kind_must_be_distinct")
    for item in checks:
        if not isinstance(item, dict):
            reasons.append("check_must_be_object")
            continue
        if not str(item.get("scope", "")).strip():
            reasons.append("scope_missing")
        if "threshold" not in item or item.get("threshold") is None:
            reasons.append("threshold_missing")
        if item.get("exit_code") != 0:
            reasons.append("exit_code_nonzero")
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(item.get("result_hash", ""))):
            reasons.append("result_hash_invalid")
    # Preserve order while avoiding an unreadable duplicate reason list.
    reasons = list(dict.fromkeys(reasons))
    ready = not reasons
    provenance = artifact_provenance_gate(result_record, task_record=task_record)
    return {
        "status": "READY" if ready else "UNVERIFIED",
        "ready": ready,
        "problem_type": problem_type or "unknown",
        "check_count": len(checks),
        "distinct_check_kinds": sorted(kind for kind in kinds if kind),
        "reasons": reasons,
        "provenance": provenance,
    }


def release_gate_snapshot(tasks: Dict[str, Dict[str, Any]], approvals: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Return a read-only paper-claim/release projection for the snapshot."""
    task_rows = list(tasks.values())
    blocked = [row.get("id") for row in task_rows if row.get("status") in {"BLOCKED", "FAILED", "TIMEOUT"}]
    unverified = []
    for row in task_rows:
        result = row.get("result")
        if result:
            gate = validation_gate(result)
            if not gate["ready"]:
                unverified.append(row.get("id"))
            # Results submitted through the modeling contract carry a gate
            # marker. Their files must also resolve to an artifact manifest
            # before release; legacy rows remain readable but are listed as
            # unverified rather than silently upgraded.
            if "validation_gate" in result and not artifact_provenance_gate(result)["ready"]:
                unverified.append(row.get("id"))
        elif row.get("status") in {"VERIFIED", "ACCEPTED", "RELEASED"} and not row.get("manifest_linked"):
            unverified.append(row.get("id"))
    claim_total = 0
    claim_unverified = 0
    for row in task_rows:
        result = row.get("result") or {}
        for claim in result.get("paper_claims") or []:
            claim_total += 1
            if claim.get("status") not in {"VERIFIED", "ACCEPTED"}:
                claim_unverified += 1
    approvals = approvals or []
    release_approval = any(item.get("decision") == "approve" and str(item.get("scope", "")).lower().startswith(("release", "paper")) and _approval_is_live(item) for item in approvals)
    incomplete = [row.get("id") for row in task_rows if row.get("status") not in {"VERIFIED", "INTEGRATED", "ACCEPTED", "RELEASED"}]
    ready = not blocked and not unverified and not incomplete and release_approval
    blockers = sorted(item for item in blocked + unverified + incomplete if item)
    if not release_approval:
        blockers.append("owner_release_approval")
    return {
        "status": "READY" if ready else "BLOCKED",
        "paper_claims": {"total": claim_total, "unverified": claim_unverified},
        "blocking_tasks": sorted(set(blockers)),
        "owner_approval": release_approval,
        "reason": None if ready else "validation_or_task_or_owner_gate_incomplete",
    }


def _approval_is_live(approval: Dict[str, Any]) -> bool:
    """Return whether a recorded approval has not expired or been revoked."""
    if approval.get("revoked_at"):
        return False
    try:
        return datetime.fromisoformat(str(approval.get("expires_at"))) > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    sender_id: str = Field(default="owner")
    channel: str = Field(default="main", max_length=80)
    mode: Literal["solo", "lite", "full"] = "full"
    # Optional modeling provenance.  A plain chat message remains valid, but
    # the projection marks missing fields as UNVERIFIED instead of guessing.
    claim_class: Optional[Literal["observed", "derived", "hypothesis"]] = None
    task_id: Optional[str] = Field(default=None, max_length=120)
    subproblem_id: Optional[str] = Field(default=None, max_length=40)
    evidence_refs: List[str] = Field(default_factory=list, max_length=50)
    target_revision: Optional[str] = Field(default=None, max_length=200)
    base_revision: Optional[str] = Field(default=None, min_length=1, max_length=200)
    # Optional composition metadata.  It is an auditable pointer only; it
    # never turns a dry-run assembly into a verified numerical result.
    assembly_revision: Optional[str] = Field(default=None, max_length=200)
    capability_revision: Optional[str] = Field(default=None, max_length=200)
    # Required so a client retry cannot accidentally create a second event.
    # The UI always supplies a request id; adapters should persist it across
    # network retries.
    idempotency_key: str = Field(min_length=1, max_length=200)


class ClaimRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=120)
    base_revision: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class RequeueIn(BaseModel):
    """Owner/coordinator request to reopen a blocked or failed task."""

    actor_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=2000)
    evidence_refs: List[str] = Field(default_factory=list, max_length=50)
    target_revision: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ReviewIn(BaseModel):
    reviewer_id: str = Field(min_length=1, max_length=120)
    verdict: Literal["accept", "revise", "reject"]
    summary: str = Field(min_length=1, max_length=5000)
    independence_basis: str = Field(min_length=1, max_length=500)
    check_logs: List[str] = Field(min_length=1, max_length=50)
    evidence_refs: List[str] = Field(min_length=1, max_length=50)
    target_revision: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class DispatchIn(BaseModel):
    """A coordinator-issued task envelope for the local development API."""

    task_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    owner_id: str = Field(min_length=1, max_length=120)
    reviewer_id: Optional[str] = Field(default=None, max_length=120)
    objective: str = Field(min_length=1, max_length=5000)
    depends_on: List[str] = Field(default_factory=list)
    write_set: List[str] = Field(default_factory=list)
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    acceptance: List[str] = Field(default_factory=list)
    input_revision: str = Field(min_length=1, max_length=200)
    base_revision: Optional[str] = Field(default=None, min_length=1, max_length=200)
    mode: Literal["solo", "lite", "full"] = "full"
    requested_by: str = Field(default="owner", min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ModelRouteIn(BaseModel):
    """Read-only capability request used by the UI/Coordinator preview."""

    role: str = Field(min_length=1, max_length=120)
    required_capabilities: List[str] = Field(default_factory=list, max_length=80)
    data_classification: str = Field(default="internal", max_length=40)
    external_network: bool = False
    budget_remaining: Optional[float] = None
    preferred_provider: Optional[str] = Field(default=None, max_length=120)
    required_tools: List[str] = Field(default_factory=list, max_length=80)
    max_latency_ms: Optional[int] = Field(default=None, ge=0)
    min_calibration_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_level: str = Field(default="R2", max_length=8)
    owner_approved: bool = False
    approval_ref: Optional[str] = Field(default=None, max_length=200)


class CompositionNodeIn(BaseModel):
    """One user-selected block in the local, non-executing workflow canvas."""

    node_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
    block_id: str = Field(min_length=1, max_length=120)
    method_id: Optional[str] = Field(default=None, max_length=120)
    label: Optional[str] = Field(default=None, max_length=200)
    config: Dict[str, Any] = Field(default_factory=dict)


class CompositionEdgeIn(BaseModel):
    """A typed port mapping between two composition nodes."""

    source: str = Field(min_length=1, max_length=80)
    source_port: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=80)
    target_port: str = Field(min_length=1, max_length=120)


class WorkflowComposeIn(BaseModel):
    """Validate a free assembly without running a model or changing raw data."""

    nodes: List[CompositionNodeIn] = Field(min_length=1, max_length=60)
    edges: List[CompositionEdgeIn] = Field(default_factory=list, max_length=160)
    preset_id: Optional[str] = Field(default=None, max_length=120)
    archetype_id: Optional[str] = Field(default=None, max_length=120)
    scope: List[str] = Field(default_factory=list, max_length=20)
    base_revision: Optional[str] = Field(default=None, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)
    # Optional prior draft used only for a deterministic UI diff.  It is never
    # treated as an authority; the server revalidates the submitted graph.
    previous_nodes: List[CompositionNodeIn] = Field(default_factory=list, max_length=60)
    previous_edges: List[CompositionEdgeIn] = Field(default_factory=list, max_length=160)
    # Optional innovation difference card.  It is included in the assembly
    # hash/diff but never promoted beyond HYPOTHESIS by this endpoint.
    innovation_card: Optional[Dict[str, Any]] = Field(default=None)
    previous_innovation_card: Optional[Dict[str, Any]] = Field(default=None)
    content_pack_ids: List[str] = Field(default_factory=list, max_length=20)
    previous_content_pack_ids: List[str] = Field(default_factory=list, max_length=20)
    # Optional refs returned by the read-only content-pack resolver.  They are
    # candidate source bindings, never proof of a paper claim.
    content_pack_evidence_refs: List[str] = Field(default_factory=list, max_length=60)
    content_pack_index_revision: Optional[str] = Field(default=None, max_length=200)
    content_pack_resolution_revision: Optional[str] = Field(default=None, max_length=200)


class AssemblyCommitIn(BaseModel):
    """Persist one reviewed assembly projection and emit an append-only event."""

    actor_id: str = Field(default="owner", min_length=1, max_length=120)
    nodes: List[CompositionNodeIn] = Field(min_length=1, max_length=60)
    edges: List[CompositionEdgeIn] = Field(default_factory=list, max_length=160)
    preset_id: Optional[str] = Field(default=None, max_length=120)
    archetype_id: Optional[str] = Field(default=None, max_length=120)
    scope: List[str] = Field(default_factory=list, max_length=20)
    assembly_revision: str = Field(pattern=r"^assembly:[0-9a-fA-F]{64}$")
    capability_revision: str = Field(pattern=r"^cap:[0-9a-fA-F]{64}$")
    source_revision: Optional[str] = Field(default=None, max_length=200)
    base_revision: Optional[str] = Field(default=None, max_length=200)
    previous_assembly_revision: Optional[str] = Field(default=None, max_length=200)
    # A bounded, human-authored novelty proposal.  Keep this as a dictionary
    # for forward-compatible fields while the server sanitises its shape.
    innovation_card: Optional[Dict[str, Any]] = Field(default=None)
    previous_innovation_card: Optional[Dict[str, Any]] = Field(default=None)
    content_pack_ids: List[str] = Field(default_factory=list, max_length=20)
    previous_content_pack_ids: List[str] = Field(default_factory=list, max_length=20)
    content_pack_evidence_refs: List[str] = Field(default_factory=list, max_length=60)
    content_pack_index_revision: Optional[str] = Field(default=None, max_length=200)
    content_pack_resolution_revision: Optional[str] = Field(default=None, max_length=200)
    action: Literal["SAVE_DRAFT", "SUBMIT_REVIEW"] = "SAVE_DRAFT"
    idempotency_key: str = Field(min_length=1, max_length=200)


class ProblemContractIn(BaseModel):
    """A bounded problem statement draft; extraction is read-only and conservative."""

    text: str = Field(min_length=1, max_length=50000)
    source_refs: List[str] = Field(default_factory=list, max_length=50)


class HeartbeatIn(BaseModel):
    agent_id: str = Field(min_length=1, max_length=120)
    fencing_epoch: int = Field(ge=0)
    ttl_seconds: int = Field(default=1800, ge=30, le=86400)
    base_revision: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class HandoffIn(BaseModel):
    from_agent_id: str = Field(min_length=1, max_length=120)
    to_agent_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=2000)
    fencing_epoch: int = Field(ge=0)
    target_revision: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ApprovalIn(BaseModel):
    owner_id: str = Field(default="owner", min_length=1, max_length=120)
    scope: str = Field(min_length=1, max_length=160)
    decision: Literal["approve", "reject", "accept_risk"]
    target_revision: str = Field(min_length=1, max_length=200)
    base_revision: Optional[str] = Field(default=None, min_length=1, max_length=200)
    note: str = Field(default="", max_length=5000)
    idempotency_key: str = Field(min_length=1, max_length=200)


class RelayIn(BaseModel):
    from_agent_id: str = Field(min_length=1, max_length=120)
    to_agent_id: str = Field(min_length=1, max_length=120)
    task_id: str = Field(min_length=1, max_length=120)
    input_revision: str = Field(min_length=1, max_length=200)
    base_revision: Optional[str] = Field(default=None, min_length=1, max_length=200)
    payload: Dict[str, Any] = Field(default_factory=dict)
    approval_ref: Optional[str] = Field(default=None, max_length=200)
    target_kind: Literal["local", "external"] = "external"
    idempotency_key: str = Field(min_length=1, max_length=200)


class RelayAckIn(BaseModel):
    relay_id: str = Field(min_length=1, max_length=200)
    to_agent_id: str = Field(min_length=1, max_length=120)
    nonce: str = Field(min_length=8, max_length=200)
    input_hash: str = Field(pattern=r"^sha256:[0-9a-fA-F]{64}$")
    status: Literal["RECEIVED", "REJECTED"] = "RECEIVED"
    target_revision: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=200)


class RerunIn(BaseModel):
    requested_by: str = Field(default="owner", min_length=1, max_length=120)
    target_revision: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=200)


class FindingCloseIn(BaseModel):
    actor_id: str = Field(min_length=1, max_length=120)
    evidence_ref: str = Field(min_length=1, max_length=300)
    target_revision: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ValidationCheck(BaseModel):
    """One independently reproducible validation check for a modeling result."""

    check_kind: str = Field(min_length=1, max_length=80)
    scope: str = Field(min_length=1, max_length=500)
    threshold: Any
    exit_code: int
    result_hash: str = Field(pattern=r"^sha256:[0-9a-fA-F]{64}$")


class ArtifactManifestEntry(BaseModel):
    """A reproducibility pointer for one submitted artifact or evidence file."""

    ref: str = Field(pattern=r"^(?:artifact|run|claim|file):[^\s]{2,300}$")
    path: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^sha256:[0-9a-fA-F]{64}$")
    command: str = Field(min_length=1, max_length=1000)
    exit_code: int
    target_revision: str = Field(min_length=1, max_length=200)


class PaperClaimIn(BaseModel):
    """A claim that may be copied into a paper only after independent review."""

    claim_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=5000)
    claim_class: Literal["observed", "derived", "hypothesis"]
    status: Literal["PRODUCED", "READY_FOR_REVIEW", "VERIFIED", "ACCEPTED", "UNVERIFIED", "BLOCKED"] = "PRODUCED"
    metric_definition: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[str] = Field(min_length=1, max_length=50)
    target_revision: str = Field(min_length=1, max_length=200)


class ResultIn(BaseModel):
    agent_id: str = Field(min_length=1, max_length=120)
    fencing_epoch: int = Field(ge=0)
    status: Literal["READY_FOR_REVIEW", "FAILED"] = "READY_FOR_REVIEW"
    summary: str = Field(min_length=1, max_length=5000)
    artifact_refs: List[str] = Field(min_length=1, max_length=100)
    evidence_refs: List[str] = Field(min_length=1, max_length=100)
    commands: List[str] = Field(min_length=1, max_length=100)
    result_hash: str = Field(pattern=r"^sha256:[0-9a-fA-F]{64}$")
    # Modeling-specific evidence is optional at the transport boundary for
    # backwards compatibility with legacy worker adapters.  A legacy result
    # is retained as UNVERIFIED and can never pass the review gate.
    problem_type: Optional[str] = Field(default=None, max_length=120)
    validation_checks: List[ValidationCheck] = Field(default_factory=list, max_length=20)
    artifact_manifest: List[ArtifactManifestEntry] = Field(default_factory=list, max_length=100)
    paper_claims: List[PaperClaimIn] = Field(default_factory=list, max_length=100)
    target_revision: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class Event(BaseModel):
    protocol: str = "agent-collab/v1"
    project_id: str = PROJECT_ID
    run_id: str = RUN_ID
    event_id: str
    seq: int
    timestamp: str
    actor_id: str
    type: str
    channel: str = "main"
    task_id: Optional[str] = None
    base_revision: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    revision: Optional[str] = None
    prev_hash: Optional[str] = None
    event_hash: Optional[str] = None


class EventStore:
    """Single-process event store with optional atomic JSON journaling.

    The default remains in-memory so the demo is zero-setup.  Setting
    ``COLLAB_STATE_FILE`` enables a local restart-safe journal (write temp,
    fsync, atomic replace).  It is deliberately not advertised as a
    multi-process database; production deployments should use SQLite WAL or
    Postgres with a real transaction/lock manager.
    """

    def __init__(self, state_file: Optional[str] = None) -> None:
        self.state_file = Path(state_file).resolve() if state_file else None
        self.events: List[Event] = []
        self.messages: List[Dict[str, Any]] = []
        self.approvals: List[Dict[str, Any]] = []
        self.relays: List[Dict[str, Any]] = []
        # Latest committed assembly for each collaboration scope.  Full change
        # history remains in ``events``; this projection keeps snapshot reads
        # small and restart-safe.
        self.assemblies: Dict[str, Dict[str, Any]] = {}
        self.findings: Dict[str, List[Dict[str, Any]]] = {
            "G7": [{"finding_id": "F-G7-01", "severity": "P1", "status": "open", "summary": "极端样本外推尚未验证"}],
        }
        self.tasks: Dict[str, Dict[str, Any]] = {
            # Bootstrap rows are placeholders for the local demo.  They are
            # deliberately not VERIFIED until a real problem_contract and
            # artifact manifest are submitted.
            "G1": {"id": "G1", "title": "题面契约与覆盖表", "status": "PRODUCED", "owner": "scope", "source": "bootstrap_fixture", "provenance_status": "UNVERIFIED"},
            "G3": {"id": "G3", "title": "数据质量与泄漏审计", "status": "IN_PROGRESS", "owner": "data"},
            "G6-A": {"id": "G6-A", "title": "独立路线 A：机制 + 优化", "status": "IN_PROGRESS", "owner": "routeA"},
            "G6-B": {"id": "G6-B", "title": "独立路线 B：统计 + 仿真", "status": "READY_FOR_REVIEW", "owner": "routeB"},
            "G7": {"id": "G7", "title": "Critic 评分与反例", "status": "BLOCKED", "owner": "critic"},
            "G9": {"id": "G9", "title": "群主路线审批", "status": "QUEUED", "owner": "owner"},
        }
        self.seen_idempotency: Set[str] = set()
        self.idempotency_fingerprints: Dict[str, str] = {}
        self.chain_valid: bool = True
        # Projection integrity complements the append-only event hash chain:
        # the chain can remain valid even when a persisted tasks/messages
        # projection is edited out of band.  New journals carry a digest;
        # legacy journals are readable but explicitly marked unverified.
        self.projection_integrity: str = "UNAVAILABLE"
        self.connections: Set[WebSocket] = set()
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None
        if self.state_file:
            self._load_state()

    def get_lock(self) -> asyncio.Lock:
        """Create the async lock inside the active loop (Python 3.9 safe)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as error:  # pragma: no cover - only called outside an async route
            raise RuntimeError("EventStore lock requested outside a running event loop") from error
        if self._lock is None or (self._lock_loop is not loop and not self._lock.locked()):
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        elif self._lock_loop is not loop:
            raise RuntimeError("EventStore is already locked by another event loop")
        return self._lock

    def _load_state(self) -> None:
        if not self.state_file or not self.state_file.is_file():
            return
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.tasks.update({key: dict(value) for key, value in raw.get("tasks", {}).items()})
            self.messages = list(raw.get("messages", []))
            self.approvals = list(raw.get("approvals", []))
            self.relays = list(raw.get("relays", []))
            self.assemblies = {key: dict(value) for key, value in raw.get("assemblies", {}).items()}
            self.findings.update({key: list(value) for key, value in raw.get("findings", {}).items()})
            self.events = [Event.model_validate(item) for item in raw.get("events", [])]
            # Migrate journals written before the tamper-evident chain fields
            # existed.  The first migrated event is anchored at a fixed
            # genesis marker; subsequent events point to its computed hash.
            previous_hash = "sha256:genesis"
            for event in self.events:
                if not event.prev_hash:
                    event.prev_hash = previous_hash
                if not event.event_hash:
                    event.event_hash = self._compute_event_hash(event)
                previous_hash = event.event_hash
            self.chain_valid = self.verify_event_chain()
            if not self.chain_valid:
                raise RuntimeError("collaboration event journal integrity check failed")
            self.seen_idempotency = {event.idempotency_key for event in self.events}
            self.idempotency_fingerprints = dict(raw.get("idempotency_fingerprints", {}))
            # Journals written by an older build may not have fingerprints;
            # derive a conservative one from the event envelope when possible.
            for event in self.events:
                self.idempotency_fingerprints.setdefault(event.idempotency_key, revision_for({"actor_id": event.actor_id, "event_type": event.type, "channel": event.channel, "task_id": event.task_id, "base_revision": event.base_revision, "payload": event.payload}))
            declared_projection = raw.get("projection_revision")
            actual_projection = self.revision
            if declared_projection:
                if declared_projection != actual_projection:
                    self.projection_integrity = "FAILED"
                    raise RuntimeError("collaboration projection integrity check failed")
                self.projection_integrity = "VERIFIED"
            else:
                self.projection_integrity = "LEGACY_UNVERIFIED"
        except (OSError, ValueError, TypeError) as error:
            raise RuntimeError(f"cannot load collaboration state: {error}")

    @staticmethod
    def _compute_event_hash(event: Event) -> str:
        body = event.model_dump(exclude={"event_hash"})
        serialized = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def verify_event_chain(self) -> bool:
        previous_hash = "sha256:genesis"
        for event in self.events:
            if event.prev_hash != previous_hash or event.event_hash != self._compute_event_hash(event):
                return False
            previous_hash = event.event_hash or ""
        return True

    def _persist_state_unlocked(self) -> None:
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.projection_integrity = "VERIFIED"
        payload = {
            "version": 4,
            "tasks": self.tasks,
            "messages": self.messages,
            "approvals": self.approvals,
            "relays": self.relays,
            "assemblies": self.assemblies,
            "findings": self.findings,
            "events": [event.model_dump() for event in self.events],
            "idempotency_fingerprints": self.idempotency_fingerprints,
            "projection_revision": self.revision,
        }
        temp = self.state_file.with_name(self.state_file.name + ".tmp")
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.state_file)

    @property
    def revision(self) -> str:
        # Event history itself is excluded; durable control projections remain.
        return revision_for({"tasks": self.tasks, "messages": self.messages, "approvals": self.approvals, "relays": self.relays, "assemblies": self.assemblies, "findings": self.findings})

    async def append(
        self,
        *,
        actor_id: str,
        event_type: str,
        payload: Dict[str, Any],
        channel: str = "main",
        task_id: Optional[str] = None,
        base_revision: Optional[str] = None,
        idempotency_key: str,
        state_mutator: Optional[Callable[[Event], None]] = None,
        message_factory: Optional[Callable[[Event], Dict[str, Any]]] = None,
    ) -> Event:
        """Append one event and any coupled state change atomically.

        The first prototype mutated ``tasks``/``messages`` in the route after
        appending an event.  That made a duplicate idempotency key capable of
        duplicating a chat message, and allowed two claims to race.  Callers
        now provide a small synchronous mutator which runs while the store
        lock is held; a replayed key returns the original event without
        invoking it again.  The broadcast still happens after the lock is
        released so a slow websocket cannot block writers.
        """
        event: Optional[Event] = None
        if base_revision:
            validate_revision(base_revision, "base_revision")
        fingerprint = revision_for({
            "actor_id": actor_id,
            "event_type": event_type,
            "channel": channel,
            "task_id": task_id,
            "base_revision": base_revision,
            "payload": payload,
        })
        async with self.get_lock():
            if idempotency_key in self.seen_idempotency:
                if self.idempotency_fingerprints.get(idempotency_key) != fingerprint:
                    raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT", "idempotency_key": idempotency_key})
                for existing in reversed(self.events):
                    if existing.idempotency_key == idempotency_key:
                        return existing
            if base_revision and base_revision != self.revision:
                raise HTTPException(status_code=409, detail={"code": "STALE_REVISION", "current_revision": self.revision})
            backup = (copy.deepcopy(self.tasks), copy.deepcopy(self.messages), copy.deepcopy(self.approvals), copy.deepcopy(self.relays), copy.deepcopy(self.assemblies), copy.deepcopy(self.findings), list(self.events), set(self.seen_idempotency), dict(self.idempotency_fingerprints), self.chain_valid)
            try:
                previous_hash = self.events[-1].event_hash if self.events and self.events[-1].event_hash else "sha256:genesis"
                next_seq = (self.events[-1].seq + 1) if self.events else 1
                event = Event(event_id=f"evt-{next_seq:05d}", seq=next_seq, timestamp=utc_now(), actor_id=actor_id, type=event_type, channel=channel, task_id=task_id, base_revision=base_revision or self.revision, payload=payload, idempotency_key=idempotency_key, prev_hash=previous_hash)
                if state_mutator is not None:
                    state_mutator(event)
                self.events.append(event)
                self.seen_idempotency.add(idempotency_key)
                self.idempotency_fingerprints[idempotency_key] = fingerprint
                if message_factory is not None:
                    self.messages.append(message_factory(event))
                # Expose the post-commit projection revision so clients can keep
                # their CAS cursor even when task/approval state changed.
                event.revision = self.revision
                event.event_hash = self._compute_event_hash(event)
                self.chain_valid = True
                self._persist_state_unlocked()
            except Exception:
                self.tasks, self.messages, self.approvals, self.relays, self.assemblies, self.findings, self.events, self.seen_idempotency, self.idempotency_fingerprints, self.chain_valid = backup
                raise
        await self.broadcast(event)
        return event

    async def broadcast(self, event: Event) -> None:
        stale: List[WebSocket] = []
        for socket in tuple(self.connections):
            try:
                await socket.send_json(event.model_dump())
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.connections.discard(socket)


store = EventStore(os.getenv("COLLAB_STATE_FILE"))
app = FastAPI(title="G-CUP MAS Local API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:4173", "http://127.0.0.1:4173"], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])

# The API process also serves the small vanilla front end.  Keep that surface
# explicit: a broad ``/{asset_path:path}`` handler must never turn the project
# checkout into a source browser (especially for .git, .collab, .env, runtime
# journals, backend code, or user-provided material).  Dynamic knowledge files
# continue to go through the doc-id fenced route above.
# Keep each root-level browser entry explicit.  The puzzle studio is loaded as
# a separate module so the default chat shell can stay lightweight, but it is
# still a public UI asset rather than a checkout/source-browser route.
STATIC_ROOT_FILES = {
    "index.html",
    "styles.css",
    "app.js",
    "workflow-puzzle.js",
    "favicon.ico",
    "manifest.webmanifest",
}
STATIC_ROOT_DIRS = {"assets"}
STATIC_SENSITIVE_PART = re.compile(
    r"(?:^|[._-])(secret|secrets|credential|credentials|password|passwd|token|api[_-]?key|private[_-]?key)(?:[._-]|$)",
    flags=re.IGNORECASE,
)


def _safe_static_file(asset_path: str) -> Optional[Path]:
    """Resolve only public UI assets; return ``None`` for every other path."""
    if not isinstance(asset_path, str) or not asset_path or len(asset_path) > 400:
        return None
    normalized = asset_path.replace("\\", "/")
    if normalized.startswith("/") or "\x00" in normalized:
        return None
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {"", ".", ".."} or part.startswith(".") or STATIC_SENSITIVE_PART.search(part) for part in parts):
        return None
    if len(parts) == 1 and parts[0] in STATIC_ROOT_FILES:
        pass
    elif parts[0] in STATIC_ROOT_DIRS:
        pass
    else:
        return None
    candidate = ROOT.joinpath(*parts)
    # Refuse symlinked/junction-like components even when their resolved target
    # happens to remain under ROOT; static serving is an allowlist, not a link
    # traversal mechanism.
    current = ROOT
    for part in parts:
        current = current / part
        if current.is_symlink():
            return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if ROOT not in resolved.parents or not resolved.is_file():
        return None
    return resolved


def source_integrity_snapshot() -> Dict[str, Any]:
    """Expose whether the ignored local declaration matches this checkout."""
    declared = _declared_manifest_revision()
    runtime = _runtime_workspace_revision()
    if runtime and declared and runtime == declared:
        status = "MATCHED"
    elif runtime and declared:
        status = "STALE_DECLARATION"
    elif runtime:
        status = "RUNTIME_ONLY"
    else:
        status = "UNAVAILABLE"
    return {
        "status": status,
        "declared_revision": f"manifest:{declared}" if declared else None,
        "runtime_revision": f"manifest:{runtime}" if runtime else None,
        "source": "workspace_catalog_allowlist",
        "note": "运行时 revision 来自当前白名单工作区；.collab 声明仅作对照，不会覆盖当前源码。",
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    integrity = source_integrity_snapshot()
    return {
        "ok": True,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "revision": store.revision,
        "input_revision": INPUT_REVISION,
        "source_integrity": integrity,
        "mode": "offline-dev",
        "event_chain_valid": store.chain_valid,
    }


def _require_project(project_id: str) -> None:
    if project_id != PROJECT_ID:
        raise HTTPException(status_code=404, detail="project not found")


@app.get("/api/projects/{project_id}/knowledge/summary")
def knowledge_summary(project_id: str, refresh: bool = Query(default=False)) -> Dict[str, Any]:
    """Return a bounded, read-only inventory of the user's local materials.

    The source directory is never copied into the project and the response
    exposes relative paths only.  ``refresh=true`` is an explicit rescan so a
    directory that is still synchronising can be represented honestly.
    """
    _require_project(project_id)
    return knowledge_base.summary(force_refresh=refresh)


@app.get("/api/projects/{project_id}/knowledge/search")
def knowledge_search(
    project_id: str,
    q: str = Query(default="", max_length=240),
    module: Optional[str] = Query(default=None, max_length=160),
    kind: Optional[str] = Query(default=None, max_length=80),
    year: Optional[str] = Query(default=None, max_length=40),
    extension: Optional[str] = Query(default=None, max_length=16),
    top_k: int = Query(default=8, ge=1, le=20),
    with_preview: bool = Query(default=False),
) -> Dict[str, Any]:
    """Lexically retrieve short, source-linked knowledge-base records."""
    _require_project(project_id)
    return knowledge_base.search(q, module=module, kind=kind, year=year, extension=extension, top_k=top_k, with_preview=with_preview)


@app.get("/api/projects/{project_id}/knowledge/retrieve")
def knowledge_retrieve(
    project_id: str,
    q: str = Query(default="", max_length=240),
    module: Optional[str] = Query(default=None, max_length=160),
    kind: Optional[str] = Query(default=None, max_length=80),
    year: Optional[str] = Query(default=None, max_length=40),
    extension: Optional[str] = Query(default=None, max_length=16),
    top_k: int = Query(default=8, ge=1, le=20),
) -> Dict[str, Any]:
    """Agent-facing alias: always returns bounded previews and citation refs."""
    _require_project(project_id)
    return knowledge_base.search(q, module=module, kind=kind, year=year, extension=extension, top_k=top_k, with_preview=True)


@app.get("/api/projects/{project_id}/knowledge/context")
def knowledge_context(
    project_id: str,
    q: str = Query(default="", max_length=240),
    module: Optional[str] = Query(default=None, max_length=160),
    kind: Optional[str] = Query(default=None, max_length=80),
    year: Optional[str] = Query(default=None, max_length=40),
    extension: Optional[str] = Query(default=None, max_length=16),
    top_k: int = Query(default=6, ge=1, le=12),
) -> Dict[str, Any]:
    """Prompt-sized KB context for model adapters; no arbitrary file access."""
    _require_project(project_id)
    return knowledge_base.context(q, module=module, kind=kind, year=year, extension=extension, top_k=top_k)


@app.get("/api/projects/{project_id}/workspace/catalog")
def workspace_catalog_snapshot(project_id: str) -> Dict[str, Any]:
    """Return allowlisted repository metadata for Agent context mounting."""
    _require_project(project_id)
    return workspace_catalog.catalog()


@app.get("/api/projects/{project_id}/workspace/search")
def workspace_catalog_search(
    project_id: str,
    q: str = Query(default="", max_length=240),
    top_k: int = Query(default=20, ge=1, le=50),
    path: Optional[str] = Query(default=None, max_length=240),
) -> Dict[str, Any]:
    """Search the allowlisted repository by metadata and bounded text body."""
    _require_project(project_id)
    try:
        return workspace_catalog.search(q, top_k=top_k, path=path)
    except CatalogPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/capabilities/catalog")
def capability_catalog(project_id: str, refresh: bool = Query(default=False)) -> Dict[str, Any]:
    """Return the modeling capability layer projected from the current KB.

    This endpoint is deliberately read-only.  It exposes standard workflow
    presets and free-assembly blocks, while keeping source files and model
    execution behind separate, approved boundaries.
    """
    _require_project(project_id)
    return capability_catalog_snapshot(force_refresh=refresh)


@app.get("/api/projects/{project_id}/capabilities/suggest")
def capability_suggest(
    project_id: str,
    q: str = Query(default="", max_length=2000),
    limit: int = Query(default=8, ge=1, le=20),
) -> Dict[str, Any]:
    """Give transparent cue-based archetype/method suggestions."""
    _require_project(project_id)
    catalog = capability_catalog_snapshot()
    result = _capability_suggestions(q, catalog, limit=limit)
    result["capability_revision"] = catalog.get("capability_revision")
    result["source"] = catalog.get("source", {})
    return result


def _safe_relative_source_path(value: Any) -> Optional[str]:
    """Keep only a relative KB path; never expose or resolve an absolute path."""
    if not isinstance(value, str):
        return None
    candidate = value.strip().replace("\\", "/")
    if not candidate or candidate.startswith("/") or re.match(r"^[A-Za-z]:", candidate):
        return None
    parts = candidate.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return candidate[:500]


def _content_pack_hit(raw: Mapping[str, Any], pack: Mapping[str, Any], index_revision: Any) -> Optional[Dict[str, Any]]:
    """Project one KB hit into a source-linked, non-executable evidence row."""
    path_rel = _safe_relative_source_path(raw.get("path_rel"))
    citation = str(raw.get("citation_ref", "")).strip()
    # Search results generated by KnowledgeBase are kbdoc references.  Keep a
    # strict check here as a second boundary in case another index adapter is
    # plugged in later.
    if not re.fullmatch(r"kbdoc:kbdoc_[0-9a-f]{16}(?:#p\d+)?", citation, flags=re.IGNORECASE):
        citation = ""
    if path_rel is None or not citation:
        return None
    pack_title = str(pack.get("title", pack.get("id", "内容包")))[:120]
    row: Dict[str, Any] = {
        "doc_id": raw.get("doc_id"),
        "title": str(raw.get("title", ""))[:240],
        "citation_ref": citation,
        "evidence_ref": citation,
        # ``path`` is intentionally an alias of the fenced relative path;
        # absolute Windows paths are never returned by this endpoint.
        "path": path_rel,
        "path_rel": path_rel,
        "extract_status": str(raw.get("extract_status", "pending")),
        "source_status": str(raw.get("source_status", "LOCAL_INDEXED")),
        "hash_status": raw.get("hash_status"),
        "kind": raw.get("kind"),
        "module": raw.get("module"),
        "years": list(raw.get("years") or []),
        "score": raw.get("score", 0),
        "snippet": str(raw.get("snippet", ""))[:320],
        "claim_class": "observed",
        "applicability_claim_class": "hypothesis",
        "usage": f"{pack_title}：候选证据",
        "usage_note": "仅证明资料命中与来源位置；将其用于模型或论文前需核对原文、单位、页码和独立验证。",
        "index_revision": index_revision,
    }
    if "preview" in raw:
        row["preview"] = str(raw.get("preview") or "")[:2400]
    return row


def _resolve_content_pack(
    project_id: str,
    pack_id: str,
    *,
    q: Optional[str] = None,
    module: Optional[str] = None,
    kind: Optional[str] = None,
    year: Optional[str] = None,
    extension: Optional[str] = None,
    top_k: int = 6,
    with_preview: bool = True,
    refresh: bool = False,
) -> Dict[str, Any]:
    """Resolve a built-in content pack against the current read-only KB index."""
    canonical_id = _safe_content_pack_id(pack_id)
    if canonical_id is None:
        raise HTTPException(status_code=404, detail={"code": "CONTENT_PACK_NOT_FOUND", "content_pack_id": str(pack_id)[:120]})
    catalog = capability_catalog_snapshot(force_refresh=refresh)
    pack = next((item for item in catalog.get("content_packs", []) if str(item.get("id")) == canonical_id), None)
    if not isinstance(pack, Mapping):
        raise HTTPException(status_code=404, detail={"code": "CONTENT_PACK_NOT_FOUND", "content_pack_id": canonical_id})
    # The catalogue call above establishes the snapshot.  A second summary is
    # cheap (normally cached) and gives the resolver an explicit source view.
    summary = knowledge_base.summary(force_refresh=False)
    pack_query = str(pack.get("query", "") or "").strip()
    effective_query = str(q if q is not None and str(q).strip() else pack_query).strip()[:240]
    bounded_top_k = max(1, min(12, int(top_k or 6)))
    search_result = knowledge_base.search(
        effective_query,
        module=module,
        kind=kind,
        year=year,
        extension=extension,
        top_k=bounded_top_k,
        with_preview=bool(with_preview),
    )
    index_revision = search_result.get("index_revision") or summary.get("index_revision")
    warnings = [str(item) for item in (search_result.get("warnings") or [])]
    if search_result.get("index_revision") and summary.get("index_revision") and search_result.get("index_revision") != summary.get("index_revision"):
        warnings.append("解析期间资料库索引版本发生变化；请重新 resolve 以获得同一快照。")
    rows: List[Dict[str, Any]] = []
    dropped_unsafe = 0
    for raw in search_result.get("results", []) or []:
        if not isinstance(raw, Mapping):
            continue
        projected = _content_pack_hit(raw, pack, index_revision)
        if projected is None:
            dropped_unsafe += 1
            continue
        rows.append(projected)
    if dropped_unsafe:
        warnings.append(f"已丢弃 {dropped_unsafe} 条缺少安全相对路径或合法 citation_ref 的命中。")
    status_counts: Dict[str, int] = {}
    for row in rows:
        status = str(row.get("extract_status", "pending"))
        status_counts[status] = status_counts.get(status, 0) + 1
    source_status = str(summary.get("source_status", "UNAVAILABLE"))
    if source_status == "UNAVAILABLE":
        coverage_state = "SOURCE_UNAVAILABLE"
    elif not rows:
        coverage_state = "NO_MATCH"
    elif int(summary.get("temporary_count", 0) or 0) > 0:
        coverage_state = "PARTIAL_PENDING"
    elif bool(search_result.get("truncated")):
        coverage_state = "PARTIAL_BOUNDED"
    elif any(item in status_counts for item in ("OCR_REQUIRED", "PREVIEW_UNAVAILABLE", "PREVIEW_UNAVAILABLE_LARGE", "TEXT_PARTIAL", "REINDEX_REQUIRED")):
        coverage_state = "PARTIAL_EXTRACTION"
    else:
        coverage_state = "RESOLVED"
    evidence_refs = list(dict.fromkeys(str(row["citation_ref"]) for row in rows if row.get("citation_ref")))
    coverage = _content_pack_coverage(
        summary,
        state=coverage_state,
        returned_count=len(rows),
        evidence_ref_count=len(evidence_refs),
        truncated=bool(search_result.get("truncated")),
        extract_status_counts=status_counts,
        query=effective_query,
    )
    coverage.update({
        "candidate_count": int(search_result.get("total_candidates", search_result.get("total", len(rows))) or 0),
        "scored_count": int(search_result.get("total", len(rows)) or 0),
        "metadata_only_results": sum(1 for row in rows if row.get("extract_status") in {"PREVIEW_UNAVAILABLE", "PREVIEW_UNAVAILABLE_LARGE", "OCR_REQUIRED"}),
    })
    pack_out = dict(pack)
    pack_out.update({
        "claim_class": "hypothesis",
        "evidence_refs": evidence_refs,
        "source_refs": evidence_refs,
        "coverage": coverage,
        "coverage_state": coverage_state,
    })
    if source_status == "LOCAL_PENDING":
        warnings.append("资料目录仍有临时文件；本次结果不是完整快照。")
    warnings.append("当前仅提供文档级 kbdoc 引用，尚未提供页级/段落级 kbchunk；候选证据不能自动升级论文结论。")
    resolution_payload = {
        "pack_id": canonical_id,
        "query": effective_query,
        "index_revision": index_revision,
        "evidence_refs": evidence_refs,
        "coverage": coverage,
    }
    resolution_serial = json.dumps(resolution_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": "content-pack-resolution/v1",
        "project_id": project_id,
        "pack_id": canonical_id,
        "pack": pack_out,
        "content_pack": pack_out,
        "query": effective_query,
        "query_source": "override" if q is not None and str(q).strip() else "pack_default",
        "index_revision": index_revision,
        "source_status": source_status,
        "source": {
            "root_id": summary.get("root_id"),
            "source_status": source_status,
            "index_revision": index_revision,
            "indexed_count": summary.get("indexed_count", summary.get("valid_count", 0)),
            "temporary_count": summary.get("temporary_count", 0),
            "catalog_consistent": bool(summary.get("catalog_consistent", False)),
        },
        "results": rows,
        "evidence_refs": evidence_refs,
        "citation_refs": evidence_refs,
        "coverage": coverage,
        "coverage_state": coverage_state,
        "claim_class": "hypothesis",
        "usage": "candidate_retrieval",
        "usage_note": "内容包解析结果用于候选资料与审查清单；需 Owner/独立审查后才能进入论文 claim。",
        "returned_count": len(rows),
        "total_candidates": search_result.get("total_candidates", search_result.get("total", len(rows))),
        "truncated": bool(search_result.get("truncated")),
        "warnings": list(dict.fromkeys(warnings)),
        "resolved_at": utc_now(),
        "resolution_revision": "content-pack:" + hashlib.sha256(resolution_serial.encode("utf-8")).hexdigest(),
    }


@app.get("/api/projects/{project_id}/capabilities/content-packs/{pack_id}/resolve")
def capability_content_pack_resolve(
    project_id: str,
    pack_id: str,
    q: Optional[str] = Query(default=None, max_length=240),
    module: Optional[str] = Query(default=None, max_length=160),
    kind: Optional[str] = Query(default=None, max_length=80),
    year: Optional[str] = Query(default=None, max_length=40),
    extension: Optional[str] = Query(default=None, max_length=16),
    top_k: int = Query(default=6, ge=1, le=12),
    with_preview: bool = Query(default=True),
    refresh: bool = Query(default=False),
) -> Dict[str, Any]:
    """Resolve one catalogue content pack using a bounded KB search.

    The route is strictly read-only: it returns relative source paths and
    source citations, never executes/open arbitrary files, and never mutates
    the collaboration event store.
    """
    _require_project(project_id)
    return _resolve_content_pack(
        project_id,
        pack_id,
        q=q,
        module=module,
        kind=kind,
        year=year,
        extension=extension,
        top_k=top_k,
        with_preview=with_preview,
        refresh=refresh,
    )


@app.get("/api/capabilities/content-packs/{pack_id}/resolve")
def capabilities_content_pack_resolve_alias(
    pack_id: str,
    q: Optional[str] = Query(default=None, max_length=240),
    module: Optional[str] = Query(default=None, max_length=160),
    kind: Optional[str] = Query(default=None, max_length=80),
    year: Optional[str] = Query(default=None, max_length=40),
    extension: Optional[str] = Query(default=None, max_length=16),
    top_k: int = Query(default=6, ge=1, le=12),
    with_preview: bool = Query(default=True),
    refresh: bool = Query(default=False),
) -> Dict[str, Any]:
    """Adapter-friendly alias for the project-scoped resolver."""
    return _resolve_content_pack(
        PROJECT_ID,
        pack_id,
        q=q,
        module=module,
        kind=kind,
        year=year,
        extension=extension,
        top_k=top_k,
        with_preview=with_preview,
        refresh=refresh,
    )


INNOVATION_TEXT_FIELDS = ("baseline", "difference", "necessity", "boundary", "validation")


def _normalise_innovation_card(raw: Any) -> Optional[Dict[str, Any]]:
    """Keep the user-authored innovation card small, deterministic and safe.

    The card is deliberately metadata-only: arbitrary nested payloads,
    executable snippets and hidden instructions are discarded before they can
    affect an assembly hash or event projection.  Text remains a hypothesis
    until a reviewer binds it to a problem, baseline and clean validation.
    """
    if not isinstance(raw, Mapping):
        return None
    card: Dict[str, Any] = {}
    for field in INNOVATION_TEXT_FIELDS:
        value = raw.get(field, "")
        if isinstance(value, str):
            value = value.strip()[:2000]
        else:
            value = ""
        if value:
            card[field] = value
    subproblem = raw.get("subproblem_id")
    if isinstance(subproblem, str) and subproblem.strip():
        card["subproblem_id"] = subproblem.strip()[:40]
    refs = raw.get("evidence_refs")
    if isinstance(refs, list):
        safe_refs = [str(item).strip()[:200] for item in refs[:20] if isinstance(item, (str, int, float)) and str(item).strip()]
        if safe_refs:
            card["evidence_refs"] = safe_refs
    # Never allow a caller to label a novelty claim as observed/verified.
    card["claim_class"] = "hypothesis"
    return card if any(key in card for key in INNOVATION_TEXT_FIELDS) else None


def _materialise_assembly(request: Any, catalog: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate references and build a deterministic assembly projection.

    ``request`` may be the dry-run or commit input model.  Keeping this logic
    in one place prevents the UI and the persistence endpoint from silently
    disagreeing about what an assembly revision means.
    """
    source = catalog.get("source", {})
    current_revision = source.get("index_revision")
    requested_catalog_revision = getattr(request, "capability_revision", None) or getattr(request, "base_revision", None)
    if requested_catalog_revision and requested_catalog_revision not in {current_revision, catalog.get("capability_revision")}:
        raise HTTPException(status_code=409, detail={"code": "CAPABILITY_REVISION_STALE", "current_revision": current_revision, "capability_revision": catalog.get("capability_revision")})
    block_ids = {str(block.get("id")) for block in catalog.get("workflow_blocks", [])}
    method_ids = {str(method.get("id")) for method in catalog.get("methods", [])}
    method_by_id = {str(method.get("id")): method for method in catalog.get("methods", [])}
    preset_ids = {str(preset.get("id")) for preset in catalog.get("workflow_presets", [])}
    archetype_ids = {str(item.get("id")) for item in catalog.get("problem_archetypes", [])}
    content_pack_ids_available = {str(item.get("id")) for item in catalog.get("content_packs", [])}
    nodes = list(getattr(request, "nodes", []) or [])
    edges = list(getattr(request, "edges", []) or [])
    invalid_methods = [node.method_id for node in nodes if node.method_id and node.method_id not in method_ids]
    invalid_blocks = [node.block_id for node in nodes if node.block_id not in block_ids]
    if invalid_methods or invalid_blocks:
        raise HTTPException(status_code=422, detail={"code": "CAPABILITY_REF_INVALID", "invalid_methods": invalid_methods[:10], "invalid_blocks": invalid_blocks[:10]})
    family_default_block = {
        "statistical": "baseline-model", "classification": "baseline-model", "ensemble": "baseline-model",
        "time-series": "baseline-model", "survival": "baseline-model", "optimization": "optimization",
        "mechanism": "mechanism-model", "simulation": "simulation", "validation": "sensitivity",
    }
    method_block_warnings = []
    for node in nodes:
        if not node.method_id:
            continue
        method = method_by_id.get(node.method_id) or {}
        expected = family_default_block.get(str(method.get("family", "")))
        if expected and node.block_id != expected:
            method_block_warnings.append({
                "node_id": node.node_id,
                "method_id": node.method_id,
                "family": method.get("family"),
                "selected_block": node.block_id,
                "suggested_block": expected,
                "claim_class": "hypothesis",
            })
    preset_id = getattr(request, "preset_id", None)
    archetype_id = getattr(request, "archetype_id", None)
    if preset_id and preset_id not in preset_ids:
        raise HTTPException(status_code=422, detail={"code": "WORKFLOW_PRESET_NOT_FOUND", "preset_id": preset_id})
    if archetype_id and archetype_id not in archetype_ids:
        raise HTTPException(status_code=422, detail={"code": "PROBLEM_ARCHETYPE_NOT_FOUND", "archetype_id": archetype_id})
    requested_content_packs = [str(item).strip() for item in (getattr(request, "content_pack_ids", []) or []) if str(item).strip()]
    previous_content_packs = [str(item).strip() for item in (getattr(request, "previous_content_pack_ids", []) or []) if str(item).strip()]
    invalid_content_packs = sorted((set(requested_content_packs) | set(previous_content_packs)).difference(content_pack_ids_available))
    if invalid_content_packs:
        raise HTTPException(status_code=422, detail={"code": "CONTENT_PACK_NOT_FOUND", "content_pack_ids": invalid_content_packs[:20]})
    content_pack_ids = sorted(set(requested_content_packs))
    previous_content_pack_ids = sorted(set(previous_content_packs))
    content_pack_evidence_refs = _normalise_content_pack_evidence_refs(
        getattr(request, "content_pack_evidence_refs", [])
    )
    content_pack_index_revision = getattr(request, "content_pack_index_revision", None)
    if content_pack_evidence_refs:
        if not content_pack_index_revision:
            raise HTTPException(status_code=422, detail={
                "code": "CONTENT_PACK_INDEX_REVISION_REQUIRED",
                "message": "提交内容包证据引用时必须同时提供 resolver 返回的 content_pack_index_revision",
            })
        if content_pack_index_revision != current_revision:
            raise HTTPException(status_code=409, detail={
                "code": "CONTENT_PACK_INDEX_REVISION_STALE",
                "current_revision": current_revision,
                "content_pack_index_revision": content_pack_index_revision,
            })
    # Invalidly shaped refs are ignored rather than copied into an assembly;
    # the client can still submit an unbound content-pack draft.  The bounded
    # resolver is the only supported way to obtain candidate refs.
    content_pack_resolution_revision = getattr(request, "content_pack_resolution_revision", None)
    if content_pack_resolution_revision is not None:
        content_pack_resolution_revision = str(content_pack_resolution_revision).strip()[:200]
        if content_pack_resolution_revision and not re.fullmatch(r"content-pack:[0-9a-fA-F]{64}", content_pack_resolution_revision):
            raise HTTPException(status_code=422, detail={
                "code": "CONTENT_PACK_RESOLUTION_REVISION_INVALID",
                "message": "content_pack_resolution_revision 必须来自 resolver",
            })
    node_map: Dict[str, str] = {}
    duplicate_nodes: List[str] = []
    for node in nodes:
        if node.node_id in node_map:
            duplicate_nodes.append(node.node_id)
        node_map[node.node_id] = node.block_id
    if duplicate_nodes:
        raise HTTPException(status_code=422, detail={"code": "DUPLICATE_COMPOSITION_NODE", "nodes": sorted(set(duplicate_nodes))})
    edge_payload = [edge.model_dump() if hasattr(edge, "model_dump") else dict(edge) for edge in edges]
    report: Dict[str, Any] = {"valid": False, "errors": ["composition_not_checked"], "topological_order": [], "node_count": len(node_map), "edge_count": len(edge_payload)}
    try:
        composed = compose_workflow(node_map, edge_payload, blocks=BUILTIN_BLOCKS)
        report = composed["validation"]
    except ValueError as error:
        report = {**report, "errors": [str(error)]}
    normalized_nodes = []
    for node in nodes:
        normalized_nodes.append({
            **(node.model_dump() if hasattr(node, "model_dump") else dict(node)),
            "status": "READY_FOR_REVIEW" if report.get("valid") else "BLOCKED",
            "claim_class": "hypothesis",
        })
    normalized_edges = edge_payload
    previous_nodes = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in (getattr(request, "previous_nodes", []) or [])]
    previous_edges = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in (getattr(request, "previous_edges", []) or [])]
    innovation_card = _normalise_innovation_card(getattr(request, "innovation_card", None))
    previous_innovation_card = _normalise_innovation_card(getattr(request, "previous_innovation_card", None))
    diff = composition_diff(
        previous_nodes,
        previous_edges,
        normalized_nodes,
        normalized_edges,
        previous_innovation=previous_innovation_card,
        current_innovation=innovation_card,
        previous_content_pack_ids=previous_content_pack_ids,
        current_content_pack_ids=content_pack_ids,
    )
    innovation_missing = [field for field in INNOVATION_TEXT_FIELDS if not innovation_card or not innovation_card.get(field)]
    innovation_gate = {
        "present": bool(innovation_card),
        "ready": bool(innovation_card) and not innovation_missing,
        "status": "READY_FOR_REVIEW" if bool(innovation_card) and not innovation_missing else "DRAFT_UNVERIFIED",
        "missing": innovation_missing,
        "claim_class": "hypothesis",
    }
    selected_content_packs = [item for item in catalog.get("content_packs", []) if str(item.get("id")) in content_pack_ids]
    content_pack_coverage = {
        str(item.get("id")): copy.deepcopy(item.get("coverage") or {
            "schema_version": CONTENT_PACK_COVERAGE_SCHEMA,
            "state": item.get("coverage_state", "PENDING_RESOLUTION"),
            "index_revision": current_revision,
            "evidence_ref_count": 0,
        })
        for item in selected_content_packs
    }
    catalog_content_pack_evidence_refs = sorted({
        str(ref)
        for item in selected_content_packs
        for ref in (item.get("evidence_refs") or [])
        if isinstance(ref, str) and re.fullmatch(r"kbdoc:kbdoc_[0-9a-f]{16}(?:#p\d+)?", ref, flags=re.IGNORECASE)
    })
    content_pack_evidence_refs = sorted(set(content_pack_evidence_refs) | set(catalog_content_pack_evidence_refs), key=str.lower)
    content_pack_evidence_state = "BOUND_CANDIDATE" if content_pack_evidence_refs else "UNBOUND"
    assembly_payload = {
        "schema_version": "assembly/v1",
        "project_id": PROJECT_ID,
        "preset_id": preset_id,
        "archetype_id": archetype_id,
        "scope": list(getattr(request, "scope", []) or []),
        "catalog_revision": catalog.get("capability_revision"),
        "source_revision": current_revision,
        "nodes": normalized_nodes,
        "edges": normalized_edges,
        "innovation_card": innovation_card,
        "innovation_gate": innovation_gate,
        "content_pack_ids": content_pack_ids,
        "content_packs": selected_content_packs,
        "content_pack_evidence_refs": content_pack_evidence_refs,
        "content_pack_index_revision": content_pack_index_revision if content_pack_evidence_refs else None,
        "content_pack_resolution_revision": content_pack_resolution_revision if content_pack_evidence_refs else None,
        "content_pack_evidence_state": content_pack_evidence_state,
        "content_pack_coverage": content_pack_coverage,
        "method_block_warnings": method_block_warnings,
        "validation": report,
        "diff": diff,
    }
    assembly_serial = json.dumps(assembly_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assembly_revision = "assembly:" + hashlib.sha256(assembly_serial.encode("utf-8")).hexdigest()
    return {
        "assembly_revision": assembly_revision,
        "catalog_revision": catalog.get("capability_revision"),
        "source_revision": current_revision,
        "composition": {"nodes": normalized_nodes, "edges": normalized_edges},
        "validation": report,
        "diff": diff,
        "innovation_card": innovation_card,
        "innovation_gate": innovation_gate,
        "content_pack_ids": content_pack_ids,
        "content_packs": selected_content_packs,
        "content_pack_evidence_refs": content_pack_evidence_refs,
        "content_pack_index_revision": content_pack_index_revision if content_pack_evidence_refs else None,
        "content_pack_resolution_revision": content_pack_resolution_revision if content_pack_evidence_refs else None,
        "content_pack_evidence_state": content_pack_evidence_state,
        "content_pack_coverage": content_pack_coverage,
        "method_block_warnings": method_block_warnings,
        "payload": assembly_payload,
        "status": "READY_FOR_REVIEW" if report.get("valid") else "BLOCKED",
    }


@app.post("/api/projects/{project_id}/capabilities/compose")
def capability_compose(project_id: str, request: WorkflowComposeIn) -> Dict[str, Any]:
    """Validate a typed, user-composed workflow and return an assembly revision.

    Composition is a dry-run: it does not dispatch agents, execute code, or
    alter the event store.  A later persistence endpoint can attach an
    Owner-approved composition to a run after this report is reviewed.
    """
    _require_project(project_id)
    catalog = capability_catalog_snapshot()
    assembled = _materialise_assembly(request, catalog)
    return {
        "accepted": True,
        "status": assembled["status"],
        "assembly_revision": assembled["assembly_revision"],
        "catalog_revision": assembled["catalog_revision"],
        "source_revision": assembled["source_revision"],
        "composition": assembled["composition"],
        "validation": assembled["validation"],
        "diff": assembled["diff"],
        "innovation_card": assembled.get("innovation_card"),
        "innovation_gate": assembled.get("innovation_gate"),
        "content_pack_ids": assembled.get("content_pack_ids", []),
        "content_packs": assembled.get("content_packs", []),
        "content_pack_evidence_refs": assembled.get("content_pack_evidence_refs", []),
        "content_pack_index_revision": assembled.get("content_pack_index_revision"),
        "content_pack_resolution_revision": assembled.get("content_pack_resolution_revision"),
        "content_pack_evidence_state": assembled.get("content_pack_evidence_state", "UNBOUND"),
        "content_pack_coverage": assembled.get("content_pack_coverage", {}),
        "required_block_ids": sorted(REQUIRED_BLOCK_IDS),
        "custom_block_count": len(assembled["validation"].get("custom_block_ids", [])),
        "method_block_warnings": assembled.get("method_block_warnings", []),
        "warnings": [
            "组合校验只证明结构、端口和证据链形状；不证明参数、数值结果或论文结论。",
            "方法卡与本地资料引用仍需按当前题面和独立 clean-run 复核。",
        ],
    }


@app.post("/api/projects/{project_id}/capabilities/commit")
async def capability_commit(project_id: str, request: AssemblyCommitIn) -> Dict[str, Any]:
    """Persist a bounded assembly projection and publish one sync event.

    This is the bridge between the free canvas and the group chat.  It stores
    only the typed composition metadata; no source file, model call or code is
    executed.  ``SUBMIT_REVIEW`` additionally requires every hard gate.
    """
    _require_project(project_id)
    catalog = capability_catalog_snapshot()
    assembled = _materialise_assembly(request, catalog)
    if request.source_revision and request.source_revision != assembled["source_revision"]:
        raise HTTPException(status_code=409, detail={"code": "ASSEMBLY_SOURCE_REVISION_STALE", "current_revision": assembled["source_revision"]})
    if request.assembly_revision != assembled["assembly_revision"]:
        raise HTTPException(status_code=409, detail={"code": "ASSEMBLY_REVISION_MISMATCH", "expected": assembled["assembly_revision"], "received": request.assembly_revision})
    if request.action == "SUBMIT_REVIEW" and not assembled["validation"].get("valid"):
        raise HTTPException(status_code=409, detail={"code": "ASSEMBLY_GATE_BLOCKED", "validation": assembled["validation"]})
    current = store.assemblies.get("main")
    if request.previous_assembly_revision and current and current.get("assembly_revision") != request.previous_assembly_revision:
        raise HTTPException(status_code=409, detail={"code": "ASSEMBLY_PREVIOUS_REVISION_MISMATCH", "current_revision": current.get("assembly_revision")})
    recorded: Dict[str, Any] = {}

    def apply_assembly(event: Event) -> None:
        record = {
            **assembled["payload"],
            "assembly_revision": assembled["assembly_revision"],
            "status": assembled["status"],
            "action": request.action,
            "actor_id": request.actor_id,
            "event_ref": event.event_id,
            "updated_at": event.timestamp,
            "claim_class": "hypothesis",
        }
        store.assemblies["main"] = record
        recorded.update(copy.deepcopy(record))

    event = await store.append(
        actor_id=request.actor_id,
        event_type="ASSEMBLY_UPDATED",
        channel="assembly",
        base_revision=request.base_revision,
        idempotency_key=request.idempotency_key,
        payload={
            "assembly_revision": assembled["assembly_revision"],
            "capability_revision": assembled["catalog_revision"],
            "action": request.action,
            "diff": assembled["diff"],
            "innovation_card": assembled.get("innovation_card"),
            "innovation_gate": assembled.get("innovation_gate"),
            "content_pack_ids": assembled.get("content_pack_ids", []),
            "content_pack_evidence_refs": assembled.get("content_pack_evidence_refs", []),
            "content_pack_index_revision": assembled.get("content_pack_index_revision"),
            "content_pack_resolution_revision": assembled.get("content_pack_resolution_revision"),
            "content_pack_evidence_state": assembled.get("content_pack_evidence_state", "UNBOUND"),
            "content_pack_coverage": assembled.get("content_pack_coverage", {}),
            "method_block_warnings": assembled.get("method_block_warnings", []),
            "status": assembled["status"],
        },
        state_mutator=apply_assembly,
    )
    if not recorded:
        recorded.update(copy.deepcopy(store.assemblies.get("main") or {}))
    return {
        "accepted": True,
        "status": recorded.get("status", assembled["status"]),
        "assembly": recorded,
        "diff": assembled["diff"],
        "event": event.model_dump(),
        "revision": event.revision or store.revision,
    }


@app.post("/api/projects/{project_id}/capabilities/problem-contract")
def capability_problem_contract(project_id: str, request: ProblemContractIn) -> Dict[str, Any]:
    """Create a dynamic, source-linked problem-contract draft.

    The extractor is intentionally conservative: it records lexical evidence
    and hypotheses, leaving units, semantics, and truth to Scope/Owner review.
    """
    _require_project(project_id)
    return build_problem_contract(request.text, request.source_refs)


# Short aliases for external/local Agent adapters.
@app.get("/api/capabilities/catalog")
def capabilities_catalog_alias(refresh: bool = Query(default=False)) -> Dict[str, Any]:
    return capability_catalog_snapshot(force_refresh=refresh)


@app.get("/api/capabilities/suggest")
def capabilities_suggest_alias(q: str = Query(default="", max_length=2000), limit: int = Query(default=8, ge=1, le=20)) -> Dict[str, Any]:
    catalog = capability_catalog_snapshot()
    result = _capability_suggestions(q, catalog, limit=limit)
    result["capability_revision"] = catalog.get("capability_revision")
    result["source"] = catalog.get("source", {})
    return result


@app.post("/api/capabilities/problem-contract")
def capabilities_problem_contract_alias(request: ProblemContractIn) -> Dict[str, Any]:
    return build_problem_contract(request.text, request.source_refs)


@app.get("/api/projects/{project_id}/knowledge/documents/{doc_id}")
def knowledge_document(project_id: str, doc_id: str, include_preview: bool = Query(default=True)) -> Dict[str, Any]:
    _require_project(project_id)
    document = knowledge_base.document(doc_id, include_preview=include_preview)
    if document is None:
        raise HTTPException(status_code=404, detail={"code": "KB_DOCUMENT_NOT_FOUND"})
    if document.get("source_status") == "SOURCE_CHANGED":
        raise HTTPException(status_code=409, detail={"code": "KB_SOURCE_CHANGED", "message": "源文件已变化，请先刷新资料库快照"})
    return {"document": document, "index_revision": knowledge_base.summary().get("index_revision")}


@app.get("/api/projects/{project_id}/knowledge/documents/{doc_id}/file")
def knowledge_file(project_id: str, doc_id: str) -> FileResponse:
    """Open one allow-listed source file after an explicit user click."""
    _require_project(project_id)
    path = knowledge_base.file_path(doc_id)
    if path is None:
        raise HTTPException(status_code=404, detail={"code": "KB_FILE_NOT_AVAILABLE"})
    try:
        if path.stat().st_size > MAX_OPEN_FILE_BYTES:
            raise HTTPException(status_code=413, detail={"code": "KB_FILE_TOO_LARGE", "message": "原文件超过本地内联打开上限，请在文件管理器中处理"})
    except OSError:
        raise HTTPException(status_code=404, detail={"code": "KB_FILE_NOT_AVAILABLE"})
    import mimetypes
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name, content_disposition_type="inline")


# Short aliases keep the adapter convenient for non-UI agents while the
# project-scoped routes above remain the canonical browser contract.
@app.get("/api/kb/status")
def kb_status(refresh: bool = Query(default=False)) -> Dict[str, Any]:
    return knowledge_base.summary(force_refresh=refresh)


@app.get("/api/kb/search")
def kb_search(
    q: str = Query(default="", max_length=240),
    module: Optional[str] = Query(default=None, max_length=160),
    kind: Optional[str] = Query(default=None, max_length=80),
    year: Optional[str] = Query(default=None, max_length=40),
    extension: Optional[str] = Query(default=None, max_length=16),
    top_k: int = Query(default=8, ge=1, le=20),
    with_preview: bool = Query(default=True),
) -> Dict[str, Any]:
    return knowledge_base.search(q, module=module, kind=kind, year=year, extension=extension, top_k=top_k, with_preview=with_preview)


@app.get("/api/kb/context")
def kb_context(
    q: str = Query(default="", max_length=240),
    module: Optional[str] = Query(default=None, max_length=160),
    kind: Optional[str] = Query(default=None, max_length=80),
    year: Optional[str] = Query(default=None, max_length=40),
    extension: Optional[str] = Query(default=None, max_length=16),
    top_k: int = Query(default=6, ge=1, le=12),
) -> Dict[str, Any]:
    return knowledge_base.context(q, module=module, kind=kind, year=year, extension=extension, top_k=top_k)


@app.get("/api/projects/{project_id}/snapshot")
async def snapshot(project_id: str) -> Dict[str, Any]:
    if project_id != PROJECT_ID:
        raise HTTPException(status_code=404, detail="project not found")
    async with store.get_lock():
        integrity = source_integrity_snapshot()
        return {
            "project_id": PROJECT_ID,
            "run_id": RUN_ID,
            "revision": store.revision,
            "context": {
                "project_id": PROJECT_ID,
                "run_id": RUN_ID,
                "mode": "live",
                "source_status": "local_event_store",
                "input_revision": INPUT_REVISION,
                "worktree_revision": INPUT_REVISION,
                "control_revision": store.revision,
                "event_chain_valid": store.chain_valid,
                "projection_integrity": store.projection_integrity,
                "source_integrity": integrity,
            },
            "tasks": copy.deepcopy(list(store.tasks.values())),
            "messages": copy.deepcopy(store.messages[-100:]),
            "approvals": copy.deepcopy(store.approvals[-50:]),
            "relays": copy.deepcopy(store.relays[-50:]),
            "assemblies": copy.deepcopy(store.assemblies),
            "assembly": copy.deepcopy(store.assemblies.get("main")),
            "findings": copy.deepcopy(store.findings),
            "release_gate": release_gate_snapshot(store.tasks, store.approvals),
            # The local gateway does not own a contest problem contract yet.
            # Expose that absence explicitly so a client cannot reuse its
            # generic fixture Q-cards as if they came from the live input.
            "modeling": {
                "source_status": "unavailable",
                "prompt_refs": [],
                "subproblems": [],
                "variables": [],
                "model_edges": [],
                "validation_plans": [],
                "gates": [],
            },
            "next_seq": store.events[-1].seq if store.events else 0,
            "agent_sync": {"antigravity": "PENDING_RELAY"},
            "event_chain_valid": store.chain_valid,
            "projection_integrity": store.projection_integrity,
            "source_integrity": integrity,
        }


@app.get("/api/projects/{project_id}/events")
async def events(
    project_id: str,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> Dict[str, Any]:
    if project_id != PROJECT_ID:
        raise HTTPException(status_code=404, detail="project not found")
    async with store.get_lock():
        pending = [event for event in store.events if event.seq > after_seq]
        page = pending[:limit]
        return {
            "events": [event.model_dump() for event in page],
            "next_seq": store.events[-1].seq if store.events else 0,
            "has_more": len(pending) > len(page),
            "next_after_seq": page[-1].seq if page else after_seq,
        }


@app.post("/api/projects/{project_id}/dispatch")
async def dispatch_task(project_id: str, request: DispatchIn) -> Dict[str, Any]:
    """Register a coordinator-issued task envelope without running a model.

    The local API intentionally stops at the dispatch boundary.  A real
    worker adapter consumes this envelope asynchronously and later posts a
    result/review event; this endpoint never pretends that dispatch means
    completion.
    """
    if project_id != PROJECT_ID:
        raise HTTPException(status_code=404, detail="project not found")
    if request.requested_by not in {"owner", "coordinator", "codex/root"}:
        raise HTTPException(status_code=403, detail={"code": "DISPATCH_FORBIDDEN", "required_role": "owner_or_coordinator"})
    validate_revision(request.input_revision, "input_revision")
    normalized_write_set: List[str] = []
    try:
        for path in request.write_set:
            normalized_write_set.append(_normalise_write_set_path(path))
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": "INVALID_WRITE_SET", "message": str(error)})
    task_record = {
        "id": request.task_id,
        "title": request.title,
        "status": "QUEUED",
        "owner": request.owner_id,
        "reviewer": request.reviewer_id,
        "objective": request.objective,
        "depends_on": list(request.depends_on),
        "write_set": normalized_write_set,
        "capabilities": dict(request.capabilities),
        "acceptance": list(request.acceptance),
        "input_revision": request.input_revision,
        "mode": request.mode,
    }
    created: Dict[str, Any] = {}

    def apply_dispatch(_: Event) -> None:
        for dependency in request.depends_on:
            if dependency == request.task_id or dependency not in store.tasks:
                raise HTTPException(status_code=422, detail={"code": "INVALID_DEPENDENCY", "dependency": dependency})
        for existing_id, existing_task in store.tasks.items():
            if existing_id == request.task_id or existing_task.get("status") in {"CANCELLED", "SUPERSEDED", "RELEASED"}:
                continue
            existing_write_set = existing_task.get("write_set") or []
            if existing_write_set and write_sets_conflict(normalized_write_set, existing_write_set):
                raise HTTPException(status_code=409, detail={"code": "WRITE_SET_CONFLICT", "task_id": existing_id})
        current = store.tasks.get(request.task_id)
        if current and current.get("status") in {"IN_PROGRESS", "READY_FOR_REVIEW", "VERIFIED", "INTEGRATED", "ACCEPTED", "RELEASED"}:
            raise HTTPException(status_code=409, detail={"code": "TASK_ALREADY_ACTIVE", "status": current.get("status")})
        proposed_graph = {task_id: list(task.get("depends_on") or []) for task_id, task in store.tasks.items()}
        proposed_graph[request.task_id] = list(request.depends_on)
        try:
            validate_dependency_graph(proposed_graph)
        except ValueError as error:
            raise HTTPException(status_code=422, detail={"code": "INVALID_DEPENDENCY_GRAPH", "message": str(error)})
        store.tasks[request.task_id] = dict(task_record)
        created.update(store.tasks[request.task_id])

    event = await store.append(
        actor_id=request.requested_by,
        event_type="TASK_DISPATCHED",
        task_id=request.task_id,
        base_revision=request.base_revision,
        idempotency_key=request.idempotency_key,
        payload={"task": task_record},
        state_mutator=apply_dispatch,
    )
    if not created:
        created.update(store.tasks[request.task_id])
    return {"accepted": True, "task": created, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/projects/{project_id}/messages")
async def post_message(project_id: str, message: MessageIn) -> Dict[str, Any]:
    if project_id != PROJECT_ID:
        raise HTTPException(status_code=404, detail="project not found")
    if message.target_revision:
        validate_target_revision(message.target_revision, "target_revision")
    if message.assembly_revision and not re.fullmatch(r"assembly:[0-9a-fA-F]{64}", message.assembly_revision):
        raise HTTPException(status_code=422, detail={"code": "INVALID_ASSEMBLY_REVISION"})
    if message.capability_revision and not re.fullmatch(r"cap:[0-9a-fA-F]{64}", message.capability_revision):
        raise HTTPException(status_code=422, detail={"code": "INVALID_CAPABILITY_REVISION"})
    invalid_refs = [ref for ref in message.evidence_refs if not valid_evidence_ref(ref)]
    if invalid_refs:
        raise HTTPException(status_code=422, detail={"code": "INVALID_EVIDENCE_REF", "refs": invalid_refs[:5]})
    provenance = modeling_provenance(message)
    event = await store.append(
        actor_id=message.sender_id,
        event_type="MESSAGE",
        channel=message.channel,
        base_revision=message.base_revision,
        idempotency_key=message.idempotency_key,
        payload={
            "text": message.text,
            "mode": message.mode,
            "claim_class": message.claim_class,
            "task_id": message.task_id,
            "subproblem_id": message.subproblem_id,
            "evidence_refs": list(message.evidence_refs),
            "target_revision": message.target_revision,
            "assembly_revision": message.assembly_revision,
            "capability_revision": message.capability_revision,
            "provenance_status": provenance["provenance_status"],
        },
        message_factory=lambda created: {
            "message_id": created.event_id,
            "sender_id": message.sender_id,
            "channel": message.channel,
            "text": message.text,
            "mode": message.mode,
            "claim_class": provenance["claim_class"],
            "task_id": message.task_id,
            "subproblem_id": message.subproblem_id,
            "evidence_refs": list(message.evidence_refs),
            "target_revision": message.target_revision,
            "assembly_revision": message.assembly_revision,
            "capability_revision": message.capability_revision,
            "status": provenance["provenance_status"],
            "provenance_status": provenance["provenance_status"],
            "timestamp": created.timestamp,
            "event_ref": created.event_id,
        },
    )
    return {"accepted": True, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/tasks/{task_id}/claim")
async def claim_task(task_id: str, request: ClaimRequest) -> Dict[str, Any]:
    task = store.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    claimed: Dict[str, Any] = {}
    claim_payload: Dict[str, Any] = {"task_id": task_id, "agent_id": request.agent_id}

    def apply_claim(_: Event) -> None:
        current = store.tasks[task_id]
        status = current.get("status")
        # Failed and timed-out attempts must be explicitly requeued by the
        # Owner/coordinator before another worker can claim them.  Keeping
        # retry as a visible state transition preserves the prior result,
        # increments the audit trail, and prevents a direct claim from
        # bypassing the retry authorization/CAS gate.  An expired lease is
        # still reclaimable because its task remains IN_PROGRESS.
        if status not in {"QUEUED", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "TASK_NOT_CLAIMABLE", "status": status})
        for dependency in current.get("depends_on") or []:
            dependency_task = store.tasks.get(dependency)
            if dependency_task is None or dependency_task.get("status") not in {"VERIFIED", "INTEGRATED", "ACCEPTED", "RELEASED"}:
                raise HTTPException(status_code=409, detail={"code": "DEPENDENCY_NOT_READY", "dependency": dependency})
        existing_lease = current.get("lease") or {"fencing_epoch": current.get("last_fencing_epoch", 0)}
        existing_holder = current.get("claimed_by") or (existing_lease or {}).get("holder")
        if status == "IN_PROGRESS" and existing_holder not in {None, request.agent_id} and not lease_expired(existing_lease):
            raise HTTPException(status_code=409, detail={"code": "TASK_LEASE_HELD", "holder": existing_holder, "expires_at": (existing_lease or {}).get("expires_at")})
        # A queued task is already assigned by the coordinator's envelope.  A
        # different worker must arrive through the explicit handoff/requeue
        # path; otherwise any caller of this local (unauthenticated) API could
        # silently take another agent's write set.  Coordinator/owner-created
        # placeholder assignments remain claimable by a local adapter.
        assigned_owner = str(current.get("owner") or "").strip()
        open_assignment = {"", "unassigned", "coordinator", "codex/root", "owner", "user"}
        if status != "IN_PROGRESS" and assigned_owner.lower() not in open_assignment and request.agent_id != assigned_owner:
            raise HTTPException(status_code=403, detail={"code": "TASK_OWNER_MISMATCH", "owner": assigned_owner, "agent_id": request.agent_id})
        # A claim on an expired lease is an explicit reclaim.  ``new_lease``
        # increments the fencing epoch, so writes from the old worker are
        # rejected even if they arrive after the reclaim race.
        current.update({"status": "IN_PROGRESS", "claimed_by": request.agent_id, "lease": new_lease(existing_lease, 1800, request.agent_id)})
        claimed.update(current)
        claim_payload["task"] = dict(current)

    event = await store.append(
        actor_id=request.agent_id,
        event_type="TASK_CLAIMED",
        task_id=task_id,
        base_revision=request.base_revision,
        idempotency_key=request.idempotency_key,
        payload=claim_payload,
        state_mutator=apply_claim,
    )
    if not claimed:
        claimed.update(store.tasks[task_id])
    return {"accepted": True, "task": claimed, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/tasks/{task_id}/result")
async def submit_task_result(task_id: str, result: ResultIn) -> Dict[str, Any]:
    """Commit a worker result and move its task to a reviewable state.

    Result submission is deliberately tied to the current lease/fencing epoch:
    an old worker must not be able to publish after another worker has reclaimed
    the task.  The event carries a complete task projection so an idempotent
    replay can return the original response even if the task changed later.
    """
    if task_id not in store.tasks:
        raise HTTPException(status_code=404, detail="task not found")
    submitted: Dict[str, Any] = {}
    result_payload = result.model_dump()
    result_gate = validation_gate(result_payload, task_record=store.tasks.get(task_id))
    # Explicit modeling submissions are strict at ingress.  Legacy payloads
    # without these fields remain readable as UNVERIFIED so old adapters can
    # migrate, but they are blocked later by the review acceptance gate.
    explicit_contract = result.problem_type is not None or bool({"problem_type", "validation_checks"}.intersection(result.model_fields_set))
    if result.status == "READY_FOR_REVIEW" and explicit_contract and not result_gate["ready"]:
        raise HTTPException(status_code=422, detail={"code": "VALIDATION_STRUCTURE_INVALID", "gate": result_gate})
    result_payload["validation_gate"] = result_gate
    result_payload["provenance_gate"] = artifact_provenance_gate(result_payload, task_record=store.tasks.get(task_id))

    def apply_result(_: Event) -> None:
        current = store.tasks[task_id]
        if current.get("status") != "IN_PROGRESS":
            raise HTTPException(status_code=409, detail={"code": "RESULT_STATE_INVALID", "status": current.get("status"), "required": "IN_PROGRESS"})
        lease = current.get("lease") or {}
        holder = current.get("claimed_by") or lease.get("holder")
        if holder != result.agent_id:
            raise HTTPException(status_code=409, detail={"code": "RESULT_NOT_OWNER", "holder": holder})
        try:
            current_epoch = int(lease.get("fencing_epoch", -1))
        except (TypeError, ValueError):
            current_epoch = -1
        if current_epoch != result.fencing_epoch:
            raise HTTPException(status_code=409, detail={"code": "STALE_FENCING_EPOCH", "holder": holder, "fencing_epoch": lease.get("fencing_epoch")})
        if lease_expired(lease):
            raise HTTPException(status_code=409, detail={"code": "LEASE_EXPIRED", "expires_at": lease.get("expires_at")})
        invalid_ref = next((ref for ref in [*result.artifact_refs, *result.evidence_refs] if not valid_evidence_ref(ref)), None)
        if invalid_ref is not None:
            raise HTTPException(status_code=422, detail={"code": "INVALID_EVIDENCE_REF", "reference": invalid_ref})
        result_record = {
            "agent_id": result.agent_id,
            "fencing_epoch": result.fencing_epoch,
            "status": result.status,
            "summary": result.summary,
            "artifact_refs": list(result.artifact_refs),
            "evidence_refs": list(result.evidence_refs),
            "commands": list(result.commands),
            "result_hash": result.result_hash,
            "problem_type": result.problem_type,
            "validation_checks": [item.model_dump() for item in result.validation_checks],
            "artifact_manifest": [item.model_dump() for item in result.artifact_manifest],
            "paper_claims": [item.model_dump() for item in result.paper_claims],
            "target_revision": result.target_revision,
            "validation_gate": validation_gate(result_payload, task_record=current),
            "provenance_gate": artifact_provenance_gate(result_payload, task_record=current),
            "submitted_at": _.timestamp,
        }
        current["result"] = result_record
        current["status"] = result.status
        # A result closes the worker lease.  Keeping the last epoch on the
        # task lets a later FAILED/TIMEOUT retry obtain a strictly higher
        # fencing epoch without allowing the old worker to heartbeat or
        # handoff a reviewable task.
        current["last_fencing_epoch"] = result.fencing_epoch
        current["lease"] = None
        current["claimed_by"] = None
        submitted.update(copy.deepcopy(current))
        result_payload["task"] = copy.deepcopy(current)

    event = await store.append(
        actor_id=result.agent_id,
        event_type="TASK_RESULT",
        task_id=task_id,
        base_revision=result.target_revision,
        idempotency_key=result.idempotency_key,
        payload=result_payload,
        state_mutator=apply_result,
    )
    if not submitted:
        # Idempotent replays return the original event before the mutator runs;
        # prefer its self-contained task projection over the current state.
        original_task = event.payload.get("task") if isinstance(event.payload, dict) else None
        if isinstance(original_task, dict):
            submitted.update(copy.deepcopy(original_task))
        else:
            submitted.update(copy.deepcopy(store.tasks[task_id]))
    return {"accepted": True, "task": submitted, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/tasks/{task_id}/heartbeat")
async def heartbeat_task(task_id: str, request: HeartbeatIn) -> Dict[str, Any]:
    task = store.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    renewed: Dict[str, Any] = {}
    heartbeat_payload: Dict[str, Any] = {"agent_id": request.agent_id, "fencing_epoch": request.fencing_epoch, "ttl_seconds": request.ttl_seconds}

    def apply_heartbeat(_: Event) -> None:
        current = store.tasks[task_id]
        if current.get("status") != "IN_PROGRESS":
            raise HTTPException(status_code=409, detail={"code": "HEARTBEAT_STATE_INVALID", "status": current.get("status")})
        lease = current.get("lease") or {}
        holder = current.get("claimed_by") or lease.get("holder")
        if holder != request.agent_id or int(lease.get("fencing_epoch", -1)) != request.fencing_epoch:
            raise HTTPException(status_code=409, detail={"code": "STALE_FENCING_EPOCH", "holder": holder, "fencing_epoch": lease.get("fencing_epoch")})
        if lease_expired(lease):
            raise HTTPException(status_code=409, detail={"code": "LEASE_EXPIRED", "expires_at": lease.get("expires_at")})
        current["lease"] = renew_lease(lease, request.ttl_seconds)
        renewed.update(current)
        heartbeat_payload["task"] = dict(current)

    event = await store.append(
        actor_id=request.agent_id,
        event_type="TASK_HEARTBEAT",
        task_id=task_id,
        base_revision=request.base_revision,
        idempotency_key=request.idempotency_key,
        payload=heartbeat_payload,
        state_mutator=apply_heartbeat,
    )
    if not renewed:
        renewed.update(store.tasks[task_id])
    return {"accepted": True, "task": renewed, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/tasks/{task_id}/handoff")
async def handoff_task(task_id: str, request: HandoffIn) -> Dict[str, Any]:
    if task_id not in store.tasks:
        raise HTTPException(status_code=404, detail="task not found")
    handed: Dict[str, Any] = {}
    handoff_payload: Dict[str, Any] = {"from_agent_id": request.from_agent_id, "to_agent_id": request.to_agent_id, "reason": request.reason}

    def apply_handoff(_: Event) -> None:
        current = store.tasks[task_id]
        if current.get("status") != "IN_PROGRESS":
            raise HTTPException(status_code=409, detail={"code": "HANDOFF_STATE_INVALID", "status": current.get("status")})
        lease = current.get("lease") or {}
        holder = current.get("claimed_by") or (current.get("lease") or {}).get("holder")
        if holder != request.from_agent_id:
            raise HTTPException(status_code=409, detail={"code": "HANDOFF_NOT_OWNER", "holder": holder})
        if int(lease.get("fencing_epoch", -1)) != request.fencing_epoch:
            raise HTTPException(status_code=409, detail={"code": "STALE_FENCING_EPOCH", "holder": holder, "fencing_epoch": lease.get("fencing_epoch")})
        if lease_expired(lease):
            raise HTTPException(status_code=409, detail={"code": "LEASE_EXPIRED", "expires_at": lease.get("expires_at")})
        current.update({"owner": request.to_agent_id, "claimed_by": request.to_agent_id, "status": "IN_PROGRESS", "lease": new_lease(lease, 1800, request.to_agent_id)})
        handed.update(current)
        handoff_payload["task"] = dict(current)

    event = await store.append(
        actor_id=request.from_agent_id,
        event_type="TASK_HANDOFF",
        task_id=task_id,
        base_revision=request.target_revision,
        idempotency_key=request.idempotency_key,
        payload=handoff_payload,
        state_mutator=apply_handoff,
    )
    if not handed:
        handed.update(store.tasks[task_id])
    return {"accepted": True, "task": handed, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/tasks/{task_id}/review")
async def review_task(task_id: str, review: ReviewIn) -> Dict[str, Any]:
    if task_id not in store.tasks:
        raise HTTPException(status_code=404, detail="task not found")
    validate_target_revision(review.target_revision)
    review_payload = review.model_dump()

    def apply_review(_: Event) -> None:
        current = store.tasks[task_id]
        task_owner = current.get("owner")
        if review.reviewer_id in {"owner", "user"} or review.reviewer_id == task_owner:
            raise HTTPException(status_code=403, detail={"code": "REVIEWER_NOT_INDEPENDENT", "owner": task_owner})
        if review.independence_basis.strip().lower() in {"", "unspecified", "same session", "作者自审"}:
            raise HTTPException(status_code=422, detail={"code": "INDEPENDENCE_BASIS_REQUIRED"})
        invalid_ref = next((ref for ref in review.evidence_refs if not valid_evidence_ref(ref)), None)
        if invalid_ref is not None:
            raise HTTPException(status_code=422, detail={"code": "INVALID_EVIDENCE_REF", "reference": invalid_ref})
        if any(not str(log).strip() for log in review.check_logs):
            raise HTTPException(status_code=422, detail={"code": "EMPTY_CHECK_LOG"})
        current_status = current.get("status")
        if current_status != "READY_FOR_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "REVIEW_STATE_INVALID", "status": current_status, "required": ["READY_FOR_REVIEW"]})
        if review.verdict == "accept":
            result_record = current.get("result") or {}
            if result_record.get("status") != "READY_FOR_REVIEW":
                raise HTTPException(status_code=409, detail={"code": "RESULT_REQUIRED_FOR_ACCEPT"})
            result_refs = set(result_record.get("artifact_refs") or []) | set(result_record.get("evidence_refs") or [])
            if not result_refs.intersection(review.evidence_refs):
                raise HTTPException(status_code=409, detail={"code": "REVIEW_EVIDENCE_MISMATCH"})
        open_severities = [finding.get("severity", "") for finding in store.findings.get(task_id, []) if finding.get("status") == "open"]
        risk_approved = any(
            item.get("decision") == "accept_risk"
            and "risk" in str(item.get("scope", "")).lower()
            and item.get("target_revision") in {review.target_revision, "*"}
            and _approval_is_live(item)
            for item in store.approvals
        )
        if review.verdict == "accept" and acceptance_blocked(open_severities, accepted_risk=risk_approved):
            raise HTTPException(status_code=409, detail={"code": "CRITICAL_FINDINGS_OPEN", "severities": open_severities})
        if review.verdict == "accept":
            gate = validation_gate(current.get("result") or {}, task_record=current)
            # Results written through this API always carry a gate projection.
            # Older in-memory/journal records without that marker are allowed
            # to complete their migration path without changing legacy state.
            if "validation_gate" in (current.get("result") or {}) and not gate["ready"]:
                raise HTTPException(status_code=409, detail={"code": "VALIDATION_GATE_BLOCKED", "gate": gate})
            if "validation_gate" in (current.get("result") or {}) and not artifact_provenance_gate(current.get("result") or {}, task_record=current)["ready"]:
                raise HTTPException(status_code=409, detail={"code": "ARTIFACT_PROVENANCE_BLOCKED", "gate": artifact_provenance_gate(current.get("result") or {}, task_record=current)})
            current["status"] = "VERIFIED"
        elif review.verdict in {"revise", "reject"}:
            current["status"] = "BLOCKED"
        review_payload["task_status_after"] = current["status"]
        review_payload["task"] = copy.deepcopy(current)

    event = await store.append(
        actor_id=review.reviewer_id,
        event_type="REVIEW",
        task_id=task_id,
        base_revision=review.target_revision,
        idempotency_key=review.idempotency_key,
        payload=review_payload,
        state_mutator=apply_review,
    )
    return {"accepted": True, "task": copy.deepcopy(store.tasks[task_id]), "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/tasks/{task_id}/requeue")
async def requeue_task(task_id: str, request: RequeueIn) -> Dict[str, Any]:
    """Re-open a blocked/failed task for an explicit, auditable retry.

    Requeue is deliberately not an implicit claim.  It clears the previous
    lease and result projection, records the old state and evidence in the
    event, and returns a fresh ``QUEUED`` task.  The CAS target is the current
    control-plane revision, so a stale retry cannot silently resurrect a task
    after another review or owner decision.
    """
    if task_id not in store.tasks:
        raise HTTPException(status_code=404, detail="task not found")
    validate_target_revision(request.target_revision)
    invalid_refs = [ref for ref in request.evidence_refs if not valid_evidence_ref(ref)]
    if invalid_refs:
        raise HTTPException(status_code=422, detail={"code": "INVALID_EVIDENCE_REF", "refs": invalid_refs[:5]})
    requeued: Dict[str, Any] = {}
    payload: Dict[str, Any] = {
        "task_id": task_id,
        "actor_id": request.actor_id,
        "reason": request.reason,
        "evidence_refs": list(request.evidence_refs),
    }

    def apply_requeue(_: Event) -> None:
        current = store.tasks[task_id]
        status = str(current.get("status") or "")
        if status not in {"BLOCKED", "FAILED", "TIMEOUT"}:
            raise HTTPException(
                status_code=409,
                detail={"code": "TASK_REQUEUE_STATE_INVALID", "status": status, "required": ["BLOCKED", "FAILED", "TIMEOUT"]},
            )
        # Only the owner/coordinator (or the task's assigned worker/reviewer)
        # may reopen a task.  This is an identity boundary even in the local
        # unauthenticated development adapter; production must add OIDC/RBAC.
        owner = str(current.get("owner") or "").strip()
        reviewer = str(current.get("reviewer") or "").strip()
        local_owners = {"owner", "user", "coordinator", "codex/root"}
        if request.actor_id not in local_owners and request.actor_id not in {owner, reviewer}:
            raise HTTPException(
                status_code=403,
                detail={"code": "TASK_REQUEUE_FORBIDDEN", "actor_id": request.actor_id, "owner": owner},
            )
        previous_result = current.pop("result", None)
        current.update(
            {
                "status": "QUEUED",
                "claimed_by": None,
                "lease": None,
                "requeue_count": int(current.get("requeue_count", 0) or 0) + 1,
                "last_requeue": {
                    "actor_id": request.actor_id,
                    "reason": request.reason,
                    "evidence_refs": list(request.evidence_refs),
                    "from_status": status,
                    "at": _.timestamp,
                },
                "last_blocked_status": status,
            }
        )
        # Preserve the prior result for inspection without allowing it to be
        # mistaken for the new attempt's result.  The release gate only reads
        # the active ``result`` field.
        if previous_result is not None:
            current["previous_result"] = previous_result
        payload["from_status"] = status
        payload["task"] = copy.deepcopy(current)
        requeued.update(copy.deepcopy(current))

    event = await store.append(
        actor_id=request.actor_id,
        event_type="TASK_REQUEUED",
        task_id=task_id,
        base_revision=request.target_revision,
        idempotency_key=request.idempotency_key,
        payload=payload,
        state_mutator=apply_requeue,
    )
    if not requeued:
        original_task = event.payload.get("task") if isinstance(event.payload, dict) else None
        if isinstance(original_task, dict):
            requeued.update(copy.deepcopy(original_task))
        else:
            requeued.update(copy.deepcopy(store.tasks[task_id]))
    return {"accepted": True, "task": requeued, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.get("/api/tasks/{task_id}/findings")
async def task_findings(task_id: str) -> Dict[str, Any]:
    if task_id not in store.tasks:
        raise HTTPException(status_code=404, detail="task not found")
    return {"task_id": task_id, "findings": [dict(item) for item in store.findings.get(task_id, [])]}


@app.post("/api/tasks/{task_id}/findings/{finding_id}/close")
async def close_finding(task_id: str, finding_id: str, request: FindingCloseIn) -> Dict[str, Any]:
    if task_id not in store.tasks:
        raise HTTPException(status_code=404, detail="task not found")
    validate_revision(request.target_revision, "target_revision")
    current_task = store.tasks[task_id]
    actor_id = request.actor_id.strip()
    task_owner = str(current_task.get("owner") or "").strip()
    task_reviewer = str(current_task.get("reviewer") or "").strip()
    # Closing a finding changes the release gate.  Only the human Owner or
    # coordinator, or an explicitly assigned task owner/reviewer, may perform
    # that transition.  The generic ``user`` alias is intentionally rejected:
    # the UI's Owner identity is ``owner`` and must not be confused with an
    # arbitrary unauthenticated caller.
    authorized = actor_id in {"owner", "coordinator", "codex/root"} or (
        actor_id not in {"", "user"} and actor_id in {task_owner, task_reviewer}
    )
    if not authorized:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FINDING_CLOSE_FORBIDDEN",
                "actor_id": actor_id,
                "owner": task_owner,
                "reviewer": task_reviewer or None,
            },
        )
    if not valid_evidence_ref(request.evidence_ref):
        raise HTTPException(status_code=422, detail={"code": "INVALID_EVIDENCE_REF", "reference": request.evidence_ref})
    if request.evidence_ref not in _known_finding_evidence_refs(task_id):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "FINDING_EVIDENCE_UNKNOWN",
                "evidence_ref": request.evidence_ref,
                "message": "evidence_ref must already be registered in this task result or event payload",
            },
        )
    closed: Dict[str, Any] = {}

    def apply_close(_: Event) -> None:
        finding = next((item for item in store.findings.get(task_id, []) if item.get("finding_id") == finding_id), None)
        if finding is None:
            raise HTTPException(status_code=404, detail="finding not found")
        # Re-check the evidence while holding the event-store lock.  This keeps
        # a concurrent result/requeue update from turning a preflight check into
        # a stale closure.
        if request.evidence_ref not in _known_finding_evidence_refs(task_id):
            raise HTTPException(
                status_code=409,
                detail={"code": "FINDING_EVIDENCE_STALE", "evidence_ref": request.evidence_ref},
            )
        if finding.get("status") == "closed":
            closed.update(finding)
            return
        finding.update({"status": "closed", "closed_by": request.actor_id, "evidence_ref": request.evidence_ref})
        closed.update(finding)

    event = await store.append(
        actor_id=request.actor_id,
        event_type="FINDING_CLOSED",
        task_id=task_id,
        base_revision=request.target_revision,
        idempotency_key=request.idempotency_key,
        payload={"finding_id": finding_id, "evidence_ref": request.evidence_ref},
        state_mutator=apply_close,
    )
    if not closed:
        closed.update(next((item for item in store.findings.get(task_id, []) if item.get("finding_id") == finding_id), {}))
    return {"accepted": True, "finding": closed, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/projects/{project_id}/approvals")
async def create_approval(project_id: str, approval: ApprovalIn) -> Dict[str, Any]:
    """Record an Owner decision; it does not execute the approved action."""
    if project_id != PROJECT_ID:
        raise HTTPException(status_code=404, detail="project not found")
    if approval.owner_id not in {"owner", "user"}:
        raise HTTPException(status_code=403, detail={"code": "OWNER_APPROVAL_REQUIRED"})
    validate_target_revision(approval.target_revision, allow_wildcard=approval.decision == "accept_risk")
    recorded: Dict[str, Any] = {}
    approval_payload: Dict[str, Any] = {"scope": approval.scope, "decision": approval.decision, "note": approval.note}

    def apply_approval(event: Event) -> None:
        recorded.update({
            "approval_id": f"approval-{event.event_id}",
            "owner_id": approval.owner_id,
            "scope": approval.scope,
            "decision": approval.decision,
            "target_revision": approval.target_revision,
            "note": approval.note,
            "created_at": event.timestamp,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec="seconds"),
            "status": "RECORDED",
        })
        store.approvals.append(dict(recorded))
        approval_payload["approval"] = dict(recorded)

    event = await store.append(
        actor_id=approval.owner_id,
        event_type="APPROVAL",
        base_revision=approval.base_revision,
        idempotency_key=approval.idempotency_key,
        payload=approval_payload,
        state_mutator=apply_approval,
    )
    if not recorded:
        recorded.update(next((item for item in reversed(store.approvals) if item["approval_id"] == f"approval-{event.event_id}"), {}))
    return {"accepted": True, "approval": recorded, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/relays")
async def create_relay(relay: RelayIn) -> Dict[str, Any]:
    """Create a bounded external relay packet, without sending it."""
    validate_revision(relay.input_revision, "input_revision")
    if relay.task_id not in store.tasks:
        raise HTTPException(status_code=404, detail="task not found")
    task_input_revision = store.tasks[relay.task_id].get("input_revision")
    if task_input_revision and task_input_revision != relay.input_revision:
        raise HTTPException(status_code=409, detail={"code": "RELAY_TASK_REVISION_MISMATCH", "task_revision": task_input_revision, "input_revision": relay.input_revision})
    # The caller must opt into an external target explicitly.  This avoids an
    # accidental approval requirement (or egress) merely because a provider
    # uses a non-local agent id; unknown local ids are still represented as a
    # local adapter when ``target_kind=local`` is selected.
    if relay.target_kind == "external":
        approval = next((item for item in reversed(store.approvals) if item.get("approval_id") == relay.approval_ref), None)
        if approval is None:
            raise HTTPException(status_code=428, detail={"code": "EXTERNAL_APPROVAL_REQUIRED", "message": "external relay requires a recorded Owner approval_ref"})
        if approval.get("decision") != "approve" or not str(approval.get("scope", "")).lower().startswith(("external", "relay", "antigravity")):
            raise HTTPException(status_code=403, detail={"code": "RELAY_SCOPE_DENIED", "message": "approval scope/decision does not authorize external relay"})
        if approval.get("target_revision") not in {relay.input_revision, "*"}:
            raise HTTPException(status_code=409, detail={"code": "RELAY_REVISION_MISMATCH", "approval_revision": approval.get("target_revision"), "input_revision": relay.input_revision})
        if not _approval_is_live(approval):
            raise HTTPException(status_code=403, detail={"code": "APPROVAL_INVALID_EXPIRY"})
    issued_at = utc_now()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec="seconds")
    packet = {
        "protocol": "agent-collab/v1",
        "relay_id": f"relay-{secrets.token_hex(8)}",
        "from_agent_id": relay.from_agent_id,
        "to_agent_id": relay.to_agent_id,
        "task_id": relay.task_id,
        "input_revision": relay.input_revision,
        "payload": relay.payload,
        "approval_ref": relay.approval_ref,
        "target_kind": relay.target_kind,
        "nonce": secrets.token_urlsafe(18),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    packet_hash = hashlib.sha256(json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    secret = os.getenv("COLLAB_RELAY_SECRET")
    signature = hmac.new(secret.encode("utf-8"), packet_hash.encode("ascii"), hashlib.sha256).hexdigest() if secret else None
    packet["input_hash"] = f"sha256:{packet_hash}"
    packet["signature"] = signature
    packet["signature_status"] = "SIGNED_DEV_SECRET" if secret else "UNSIGNED_DEV"
    packet["status"] = "PENDING_RELAY"
    recorded: Dict[str, Any] = {}

    def apply_relay(event: Event) -> None:
        packet["event_ref"] = event.event_id
        recorded.update(packet)
        store.relays.append(dict(packet))

    event = await store.append(
        actor_id=relay.from_agent_id,
        event_type="RELAY",
        task_id=relay.task_id,
        base_revision=relay.base_revision,
        idempotency_key=relay.idempotency_key,
        payload={"relay_id": packet["relay_id"], "to_agent_id": relay.to_agent_id, "input_hash": packet["input_hash"], "status": packet["status"]},
        state_mutator=apply_relay,
    )
    if not recorded:
        recorded.update(next((item for item in reversed(store.relays) if item.get("event_ref") == event.event_id), packet))
    return {"accepted": True, "relay": recorded, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.post("/api/relays/{relay_id}/ack")
async def acknowledge_relay(relay_id: str, ack: RelayAckIn) -> Dict[str, Any]:
    """Record a recipient connectivity/hash acknowledgement.

    An ACK only proves that the recipient saw the exact nonce and frozen input
    hash.  It does not grant write access, approve a route, or imply that the
    external model completed its task.
    """
    if ack.relay_id != relay_id:
        raise HTTPException(status_code=409, detail={"code": "RELAY_ID_MISMATCH"})
    validate_target_revision(ack.target_revision)
    acknowledged: Dict[str, Any] = {}

    def apply_ack(_: Event) -> None:
        relay = next((item for item in store.relays if item.get("relay_id") == relay_id), None)
        if relay is None:
            raise HTTPException(status_code=404, detail="relay not found")
        if relay.get("to_agent_id") != ack.to_agent_id:
            raise HTTPException(status_code=403, detail={"code": "RELAY_ACK_RECIPIENT_MISMATCH"})
        if relay.get("status") != "PENDING_RELAY":
            raise HTTPException(status_code=409, detail={"code": "RELAY_ACK_STATE_INVALID", "status": relay.get("status")})
        if not hmac.compare_digest(str(relay.get("nonce", "")), ack.nonce) or not hmac.compare_digest(str(relay.get("input_hash", "")), ack.input_hash):
            raise HTTPException(status_code=409, detail={"code": "RELAY_ACK_HASH_MISMATCH"})
        try:
            if datetime.fromisoformat(str(relay.get("expires_at"))) <= datetime.now(timezone.utc):
                raise HTTPException(status_code=409, detail={"code": "RELAY_EXPIRED"})
        except (TypeError, ValueError):
            raise HTTPException(status_code=409, detail={"code": "RELAY_INVALID_EXPIRY"})
        relay["status"] = "CONNECTIVITY_VERIFIED" if ack.status == "RECEIVED" else "REJECTED"
        relay["ack"] = {
            "to_agent_id": ack.to_agent_id,
            "status": ack.status,
            "note": ack.note,
            "acknowledged_at": _.timestamp,
        }
        acknowledged.update(copy.deepcopy(relay))

    event = await store.append(
        actor_id=ack.to_agent_id,
        event_type="RELAY_ACK",
        task_id=None,
        base_revision=ack.target_revision,
        idempotency_key=ack.idempotency_key,
        payload={"relay_id": relay_id, "to_agent_id": ack.to_agent_id, "input_hash": ack.input_hash, "status": ack.status, "note": ack.note},
        state_mutator=apply_ack,
    )
    if not acknowledged:
        acknowledged.update(next((item for item in reversed(store.relays) if item.get("relay_id") == relay_id), {}))
    return {"accepted": True, "relay": acknowledged, "event": event.model_dump(), "revision": event.revision or store.revision}


@app.get("/api/model-profiles")
async def model_profiles() -> Dict[str, Any]:
    profiles = []
    for profile in default_profiles():
        profiles.append({
            "provider": profile.provider,
            "model": profile.model,
            "capabilities": sorted(profile.capabilities),
            "roles": sorted(profile.roles),
            "data_policy": profile.data_policy,
            "latency_class": profile.latency_class,
            "fallback_rank": profile.fallback_rank,
            "version": profile.version,
            "reasoning_effort": profile.reasoning_effort,
            "tool_permissions": sorted(profile.tool_permissions),
            "calibration_score": profile.calibration_score,
            "estimated_cost_per_1k": profile.estimated_cost_per_1k,
            "latency_ms": profile.latency_ms,
        })
    return {"registry_version": "0.1", "profiles": profiles}


@app.post("/api/model-route")
async def model_route(request: ModelRouteIn) -> Dict[str, Any]:
    """Preview capability-first routing without invoking a provider.

    This endpoint is intentionally read-only: the Coordinator can ask which
    profiles satisfy a task envelope before dispatching, while actual model
    execution remains behind an authenticated adapter.  Returning the full
    candidate list makes fallback and policy decisions inspectable in the UI.
    """

    gateway = ModelGateway(default_profiles())
    model_request = ModelRequest(
        role=request.role,
        required_capabilities=frozenset(request.required_capabilities),
        data_classification=request.data_classification,
        external_network=request.external_network,
        budget_remaining=request.budget_remaining,
        preferred_provider=request.preferred_provider,
        required_tools=frozenset(request.required_tools),
        max_latency_ms=request.max_latency_ms,
        min_calibration_score=request.min_calibration_score,
        risk_level=request.risk_level,
        owner_approved=request.owner_approved,
        approval_ref=request.approval_ref,
    )
    candidates = gateway.candidates(model_request)

    def describe(profile: Any) -> Dict[str, Any]:
        return {
            "provider": profile.provider,
            "model": profile.model,
            "roles": sorted(profile.roles),
            "capabilities": sorted(profile.capabilities),
            "data_policy": profile.data_policy,
            "version": profile.version,
            "reasoning_effort": profile.reasoning_effort,
            "tool_permissions": sorted(profile.tool_permissions),
            "calibration_score": profile.calibration_score,
            "estimated_cost_per_1k": profile.estimated_cost_per_1k,
            "latency_ms": profile.latency_ms,
            "fallback_rank": profile.fallback_rank,
        }

    return {
        "status": "ROUTE_FOUND" if candidates else "MODEL_UNAVAILABLE",
        "requested": request.model_dump(exclude={"approval_ref"}),
        "selected": describe(candidates[0]) if candidates else None,
        "candidates": [describe(profile) for profile in candidates],
        "execution": "preview_only",
    }


@app.post("/api/runs/{run_id}/rerun")
async def request_rerun(run_id: str, request: RerunIn) -> Dict[str, Any]:
    if run_id != RUN_ID:
        raise HTTPException(status_code=404, detail="run not found")
    if request.requested_by not in {"owner", "coordinator", "codex/root"}:
        raise HTTPException(status_code=403, detail={"code": "RERUN_FORBIDDEN"})
    validate_target_revision(request.target_revision)
    event = await store.append(
        actor_id=request.requested_by,
        event_type="RERUN_REQUESTED",
        base_revision=request.target_revision,
        idempotency_key=request.idempotency_key,
        payload={"target_revision": request.target_revision, "reason": request.reason},
    )
    return {"accepted": True, "status": "QUEUED", "event": event.model_dump(), "revision": event.revision or store.revision}


@app.websocket("/ws/projects/{project_id}")
async def project_socket(websocket: WebSocket, project_id: str) -> None:
    if project_id != PROJECT_ID:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    store.connections.add(websocket)
    try:
        await websocket.send_json({"type": "snapshot", "revision": store.revision, "after_seq": store.events[-1].seq if store.events else 0})
        while True:
            # The client may send a ping or a cursor acknowledgement.
            await websocket.receive_text()
    except WebSocketDisconnect:
        store.connections.discard(websocket)
    except Exception:
        store.connections.discard(websocket)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(ROOT / "index.html")


@app.get("/{asset_path:path}", include_in_schema=False)
async def assets(asset_path: str) -> FileResponse:
    candidate = _safe_static_file(asset_path)
    if candidate is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(candidate)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8787")), reload=False)
