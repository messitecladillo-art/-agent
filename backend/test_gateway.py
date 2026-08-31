from typing import Optional

import pytest

from model_gateway import (
    ModelAdapter,
    ModelGateway,
    ModelProfile,
    ModelRequest,
    ModelRun,
    canonical_capabilities,
    default_profiles,
)


def _profile(
    provider: str,
    *,
    fallback_rank: int = 10,
    calibration_score: float = 0.8,
    estimated_cost_per_1k: Optional[float] = 0.01,
    tool_permissions: frozenset[str] = frozenset(),
) -> ModelProfile:
    """Create a small deterministic profile for gateway policy tests."""

    return ModelProfile(
        provider=provider,
        model=f"{provider}-model",
        capabilities=frozenset({"reasoning"}),
        roles=frozenset({"solver"}),
        fallback_rank=fallback_rank,
        calibration_score=calibration_score,
        estimated_cost_per_1k=estimated_cost_per_1k,
        tool_permissions=tool_permissions,
    )


class _RaiseAdapter(ModelAdapter):
    def run(self, profile, request, prompt, input_manifest):
        raise RuntimeError("provider exploded")


class _UnknownStatusAdapter(ModelAdapter):
    def run(self, profile, request, prompt, input_manifest):
        return ModelRun(status="MAYBE")


class _SuccessAdapter(ModelAdapter):
    def run(self, profile, request, prompt, input_manifest):
        return ModelRun(status="SUCCEEDED")


def test_gateway_selects_capability_profile_without_calling_unknown_provider():
    gateway = ModelGateway(default_profiles())
    request = ModelRequest(role="data_auditor", required_capabilities=frozenset({"code", "python"}), data_classification="internal")
    result = gateway.run(request, "audit", "manifest:test")
    assert result.status == "MODEL_UNAVAILABLE"
    assert result.role == "data_auditor"
    assert result.input_manifest == "manifest:test"


def test_gateway_rejects_external_profile_for_restricted_data():
    gateway = ModelGateway(default_profiles())
    request = ModelRequest(role="vision", required_capabilities=frozenset({"vision"}), data_classification="restricted")
    assert gateway.candidates(request) == []


def test_gateway_requires_explicit_egress_for_external_approved_profile():
    gateway = ModelGateway(default_profiles())
    internal = ModelRequest(role="vision", required_capabilities=frozenset({"vision"}), data_classification="internal")
    assert gateway.candidates(internal) == []
    approved = ModelRequest(role="vision", required_capabilities=frozenset({"vision"}), data_classification="internal", external_network=True)
    candidates = gateway.candidates(approved)
    assert candidates
    assert candidates[0].provider == "antigravity"


def test_gateway_honors_preferred_provider_before_fallback_rank():
    gateway = ModelGateway(default_profiles())
    request = ModelRequest(
        role="writer",
        required_capabilities=frozenset({"writing"}),
        preferred_provider="claude",
    )
    candidates = gateway.candidates(request)
    assert candidates
    assert candidates[0].provider == "claude"


def test_gateway_accepts_documented_capability_aliases():
    assert canonical_capabilities({"long_context_reasoning", "code_execution"}) == {"long_context", "reasoning", "code"}
    gateway = ModelGateway(default_profiles())
    request = ModelRequest(role="validation_auditor", required_capabilities=frozenset({"code_execution"}), data_classification="internal")
    candidates = gateway.candidates(request)
    assert candidates
    assert any(profile.provider == "openai/codex" for profile in candidates)


def test_gateway_falls_back_after_adapter_exception():
    profiles = [
        _profile("broken", fallback_rank=1),
        _profile("healthy", fallback_rank=2),
    ]
    gateway = ModelGateway(
        profiles,
        adapters={"broken": _RaiseAdapter(), "healthy": _SuccessAdapter()},
    )

    result = gateway.run(
        ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"})),
        "solve",
        "manifest:test",
    )

    assert result.status == "SUCCEEDED"
    assert result.provider == "healthy"
    assert result.fallback_used is True
    assert "profile_version" in result.metadata


def test_gateway_falls_back_after_unknown_adapter_status():
    profiles = [
        _profile("unknown", fallback_rank=1),
        _profile("healthy", fallback_rank=2),
    ]
    gateway = ModelGateway(
        profiles,
        adapters={"unknown": _UnknownStatusAdapter(), "healthy": _SuccessAdapter()},
    )

    result = gateway.run(
        ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"})),
        "solve",
        "manifest:test",
    )

    assert result.status == "SUCCEEDED"
    assert result.provider == "healthy"
    assert result.fallback_used is True


def test_gateway_fails_closed_for_unknown_data_classification():
    gateway = ModelGateway([_profile("local")])
    request = ModelRequest(
        role="solver",
        required_capabilities=frozenset({"reasoning"}),
        data_classification="top-secret",
    )

    assert gateway.candidates(request) == []
    result = gateway.run(request, "solve", "manifest:test")
    assert result.status == "MODEL_UNAVAILABLE"
    assert "No profile satisfies" in (result.reason or "")


def test_gateway_fails_closed_for_unknown_risk_level():
    gateway = ModelGateway([_profile("local")])
    request = ModelRequest(
        role="solver",
        required_capabilities=frozenset({"reasoning"}),
        risk_level="R9",
    )

    assert gateway.candidates(request) == []
    assert gateway.run(request, "solve", "manifest:test").status == "MODEL_UNAVAILABLE"


