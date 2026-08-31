"""Deterministic orchestration rules used by the local API and test harness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple


class DispatchTier(str, Enum):
    SOLO = "SOLO"
    LITE = "LITE"
    FULL = "FULL"


class TaskState(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    VERIFIED = "VERIFIED"
    INTEGRATED = "INTEGRATED"
    ACCEPTED = "ACCEPTED"
    RELEASED = "RELEASED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


ALLOWED_TRANSITIONS = {
    TaskState.QUEUED: {TaskState.CLAIMED, TaskState.BLOCKED, TaskState.CANCELLED},
    TaskState.CLAIMED: {TaskState.IN_PROGRESS, TaskState.TIMEOUT, TaskState.CANCELLED},
    TaskState.IN_PROGRESS: {TaskState.READY_FOR_REVIEW, TaskState.FAILED, TaskState.TIMEOUT, TaskState.BLOCKED, TaskState.CANCELLED},
    TaskState.READY_FOR_REVIEW: {TaskState.VERIFIED, TaskState.BLOCKED, TaskState.SUPERSEDED},
    TaskState.VERIFIED: {TaskState.INTEGRATED, TaskState.SUPERSEDED},
    TaskState.INTEGRATED: {TaskState.ACCEPTED, TaskState.BLOCKED, TaskState.SUPERSEDED},
    TaskState.ACCEPTED: {TaskState.RELEASED, TaskState.SUPERSEDED},
    TaskState.RELEASED: set(),
    TaskState.FAILED: {TaskState.QUEUED, TaskState.SUPERSEDED},
    TaskState.TIMEOUT: {TaskState.QUEUED, TaskState.SUPERSEDED},
    TaskState.BLOCKED: {TaskState.QUEUED, TaskState.CANCELLED, TaskState.SUPERSEDED},
    TaskState.CANCELLED: set(),
    TaskState.SUPERSEDED: set(),
}


def can_transition(current: TaskState, target: TaskState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def canonical_path(path: str) -> str:
    """Normalize a relative POSIX-style write path and fail on traversal."""
    raw = path.replace("\\", "/")
    if raw.startswith("/") or ":" in raw.split("/")[0]:
        raise ValueError("absolute path is not allowed")
    parts = [part for part in PurePosixPath(raw).parts if part not in {"."}]
    if any(part == ".." for part in parts):
        raise ValueError("path traversal is not allowed")
    return "/".join(parts)


def paths_overlap(left: str, right: str) -> bool:
    a, b = canonical_path(left).rstrip("/"), canonical_path(right).rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def write_sets_conflict(left: Sequence[str], right: Sequence[str]) -> bool:
    return any(paths_overlap(a, b) for a in left for b in right)


def validate_dependency_graph(tasks: Mapping[str, Sequence[str]]) -> None:
    """Reject self references and cycles in a task dependency graph.

    Dispatch is a public API boundary, so a malformed envelope must not be
    allowed to create a graph that can never become runnable.  The function is
    intentionally deterministic and side-effect free; callers can build a
    proposed graph while holding their own transaction lock and then persist
    the task only after this check succeeds.
    """

    visiting: Set[str] = set()
    visited: Set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"dependency cycle detected at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in tasks.get(node, ()):
            if dependency == node:
                raise ValueError(f"self dependency detected at {node}")
            if dependency not in tasks:
                raise ValueError(f"unknown dependency: {dependency}")
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in tasks:
        visit(node)


@dataclass(frozen=True)
class DispatchLimits:
    max_agents: int
    max_parallel: int
    max_depth: int = 1
    budget_tokens: int = 20000


def validate_limits(tier: DispatchTier, limits: DispatchLimits) -> None:
    if min(limits.max_agents, limits.max_parallel, limits.max_depth, limits.budget_tokens) < 1:
        raise ValueError("dispatch limits must be positive")
    if limits.max_parallel > limits.max_agents:
        raise ValueError("max_parallel cannot exceed max_agents")
    if tier == DispatchTier.SOLO and limits.max_agents != 1:
        raise ValueError("SOLO must have exactly one agent")
    if tier == DispatchTier.LITE and limits.max_agents > 3:
        raise ValueError("LITE is capped at three agents")


def acceptance_blocked(open_severities: Iterable[str], accepted_risk: bool = False) -> bool:
    # Findings often come from human/agent text and may contain surrounding
    # whitespace; normalize before applying the release gate so ``" P1 "``
    # cannot accidentally bypass it.
    critical = {str(severity).strip().upper() for severity in open_severities} & {"P0", "P1", "CRITICAL"}
    return bool(critical) and not accepted_risk
