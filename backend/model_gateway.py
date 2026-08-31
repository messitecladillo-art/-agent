"""Capability-first model routing primitives.

The gateway deliberately contains no provider secrets and no shell execution.
Adapters can be added behind `ModelAdapter`; every run records the selected
profile and an input manifest so a competition run is reproducible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set


DATA_CLASSIFICATIONS = frozenset({"public", "internal", "confidential", "restricted"})
RISK_LEVELS = frozenset({"R0", "R1", "R2", "R3", "R4", "R5"})
TERMINAL_FAILURE_STATUSES = frozenset({"MODEL_UNAVAILABLE", "TIMEOUT", "FAILED", "BLOCKED"})
SUCCESS_STATUSES = frozenset({"SUCCEEDED", "READY_FOR_REVIEW", "VERIFIED"})

# A profile's policy is an allow-list for the *classification* of the input,
# not a marketing label.  The gateway rejects an unknown policy instead of
# silently treating it as ``internal-only``.  ``local-only`` is the only
# default profile allowed to see restricted material; external profiles are
# limited to public/internal inputs and still require an explicit egress flag.
DATA_POLICY_ALLOWLIST = {
    "public-only": frozenset({"public"}),
    "internal-only": frozenset({"public", "internal", "confidential"}),
    "local-only": DATA_CLASSIFICATIONS,
    "confidential-approved": frozenset({"public", "internal", "confidential"}),
    "external-approved": frozenset({"public", "internal"}),
    "external-only": frozenset({"public"}),
}


# The public YAML/docs use descriptive capability names while adapters often
# expose smaller primitives.  Canonicalising at the gateway keeps routing
# stable when a provider changes its marketing/API vocabulary.
CAPABILITY_ALIASES = {
    "long_context_reasoning": {"long_context", "reasoning"},
    "document_reasoning": {"long_context", "reasoning"},
    "code_execution": {"code"},
    "table_formula_extraction": {"table_formula"},
    "pdf_extraction": {"pdf"},
    "independent_modeling": {"independent_review", "reasoning"},
    "tool_orchestration": {"planning"},
    "conflict_adjudication": {"planning", "reasoning"},
    "citation_tracking": {"reasoning"},
    "multimodal_optional": set(),
    "counterexample": {"independent_review", "reasoning"},
    "chinese_technical_writing": {"writing"},
    "structure_following": {"writing"},
    "citation_safe": {"writing"},
    "structured_json": {"structured_output"},
}

ROLE_ALIASES = {
    "scope_lock": "scope",
    "rule_integrity": "scope",
    "problem_analyst": "scope",
    "vision_ocr": "vision",
    "algorithm_engineer": "algorithm",
    "validation_auditor": "validation",
    "release_auditor": "validation",
    "paper_judge": "writer",
    "defense_coach": "writer",
    "model_a": "model_strategist",
    "model_b": "independent_solver",
    "challenger": "critic",
    "resource_manager": "router",
    "context_curator": "router",
}


def canonical_capabilities(capabilities: Iterable[str]) -> frozenset[str]:
    expanded: Set[str] = set()
    for capability in capabilities:
        expanded.update(CAPABILITY_ALIASES.get(capability, {capability}))
    return frozenset(expanded)


def canonical_role(role: str) -> str:
    return ROLE_ALIASES.get(str(role).strip().lower(), str(role).strip().lower())


def normalize_data_classification(value: str) -> str:
    normalized = str(value).strip().lower().replace("-", "_")
    aliases = {"private": "confidential", "secret": "restricted", "public_data": "public"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in DATA_CLASSIFICATIONS:
        raise ValueError(f"unknown data classification: {value}")
    return normalized


def normalize_risk_level(value: str) -> str:
    normalized = str(value).strip().upper()
    if normalized not in RISK_LEVELS:
        raise ValueError(f"unknown risk level: {value}")
    return normalized


def normalize_data_policy(value: str) -> Optional[str]:
    """Return a canonical policy name, or ``None`` for an unknown profile.

    Profiles are configuration supplied by an administrator/adapter.  An
    invalid value must make that profile unavailable, never broaden access.
    """

    normalized = str(value).strip().lower().replace("_", "-")
    aliases = {
        "public": "public-only",
        "internal": "internal-only",
        "local": "local-only",
        "confidential": "confidential-approved",
        "external": "external-approved",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in DATA_POLICY_ALLOWLIST else None


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    capabilities: frozenset[str]
    roles: frozenset[str]
    data_policy: str = "internal-only"
    latency_class: str = "medium"
    fallback_rank: int = 100
    version: str = "unresolved"
    reasoning_effort: str = "medium"
    tool_permissions: frozenset[str] = frozenset()
    calibration_score: float = 0.0
    estimated_cost_per_1k: Optional[float] = None
    latency_ms: Optional[int] = None


@dataclass(frozen=True)
class ModelRequest:
    role: str
    required_capabilities: frozenset[str]
    data_classification: str = "internal"
    external_network: bool = False
    budget_remaining: Optional[float] = None
    preferred_provider: Optional[str] = None
    required_tools: frozenset[str] = frozenset()
    max_latency_ms: Optional[int] = None
    min_calibration_score: float = 0.0
    risk_level: str = "R2"
    owner_approved: bool = False
    approval_ref: Optional[str] = None


@dataclass
class ModelRun:
    status: str
    provider: Optional[str] = None
    model: Optional[str] = None
    role: Optional[str] = None
    input_manifest: Optional[str] = None
    output_hash: Optional[str] = None
    fallback_used: bool = False
    reason: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


class ModelAdapter:
    """Provider adapter interface; concrete adapters live outside the UI/API."""

    def run(self, profile: ModelProfile, request: ModelRequest, prompt: str, input_manifest: str) -> ModelRun:
        raise NotImplementedError


class UnconfiguredAdapter(ModelAdapter):
    def run(self, profile: ModelProfile, request: ModelRequest, prompt: str, input_manifest: str) -> ModelRun:
        return ModelRun(status="MODEL_UNAVAILABLE", provider=profile.provider, model=profile.model, role=request.role, input_manifest=input_manifest, reason="No provider credential/adapter configured")


class ModelGateway:
    def __init__(self, profiles: Sequence[ModelProfile], adapters: Optional[Dict[str, ModelAdapter]] = None) -> None:
        self.profiles = list(profiles)
        self.adapters = adapters or {}

    def candidates(self, request: ModelRequest) -> List[ModelProfile]:
        role = canonical_role(request.role)
        required_capabilities = canonical_capabilities(request.required_capabilities)
        try:
            data_classification = normalize_data_classification(request.data_classification)
            risk_level = normalize_risk_level(request.risk_level)
        except ValueError:
            # Unknown classifications fail closed instead of silently treating
            # sensitive input as ordinary internal data.
            return []
        required_tools = frozenset(str(item).strip().lower() for item in request.required_tools)
        if "" in required_tools or (request.budget_remaining is not None and (not math.isfinite(request.budget_remaining) or request.budget_remaining < 0)) or (request.max_latency_ms is not None and request.max_latency_ms < 0):
            return []
        if not math.isfinite(request.min_calibration_score) or request.min_calibration_score < 0 or request.min_calibration_score > 1:
            return []
        if risk_level == "R5" and (not request.owner_approved or not str(request.approval_ref or "").strip()):
            # High-impact actions (external send/publish/delete/accept-risk)
            # cannot be routed merely because a model has the capability.
            return []
        candidates = [profile for profile in self.profiles if role in profile.roles and required_capabilities.issubset(profile.capabilities)]
        policy_safe: List[ModelProfile] = []
        for profile in candidates:
            policy = normalize_data_policy(profile.data_policy)
            if policy is None:
                # Unknown profile policy is fail-closed.  A typo such as
                # ``external-approvedd`` must not accidentally gain egress.
                continue
            allowed_classes = DATA_POLICY_ALLOWLIST[policy]
            if data_classification not in allowed_classes:
                continue
            if policy in {"external-only", "external-approved"} and not request.external_network:
                # Egress is an explicit request-level opt-in as well as a
                # profile policy; both gates must be present.
                continue
            policy_safe.append(profile)
        candidates = policy_safe
        if required_tools:
            candidates = [profile for profile in candidates if required_tools.issubset(profile.tool_permissions)]
        candidates = [profile for profile in candidates if math.isfinite(profile.calibration_score) and 0 <= profile.calibration_score <= 1 and profile.calibration_score >= request.min_calibration_score]
        candidates = [profile for profile in candidates if profile.latency_ms is None or (isinstance(profile.latency_ms, int) and profile.latency_ms >= 0)]
        candidates = [profile for profile in candidates if profile.estimated_cost_per_1k is None or (math.isfinite(profile.estimated_cost_per_1k) and profile.estimated_cost_per_1k >= 0)]
        if request.max_latency_ms is not None:
            candidates = [profile for profile in candidates if profile.latency_ms is None or profile.latency_ms <= request.max_latency_ms]
        if request.budget_remaining is not None:
            # Unknown prices are retained but marked in run metadata; a known
            # estimate may not exceed the caller's remaining budget.
            candidates = [profile for profile in candidates if profile.estimated_cost_per_1k is None or profile.estimated_cost_per_1k <= request.budget_remaining]
        # Preserve the caller's provider preference before applying the
        # capability fallback rank.  A previous implementation prepended the
        # preferred list and then globally sorted by rank, silently undoing the
        # preference whenever another provider had a lower rank.
        preferred_provider = request.preferred_provider
        return sorted(candidates, key=lambda profile: (profile.provider != preferred_provider, -profile.calibration_score, profile.fallback_rank, profile.latency_ms or 10**9))

    def run(self, request: ModelRequest, prompt: str, input_manifest: str) -> ModelRun:
        candidates = self.candidates(request)
        if not candidates:
            return ModelRun(status="MODEL_UNAVAILABLE", role=request.role, input_manifest=input_manifest, reason="No profile satisfies requested capability/data policy")
        for index, profile in enumerate(candidates):
            adapter = self.adapters.get(profile.provider, UnconfiguredAdapter())
            try:
                result = adapter.run(profile, request, prompt, input_manifest)
            except TimeoutError as error:
                result = ModelRun(status="TIMEOUT", reason=str(error) or "adapter timeout")
            except Exception as error:  # adapters must not turn a provider fault into an API 500
                result = ModelRun(status="FAILED", reason=f"adapter exception: {type(error).__name__}: {error}")
            if not isinstance(result, ModelRun):
                result = ModelRun(status="FAILED", reason="adapter returned an invalid result object")
            if result.status not in SUCCESS_STATUSES | TERMINAL_FAILURE_STATUSES:
                result = ModelRun(status="FAILED", reason=f"adapter returned unknown status: {result.status}")
            result.provider = result.provider or profile.provider
            result.model = result.model or profile.model
            result.role = result.role or request.role
            result.input_manifest = result.input_manifest or input_manifest
            result.metadata.setdefault("profile_version", profile.version)
            result.metadata.setdefault("reasoning_effort", profile.reasoning_effort)
            result.metadata.setdefault("tool_permissions", sorted(profile.tool_permissions))
            result.metadata.setdefault("calibration_score", profile.calibration_score)
            result.metadata.setdefault("estimated_cost_per_1k", profile.estimated_cost_per_1k)
            result.metadata.setdefault("latency_ms", profile.latency_ms)
            if result.status not in TERMINAL_FAILURE_STATUSES:
                result.fallback_used = index > 0
                return result
        # Preserve the selected profile even if all adapters failed.
        last = candidates[-1]
        return ModelRun(status="MODEL_UNAVAILABLE", provider=last.provider, model=last.model, role=request.role, input_manifest=input_manifest, fallback_used=len(candidates) > 1, reason="All candidate adapters failed")


def default_profiles() -> List[ModelProfile]:
    return [
        ModelProfile("openai/codex", "gpt-5.6-sol", frozenset({"long_context", "reasoning", "planning", "code", "local_files"}), frozenset({"coordinator", "model_strategist", "integrator"}), fallback_rank=10, reasoning_effort="high", tool_permissions=frozenset({"read_local", "write_control", "python_sandbox"}), calibration_score=0.90, latency_ms=1800),
        ModelProfile("openai/codex", "gpt-5.6-terra", frozenset({"long_context", "reasoning", "code", "local_files", "writing"}), frozenset({"model_strategist", "writer", "solver", "scope"}), fallback_rank=20, reasoning_effort="high", tool_permissions=frozenset({"read_local", "python_sandbox", "write_artifact"}), calibration_score=0.86, latency_ms=1200),
        ModelProfile("openai/codex", "gpt-5.5", frozenset({"code", "statistics", "reproducibility", "read_only", "local_files"}), frozenset({"validation"}), fallback_rank=25, reasoning_effort="high", tool_permissions=frozenset({"read_local", "python_sandbox"}), calibration_score=0.88, latency_ms=1400),
        ModelProfile("qoder", "tool-code-profile", frozenset({"code", "local_files", "testing", "python", "reproducibility"}), frozenset({"data_auditor", "solver", "algorithm", "validation"}), data_policy="local-only", fallback_rank=30, reasoning_effort="medium", tool_permissions=frozenset({"read_local", "write_artifact", "python_sandbox", "terminal"}), calibration_score=0.84, latency_ms=900),
        ModelProfile("claude", "opus", frozenset({"long_context", "reasoning", "independent_review", "writing"}), frozenset({"independent_solver", "critic", "writer", "scope"}), fallback_rank=40, reasoning_effort="high", tool_permissions=frozenset({"read_local", "write_artifact"}), calibration_score=0.87, latency_ms=1700),
        ModelProfile("antigravity", "gemini-multimodal", frozenset({"vision", "pdf", "table_formula", "reasoning"}), frozenset({"vision", "scope", "critic"}), data_policy="external-approved", fallback_rank=50, reasoning_effort="high", tool_permissions=frozenset({"read_frozen_relay", "vision"}), calibration_score=0.82, latency_ms=2200),
        ModelProfile("openai/codex", "gpt-5.4-mini", frozenset({"triage", "short_context", "summary", "structured_output"}), frozenset({"router", "context_curator"}), fallback_rank=80, reasoning_effort="low", tool_permissions=frozenset({"read_control", "write_control"}), calibration_score=0.76, latency_ms=350),
    ]