def test_gateway_requires_owner_approval_reference_for_r5():
    gateway = ModelGateway([_profile("local")])
    base = {
        "role": "solver",
        "required_capabilities": frozenset({"reasoning"}),
        "risk_level": "R5",
    }
    assert gateway.candidates(ModelRequest(**base)) == []
    assert gateway.candidates(ModelRequest(**base, owner_approved=True)) == []
    approved = ModelRequest(**base, owner_approved=True, approval_ref="approval-001")
    assert [profile.provider for profile in gateway.candidates(approved)] == ["local"]


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"budget_remaining": -0.01},
        {"max_latency_ms": -1},
    ],
)
def test_gateway_rejects_negative_budget_or_latency(request_kwargs):
    gateway = ModelGateway([_profile("local")])
    request = ModelRequest(
        role="solver",
        required_capabilities=frozenset({"reasoning"}),
        **request_kwargs,
    )

    assert gateway.candidates(request) == []


def test_gateway_filters_required_tools():
    profiles = [
        _profile("with-tool", fallback_rank=1, tool_permissions=frozenset({"terminal"})),
        _profile("without-tool", fallback_rank=2),
    ]
    gateway = ModelGateway(profiles)
    request = ModelRequest(
        role="solver",
        required_capabilities=frozenset({"reasoning"}),
        required_tools=frozenset({"terminal"}),
    )

    assert [profile.provider for profile in gateway.candidates(request)] == ["with-tool"]


def test_gateway_filters_by_minimum_calibration_score():
    profiles = [
        _profile("high-calibration", fallback_rank=1, calibration_score=0.91),
        _profile("low-calibration", fallback_rank=2, calibration_score=0.89),
    ]
    gateway = ModelGateway(profiles)
    request = ModelRequest(
        role="solver",
        required_capabilities=frozenset({"reasoning"}),
        min_calibration_score=0.9,
    )

    assert [profile.provider for profile in gateway.candidates(request)] == ["high-calibration"]


def test_gateway_filters_known_over_budget_profiles_but_keeps_unknown_costs():
    profiles = [
        _profile("cheap", fallback_rank=1, estimated_cost_per_1k=0.01),
        _profile("expensive", fallback_rank=2, estimated_cost_per_1k=0.20),
        _profile("unpriced", fallback_rank=3, estimated_cost_per_1k=None),
    ]
    gateway = ModelGateway(profiles)
    request = ModelRequest(
        role="solver",
        required_capabilities=frozenset({"reasoning"}),
        budget_remaining=0.05,
    )

    assert [profile.provider for profile in gateway.candidates(request)] == ["cheap", "unpriced"]


def test_gateway_fails_closed_for_unknown_profile_data_policy():
    profile = _profile("typo-policy")
    profile = ModelProfile(**{**profile.__dict__, "data_policy": "external-approvedd"})
    gateway = ModelGateway([profile])

    assert gateway.candidates(ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"}), external_network=True)) == []


def test_gateway_applies_data_policy_classification_matrix():
    profiles = [
        ModelProfile("public", "m", frozenset({"reasoning"}), frozenset({"solver"}), data_policy="public-only"),
        ModelProfile("internal", "m", frozenset({"reasoning"}), frozenset({"solver"}), data_policy="internal-only"),
        ModelProfile("local", "m", frozenset({"reasoning"}), frozenset({"solver"}), data_policy="local-only"),
        ModelProfile("external", "m", frozenset({"reasoning"}), frozenset({"solver"}), data_policy="external-approved"),
    ]
    gateway = ModelGateway(profiles)

    public = gateway.candidates(ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"}), data_classification="public"))
    confidential = gateway.candidates(ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"}), data_classification="confidential"))
    restricted = gateway.candidates(ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"}), data_classification="restricted"))
    external = gateway.candidates(ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"}), data_classification="internal", external_network=True))

    assert {profile.provider for profile in public} == {"public", "internal", "local"}
    assert {profile.provider for profile in confidential} == {"internal", "local"}
    assert {profile.provider for profile in restricted} == {"local"}
    assert {profile.provider for profile in external} == {"internal", "local", "external"}


def test_gateway_requires_owner_approval_for_r5_requests():
    gateway = ModelGateway([_profile("safe")])
    request = ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"}), risk_level="R5")
    assert gateway.candidates(request) == []
    approved = ModelRequest(
        role="solver", required_capabilities=frozenset({"reasoning"}), risk_level="R5",
        owner_approved=True, approval_ref="approval-1",
    )
    assert gateway.candidates(approved)


def test_gateway_fails_closed_for_invalid_budget_latency_or_risk():
    gateway = ModelGateway([_profile("safe")])
    assert gateway.candidates(ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"}), budget_remaining=-1)) == []
    assert gateway.candidates(ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"}), max_latency_ms=-1)) == []
    assert gateway.candidates(ModelRequest(role="solver", required_capabilities=frozenset({"reasoning"}), risk_level="R9")) == []


@pytest.mark.parametrize(
    "role,capabilities,external_network",
    [
        ("coordinator", {"long_context_reasoning", "tool_orchestration", "conflict_adjudication"}, False),
        ("scope_lock", {"document_reasoning", "citation_tracking", "multimodal_optional"}, False),
        ("vision_ocr", {"vision", "pdf", "table_formula_extraction"}, True),
        ("data_auditor", {"code_execution", "local_files", "python", "testing"}, False),
        ("independent_solver", {"independent_modeling", "counterexample", "long_context_reasoning"}, False),
        ("validation_auditor", {"code_execution", "statistics", "reproducibility", "read_only"}, False),
        ("paper_judge", {"chinese_technical_writing", "structure_following", "citation_safe"}, False),
        ("resource_manager", {"triage", "short_context", "structured_output"}, False),
    ],
)
def test_documented_role_profiles_have_at_least_one_candidate(role, capabilities, external_network):
    gateway = ModelGateway(default_profiles())
    request = ModelRequest(role=role, required_capabilities=frozenset(capabilities), external_network=external_network)
    assert gateway.candidates(request), (role, capabilities)
