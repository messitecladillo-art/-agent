"""Contract tests for the local collaboration API.

These tests deliberately exercise the boundaries a real provider adapter will
depend on: idempotency, CAS revisions, leases/fencing, write-set validation,
Owner approvals and explicit external relay state.
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app as api


VALID_MANIFEST = "manifest:" + "0" * 64


@pytest.fixture()
def client(monkeypatch):
    # Each test gets a fresh in-memory control plane; no test relies on order.
    monkeypatch.setattr(api, "store", api.EventStore())
    return TestClient(api.app)


def snapshot(client):
    return client.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()


def test_message_idempotency_is_state_safe(client):
    base = snapshot(client)["revision"]
    payload = {"text": "同步审计结果", "base_revision": base, "idempotency_key": "msg-1"}
    first = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json=payload)
    second = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["event"]["event_id"] == second.json()["event"]["event_id"]
    assert len(snapshot(client)["messages"]) == 1


def test_message_projection_preserves_modeling_provenance(client):
    base = snapshot(client)["revision"]
    response = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={
        "text": "Q2 参数范围需要来源",
        "base_revision": base,
        "claim_class": "hypothesis",
        "task_id": "G5",
        "subproblem_id": "Q2",
        "evidence_refs": ["artifact:param-source"],
        "target_revision": VALID_MANIFEST,
        "idempotency_key": "msg-provenance-1",
    })
    assert response.status_code == 200
    record = snapshot(client)["messages"][0]
    assert record["claim_class"] == "hypothesis"
    assert record["task_id"] == "G5"
    assert record["subproblem_id"] == "Q2"
    assert record["evidence_refs"] == ["artifact:param-source"]
    assert record["status"] == "RECEIVED"


def test_kb_document_citation_is_accepted_but_not_a_release_shortcut(client):
    base = snapshot(client)["revision"]
    citation = "kbdoc:kbdoc_0123456789abcdef"
    response = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={
        "text": "请核对这条资料建议", "base_revision": base,
        "claim_class": "hypothesis", "evidence_refs": [citation],
        "target_revision": VALID_MANIFEST, "idempotency_key": "msg-kb-citation-1",
    })
    assert response.status_code == 200
    record = snapshot(client)["messages"][0]
    assert record["evidence_refs"] == [citation]
    assert record["status"] == "RECEIVED"
    assert api.valid_evidence_ref(citation)
    assert not api.valid_evidence_ref("kbdoc:../../outside")
    assert not api.valid_evidence_ref("kbchunk:not-a-real-id")


def test_workspace_repo_citation_is_bounded_and_accepted(client):
    base = snapshot(client)["revision"]
    repo_ref = "repo:skills/01-scope-lock/SKILL.md"
    response = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={
        "text": "请以共享技能卡为候选输入，并回到题面核验",
        "base_revision": base,
        "claim_class": "hypothesis",
        "evidence_refs": [repo_ref],
        "target_revision": VALID_MANIFEST,
        "idempotency_key": "msg-repo-citation-1",
    })
    assert response.status_code == 200
    assert response.json()["event"]["payload"]["evidence_refs"] == [repo_ref]
    assert api.valid_evidence_ref(repo_ref)
    assert not api.valid_evidence_ref("repo:../outside.txt")
    assert not api.valid_evidence_ref("repo:.env")
    assert not api.valid_evidence_ref("repo:backend/.env")


@pytest.mark.parametrize("path", [
    "/.git/config",
    "/.collab/manifest.sha256",
    "/.env.example",
    "/backend/app.py",
    "/README.md",
    "/docs/api-contract.md",
])
def test_static_server_does_not_expose_checkout_or_control_files(client, path):
    response = client.get(path)
    assert response.status_code == 404


def test_static_server_keeps_allowlisted_ui_assets_available(client):
    assert client.get("/index.html").status_code == 200
    assert client.get("/styles.css").status_code == 200
    assert client.get("/workflow-puzzle.js").status_code == 200
    assert client.get("/assets/ip/xiao-qinglong-mark-v1.png").status_code == 200
    assert client.get("/assets/workflow/qinglong-puzzle-guide-v1.png").status_code == 200
    assert client.get("/assets/workflow/qinglong-puzzle-atlas-v1.png").status_code == 200


def test_static_server_keeps_non_allowlisted_root_files_private(client):
    # This file exists in the checkout, but it is not a browser asset.  The
    # root catch-all must continue to return 404 after adding the puzzle module.
    assert client.get("/docker-compose.yml").status_code == 404


def test_idempotency_key_cannot_change_request(client):
    base = snapshot(client)["revision"]
    first = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={"text": "A", "base_revision": base, "idempotency_key": "same"})
    assert first.status_code == 200
    conflict = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={"text": "B", "base_revision": base, "idempotency_key": "same"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_stale_revision_is_rejected(client):
    base = snapshot(client)["revision"]
    assert client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={"text": "first", "base_revision": base, "idempotency_key": "m-a"}).status_code == 200
    stale = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={"text": "second", "base_revision": base, "idempotency_key": "m-b"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STALE_REVISION"


def test_dispatch_validates_write_set_and_registers_envelope(client):
    response = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-1", "title": "测试任务", "owner_id": "solver-1", "objective": "返回可复现结果",
        "write_set": ["artifacts\\solver\\T-1"], "input_revision": VALID_MANIFEST,
        "acceptance": ["exit code 0"], "idempotency_key": "dispatch-1",
    })
    assert response.status_code == 200
    assert response.json()["task"]["write_set"] == ["artifacts/solver/T-1"]
    bad = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-2", "title": "坏任务", "owner_id": "solver-1", "objective": "x",
        "write_set": ["../outside"], "input_revision": VALID_MANIFEST, "idempotency_key": "dispatch-2",
    })
    assert bad.status_code == 422


def test_dispatch_accepts_explicit_evidence_roots_and_normalises_directory_glob(client):
    response = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-evidence-root", "title": "证据目录任务", "owner_id": "solver-1", "objective": "写入审查证据",
        "write_set": [".collab\\evidence\\T-evidence-root\\**", "runtime\\artifacts\\T-evidence-root"],
        "input_revision": VALID_MANIFEST, "idempotency_key": "dispatch-evidence-root",
    })
    assert response.status_code == 200
    assert response.json()["task"]["write_set"] == [".collab/evidence/T-evidence-root", "runtime/artifacts/T-evidence-root"]


@pytest.mark.parametrize("unsafe_path", [
    ".env",
    ".env.example",
    "AGENTS.md",
    "backend/app.py",
    ".collab/charter.yaml",
    ".collab/events.jsonl",
    "runtime/collab-state.json",
    "secrets/key.txt",
    "paper/.hidden-result.json",
    "artifacts/../backend/app.py",
    "artifacts/result/*.json",
    "artifacts/out\x00.txt",
    "artifacts/CON",
    "artifacts/result.json:secret",
    "artifacts/result.json.",
    "artifacts/result.json ",
    "artifacts/AGENTS.md.",
])
def test_dispatch_rejects_control_hidden_sensitive_and_non_artifact_write_sets(client, unsafe_path):
    response = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-unsafe-" + str(abs(hash(unsafe_path))), "title": "越界任务", "owner_id": "solver-1", "objective": "x",
        "write_set": [unsafe_path], "input_revision": VALID_MANIFEST,
        "idempotency_key": "dispatch-unsafe-" + str(abs(hash(unsafe_path))),
    })
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_WRITE_SET"


def test_dispatch_rejects_unknown_dependency_and_overlapping_write_set(client):
    first = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-existing", "title": "已有任务", "owner_id": "solver-1", "objective": "x",
        "write_set": ["artifacts/shared"], "input_revision": VALID_MANIFEST, "idempotency_key": "dispatch-existing",
    })
    assert first.status_code == 200
    unknown = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-unknown", "title": "坏依赖", "owner_id": "solver-1", "objective": "x",
        "depends_on": ["does-not-exist"], "input_revision": VALID_MANIFEST, "idempotency_key": "dispatch-unknown",
    })
    assert unknown.status_code == 422
    overlap = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-overlap", "title": "重叠写集", "owner_id": "solver-2", "objective": "x",
        "write_set": ["artifacts/shared/result.json"], "input_revision": VALID_MANIFEST, "idempotency_key": "dispatch-overlap",
    })
    assert overlap.status_code == 409
    assert overlap.json()["detail"]["code"] == "WRITE_SET_CONFLICT"


def test_lease_and_fencing_gate(client):
    dispatch = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-lease", "title": "租约任务", "owner_id": "solver-1", "objective": "x",
        "input_revision": VALID_MANIFEST, "idempotency_key": "dispatch-lease",
    })
    assert dispatch.status_code == 200
    base = snapshot(client)["revision"]
    claimed = client.post("/api/tasks/T-lease/claim", json={"agent_id": "solver-1", "base_revision": base, "idempotency_key": "claim-1"})
    assert claimed.status_code == 200
    lease = claimed.json()["task"]["lease"]
    held = client.post("/api/tasks/T-lease/claim", json={"agent_id": "solver-2", "base_revision": claimed.json()["revision"], "idempotency_key": "claim-2"})
    assert held.status_code == 409
    assert held.json()["detail"]["code"] == "TASK_LEASE_HELD"
    stale = client.post("/api/tasks/T-lease/heartbeat", json={"agent_id": "solver-1", "fencing_epoch": lease["fencing_epoch"] + 1, "base_revision": claimed.json()["revision"], "idempotency_key": "hb-stale"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STALE_FENCING_EPOCH"


def test_first_claim_is_bound_to_dispatch_owner(client):
    dispatch = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-owner-bound", "title": "首领认领约束", "owner_id": "solver-1", "objective": "只允许指定 worker 首次认领",
        "input_revision": VALID_MANIFEST, "idempotency_key": "dispatch-owner-bound",
    })
    assert dispatch.status_code == 200
    foreign = client.post("/api/tasks/T-owner-bound/claim", json={
        "agent_id": "solver-2", "base_revision": dispatch.json()["revision"], "idempotency_key": "claim-owner-bound-foreign",
    })
    assert foreign.status_code == 403
    assert foreign.json()["detail"]["code"] == "TASK_OWNER_MISMATCH"
    owned = client.post("/api/tasks/T-owner-bound/claim", json={
        "agent_id": "solver-1", "base_revision": dispatch.json()["revision"], "idempotency_key": "claim-owner-bound-owner",
    })
    assert owned.status_code == 200
    assert owned.json()["task"]["claimed_by"] == "solver-1"


def test_expired_lease_can_be_reclaimed_with_a_new_epoch(client):
    dispatch = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-reclaim", "title": "可抢占任务", "owner_id": "solver-1", "objective": "x",
        "input_revision": VALID_MANIFEST, "idempotency_key": "dispatch-reclaim",
    })
    assert dispatch.status_code == 200
    claimed = client.post("/api/tasks/T-reclaim/claim", json={
        "agent_id": "solver-1", "base_revision": dispatch.json()["revision"], "idempotency_key": "claim-reclaim-1",
    })
    old_lease = claimed.json()["task"]["lease"]
    api.store.tasks["T-reclaim"]["lease"]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    reclaim = client.post("/api/tasks/T-reclaim/claim", json={
        "agent_id": "solver-2", "base_revision": snapshot(client)["revision"], "idempotency_key": "claim-reclaim-2",
    })
    assert reclaim.status_code == 200
    assert reclaim.json()["task"]["lease"]["fencing_epoch"] > old_lease["fencing_epoch"]
    stale = client.post("/api/tasks/T-reclaim/heartbeat", json={
        "agent_id": "solver-1", "fencing_epoch": old_lease["fencing_epoch"],
        "base_revision": reclaim.json()["revision"], "idempotency_key": "hb-reclaimed-old",
    })
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STALE_FENCING_EPOCH"


@pytest.mark.parametrize("terminal_status", ["FAILED", "TIMEOUT"])
def test_failed_or_timed_out_task_requires_explicit_requeue_before_claim(client, terminal_status):
    dispatch = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": f"T-direct-claim-{terminal_status.lower()}", "title": "失败重试状态门",
        "owner_id": "solver-1", "objective": "先回队再认领", "input_revision": VALID_MANIFEST,
        "idempotency_key": f"dispatch-direct-claim-{terminal_status.lower()}",
    })
    assert dispatch.status_code == 200
    task_id = dispatch.json()["task"]["id"]
    api.store.tasks[task_id]["status"] = terminal_status
    rejected = client.post(f"/api/tasks/{task_id}/claim", json={
        "agent_id": "solver-1", "base_revision": snapshot(client)["revision"],
        "idempotency_key": f"claim-direct-{terminal_status.lower()}",
    })
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "TASK_NOT_CLAIMABLE"
    assert rejected.json()["detail"]["status"] == terminal_status


def test_result_submission_moves_claimed_task_to_review_and_replays_safely(client):
    dispatch = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-result", "title": "结果回执", "owner_id": "solver-1", "objective": "提交可复现结果",
        "input_revision": "manifest:" + "0" * 64, "idempotency_key": "dispatch-result",
    })
    assert dispatch.status_code == 200
    base = snapshot(client)["revision"]
    claimed = client.post("/api/tasks/T-result/claim", json={
        "agent_id": "solver-1", "base_revision": base, "idempotency_key": "claim-result",
    })
    assert claimed.status_code == 200
    lease = claimed.json()["task"]["lease"]
    payload = {
        "agent_id": "solver-1", "fencing_epoch": lease["fencing_epoch"], "status": "READY_FOR_REVIEW",
        "summary": "clean run completed", "artifact_refs": ["artifact:result-v1"],
        "evidence_refs": ["run:clean-1"], "commands": ["python run.py --seed 20260831"],
        "result_hash": "sha256:" + "0" * 64, "target_revision": claimed.json()["revision"],
        "idempotency_key": "result-1",
    }
    stale = dict(payload)
    stale.update({"fencing_epoch": lease["fencing_epoch"] + 1, "idempotency_key": "result-stale"})
    stale_response = client.post("/api/tasks/T-result/result", json=stale)
    assert stale_response.status_code == 409
    assert stale_response.json()["detail"]["code"] == "STALE_FENCING_EPOCH"

    first = client.post("/api/tasks/T-result/result", json=payload)
    assert first.status_code == 200
    assert first.json()["task"]["status"] == "READY_FOR_REVIEW"
    assert first.json()["event"]["type"] == "TASK_RESULT"
    assert first.json()["task"]["lease"] is None
    second = client.post("/api/tasks/T-result/result", json=payload)
    assert second.status_code == 200
    assert second.json()["event"]["event_id"] == first.json()["event"]["event_id"]
    assert second.json()["task"]["result"]["result_hash"] == payload["result_hash"]
    heartbeat = client.post("/api/tasks/T-result/heartbeat", json={
        "agent_id": "solver-1", "fencing_epoch": lease["fencing_epoch"],
        "base_revision": first.json()["revision"], "idempotency_key": "hb-after-result",
    })
    assert heartbeat.status_code == 409
    assert heartbeat.json()["detail"]["code"] == "HEARTBEAT_STATE_INVALID"


def test_review_cannot_skip_ready_for_review(client):
    base = snapshot(client)["revision"]
    response = client.post("/api/tasks/G3/review", json={"reviewer_id": "validator", "verdict": "accept", "summary": "premature", "independence_basis": "clean snapshot", "check_logs": ["not-run"], "evidence_refs": ["artifact:none"], "target_revision": base, "idempotency_key": "review-premature"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REVIEW_STATE_INVALID"


def test_review_accept_requires_a_verified_worker_result(client):
    base = snapshot(client)["revision"]
    response = client.post("/api/tasks/G6-B/review", json={
        "reviewer_id": "validator", "verdict": "accept", "summary": "no result",
        "independence_basis": "clean snapshot", "check_logs": ["echo pass"],
        "evidence_refs": ["artifact:route-b"], "target_revision": base,
        "idempotency_key": "review-no-result",
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RESULT_REQUIRED_FOR_ACCEPT"


def test_critical_finding_must_close_before_accept(client):
    api.store.tasks["G7"]["status"] = "READY_FOR_REVIEW"
    api.store.tasks["G7"]["result"] = {
        "status": "READY_FOR_REVIEW",
        "artifact_refs": ["artifact:counterexample-v2"],
        "evidence_refs": ["artifact:counterexample-v2"],
    }
    base = snapshot(client)["revision"]
    blocked = client.post("/api/tasks/G7/review", json={"reviewer_id": "validator", "verdict": "accept", "summary": "仍有 P1", "independence_basis": "clean snapshot", "check_logs": ["clean-run"], "evidence_refs": ["artifact:counterexample-v2"], "target_revision": base, "idempotency_key": "review-g7-blocked"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "CRITICAL_FINDINGS_OPEN"
    closed = client.post("/api/tasks/G7/findings/F-G7-01/close", json={"actor_id": "critic", "evidence_ref": "artifact:counterexample-v2", "target_revision": base, "idempotency_key": "close-g7-1"})
    assert closed.status_code == 200
    next_revision = closed.json()["revision"]
    accepted = client.post("/api/tasks/G7/review", json={"reviewer_id": "validator", "verdict": "accept", "summary": "复核通过", "independence_basis": "clean snapshot", "check_logs": ["clean-run", "sensitivity"], "evidence_refs": ["artifact:counterexample-v2"], "target_revision": next_revision, "idempotency_key": "review-g7-accepted"})
    assert accepted.status_code == 200
    assert accepted.json()["task"]["status"] == "VERIFIED"


def test_finding_close_rejects_unknown_evidence_and_unauthorized_actor(client):
    # The reference is registered by the task result, but no arbitrary caller
    # should be able to close a P1 finding or introduce a new artifact pointer.
    api.store.tasks["G7"]["result"] = {
        "status": "READY_FOR_REVIEW",
        "artifact_refs": ["artifact:registered-finding-evidence"],
        "evidence_refs": ["artifact:registered-finding-evidence"],
    }
    base = snapshot(client)["revision"]
    denied = client.post("/api/tasks/G7/findings/F-G7-01/close", json={
        "actor_id": "random-agent", "evidence_ref": "artifact:registered-finding-evidence",
        "target_revision": base, "idempotency_key": "close-finding-unauthorized",
    })
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "FINDING_CLOSE_FORBIDDEN"

    user_alias = client.post("/api/tasks/G7/findings/F-G7-01/close", json={
        "actor_id": "user", "evidence_ref": "artifact:registered-finding-evidence",
        "target_revision": base, "idempotency_key": "close-finding-user-alias",
    })
    assert user_alias.status_code == 403

    unknown = client.post("/api/tasks/G7/findings/F-G7-01/close", json={
        "actor_id": "critic", "evidence_ref": "artifact:unregistered-finding-evidence",
        "target_revision": base, "idempotency_key": "close-finding-unknown-ref",
    })
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "FINDING_EVIDENCE_UNKNOWN"


def test_finding_close_accepts_task_scoped_event_evidence(client):
    base = snapshot(client)["revision"]
    message = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={
        "text": "记录待复核证据指针", "task_id": "G7",
        "evidence_refs": ["artifact:event-registered"],
        "target_revision": VALID_MANIFEST, "base_revision": base,
        "idempotency_key": "message-finding-evidence-event",
    })
    assert message.status_code == 200
    closed = client.post("/api/tasks/G7/findings/F-G7-01/close", json={
        "actor_id": "critic", "evidence_ref": "artifact:event-registered",
        "target_revision": message.json()["revision"], "idempotency_key": "close-finding-event-ref",
    })
    assert closed.status_code == 200
    assert closed.json()["finding"]["evidence_ref"] == "artifact:event-registered"


def test_external_relay_requires_owner_approval(client):
    missing = client.post("/api/relays", json={"from_agent_id": "coordinator", "to_agent_id": "antigravity/reviewer", "task_id": "G7", "input_revision": VALID_MANIFEST, "payload": {"question": "review"}, "idempotency_key": "relay-1"})
    assert missing.status_code == 428
    control_revision = snapshot(client)["revision"]
    approval = client.post(f"/api/projects/{api.PROJECT_ID}/approvals", json={"owner_id": "owner", "scope": "external-relay", "decision": "approve", "target_revision": VALID_MANIFEST, "base_revision": control_revision, "idempotency_key": "approval-test"})
    assert approval.status_code == 200
    approval_ref = approval.json()["approval"]["approval_id"]
    allowed = client.post("/api/relays", json={"from_agent_id": "coordinator", "to_agent_id": "antigravity/reviewer", "task_id": "G7", "input_revision": VALID_MANIFEST, "approval_ref": approval_ref, "payload": {"question": "review"}, "idempotency_key": "relay-2"})
    assert allowed.status_code == 200
    assert allowed.json()["relay"]["status"] == "PENDING_RELAY"
    unknown_external = client.post("/api/relays", json={"from_agent_id": "coordinator", "to_agent_id": "claude/reviewer", "task_id": "G7", "input_revision": VALID_MANIFEST, "payload": {}, "idempotency_key": "relay-3"})
    assert unknown_external.status_code == 428


def test_external_relay_ack_requires_matching_nonce_and_hash(client):
    control_revision = snapshot(client)["revision"]
    approval = client.post(f"/api/projects/{api.PROJECT_ID}/approvals", json={
        "owner_id": "owner", "scope": "external-relay", "decision": "approve",
        "target_revision": VALID_MANIFEST, "base_revision": control_revision, "idempotency_key": "approval-ack",
    })
    ref = approval.json()["approval"]["approval_id"]
    relay = client.post("/api/relays", json={
        "from_agent_id": "coordinator", "to_agent_id": "antigravity/reviewer", "task_id": "G7",
        "input_revision": VALID_MANIFEST, "approval_ref": ref, "payload": {"question": "review"},
        "idempotency_key": "relay-ack",
    })
    assert relay.status_code == 200
    packet = relay.json()["relay"]
    bad = client.post(f"/api/relays/{packet['relay_id']}/ack", json={
        "relay_id": packet["relay_id"], "to_agent_id": packet["to_agent_id"], "nonce": "wrongnonce",
        "input_hash": packet["input_hash"], "target_revision": relay.json()["revision"], "idempotency_key": "ack-bad",
    })
    assert bad.status_code == 409
    assert bad.json()["detail"]["code"] == "RELAY_ACK_HASH_MISMATCH"
    good = client.post(f"/api/relays/{packet['relay_id']}/ack", json={
        "relay_id": packet["relay_id"], "to_agent_id": packet["to_agent_id"], "nonce": packet["nonce"],
        "input_hash": packet["input_hash"], "target_revision": relay.json()["revision"], "idempotency_key": "ack-good",
    })
    assert good.status_code == 200
    assert good.json()["relay"]["status"] == "CONNECTIVITY_VERIFIED"


def test_dispatch_rejects_dependency_cycle(client):
    first = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-cycle-a", "title": "A", "owner_id": "a", "objective": "x",
        "depends_on": ["G1"], "write_set": ["artifacts/cycle/a"], "input_revision": VALID_MANIFEST,
        "idempotency_key": "cycle-a-1",
    })
    assert first.status_code == 200
    second = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-cycle-b", "title": "B", "owner_id": "b", "objective": "x",
        "depends_on": ["T-cycle-a"], "write_set": ["artifacts/cycle/b"], "input_revision": VALID_MANIFEST,
        "idempotency_key": "cycle-b-1",
    })
    assert second.status_code == 200
    cycle = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-cycle-a", "title": "A2", "owner_id": "a", "objective": "x",
        "depends_on": ["T-cycle-b"], "write_set": ["artifacts/cycle/a2"], "input_revision": VALID_MANIFEST,
        "idempotency_key": "cycle-a-2",
    })
    assert cycle.status_code == 422
    assert cycle.json()["detail"]["code"] == "INVALID_DEPENDENCY_GRAPH"


def test_event_chain_and_bounded_replay(client):
    base = snapshot(client)["revision"]
    for index in range(3):
        response = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={
            "text": f"event-{index}", "base_revision": base if index == 0 else None, "idempotency_key": f"page-{index}",
        })
        assert response.status_code == 200
        base = response.json()["revision"]
    page = client.get(f"/api/projects/{api.PROJECT_ID}/events?after_seq=0&limit=1")
    assert page.status_code == 200
    body = page.json()
    assert len(body["events"]) == 1 and body["has_more"] is True
    assert body["events"][0]["event_hash"].startswith("sha256:")
    assert api.store.verify_event_chain() is True


def test_model_profiles_are_capability_registry(client):
    response = client.get("/api/model-profiles")
    assert response.status_code == 200
    providers = {item["provider"] for item in response.json()["profiles"]}
    assert {"openai/codex", "claude", "qoder", "antigravity"}.issubset(providers)


def test_model_route_is_read_only_and_capability_first(client):
    response = client.post("/api/model-route", json={
        "role": "data_auditor",
        "required_capabilities": ["code_execution", "local_files", "python", "testing"],
        "data_classification": "internal",
        "external_network": False,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ROUTE_FOUND"
    assert body["execution"] == "preview_only"
    assert body["selected"]["provider"] == "qoder"
    assert client.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()["next_seq"] == 0


def test_model_route_blocks_external_profile_without_egress(client):
    response = client.post("/api/model-route", json={
        "role": "vision",
        "required_capabilities": ["vision"],
        "data_classification": "internal",
        "external_network": False,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "MODEL_UNAVAILABLE"


def test_snapshot_exposes_one_run_identity_and_revision_context(client):
    body = snapshot(client)
    assert body["project_id"] == api.PROJECT_ID == "HGC-MF-2026-001"
    assert body["run_id"] == api.RUN_ID == "RUN-MF-2026-0831"
    context = body["context"]
    assert context["project_id"] == body["project_id"]
    assert context["run_id"] == body["run_id"]
    assert context["input_revision"].startswith(("manifest:", "source:"))
    assert context["worktree_revision"] == context["input_revision"]
    assert context["control_revision"] == body["revision"]


def test_message_without_provenance_is_projected_unverified(client):
    response = client.post(f"/api/projects/{api.PROJECT_ID}/messages", json={
        "text": "没有来源的经验判断", "idempotency_key": "msg-unverified-1",
    })
    assert response.status_code == 200
    record = snapshot(client)["messages"][0]
    assert record["claim_class"] == "unknown"
    assert record["evidence_refs"] == []
    assert record["status"] == "UNVERIFIED"
    assert record["provenance_status"] == "UNVERIFIED"


def test_explicit_modeling_result_requires_two_distinct_validation_checks(client):
    dispatch = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-validation-shape", "title": "校验结构", "owner_id": "solver-1",
        "objective": "提交带双重校验的结果", "input_revision": VALID_MANIFEST,
        "idempotency_key": "dispatch-validation-shape",
    })
    assert dispatch.status_code == 200
    claimed = client.post("/api/tasks/T-validation-shape/claim", json={
        "agent_id": "solver-1", "base_revision": dispatch.json()["revision"],
        "idempotency_key": "claim-validation-shape",
    })
    lease = claimed.json()["task"]["lease"]
    response = client.post("/api/tasks/T-validation-shape/result", json={
        "agent_id": "solver-1", "fencing_epoch": lease["fencing_epoch"],
        "status": "READY_FOR_REVIEW", "summary": "仅有一个校验", "artifact_refs": ["artifact:shape"],
        "evidence_refs": ["run:shape"], "commands": ["python check.py"],
        "result_hash": "sha256:" + "0" * 64, "problem_type": "optimization",
        "validation_checks": [{"check_kind": "baseline", "scope": "train", "threshold": 0.1,
                                "exit_code": 0, "result_hash": "sha256:" + "1" * 64}],
        "target_revision": claimed.json()["revision"], "idempotency_key": "result-validation-shape",
    })
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_STRUCTURE_INVALID"


def test_legacy_result_is_unverified_and_review_accept_is_blocked(client):
    dispatch = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-validation-legacy", "title": "旧适配器", "owner_id": "solver-1",
        "objective": "迁移旧结果", "input_revision": VALID_MANIFEST,
        "idempotency_key": "dispatch-validation-legacy",
    })
    assert dispatch.status_code == 200
    claimed = client.post("/api/tasks/T-validation-legacy/claim", json={
        "agent_id": "solver-1", "base_revision": dispatch.json()["revision"],
        "idempotency_key": "claim-validation-legacy",
    })
    lease = claimed.json()["task"]["lease"]
    result = client.post("/api/tasks/T-validation-legacy/result", json={
        "agent_id": "solver-1", "fencing_epoch": lease["fencing_epoch"], "status": "READY_FOR_REVIEW",
        "summary": "旧结果", "artifact_refs": ["artifact:legacy"], "evidence_refs": ["run:legacy"],
        "commands": ["python legacy.py"], "result_hash": "sha256:" + "0" * 64,
        "target_revision": claimed.json()["revision"], "idempotency_key": "result-validation-legacy",
    })
    assert result.status_code == 200
    assert result.json()["task"]["status"] == "READY_FOR_REVIEW"
    assert result.json()["task"]["result"]["validation_gate"]["status"] == "UNVERIFIED"
    review = client.post("/api/tasks/T-validation-legacy/review", json={
        "reviewer_id": "validator", "verdict": "accept", "summary": "尝试接受旧结果",
        "independence_basis": "independent rerun", "check_logs": ["legacy"],
        "evidence_refs": ["artifact:legacy"], "target_revision": result.json()["revision"],
        "idempotency_key": "review-validation-legacy",
    })
    assert review.status_code == 409
    assert review.json()["detail"]["code"] == "VALIDATION_GATE_BLOCKED"


def test_revise_requeue_then_claim_is_explicit_and_idempotent(client):
    dispatch = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-requeue", "title": "显式重试", "owner_id": "solver-1", "reviewer_id": "validator",
        "objective": "先复核再重新排队", "input_revision": VALID_MANIFEST,
        "idempotency_key": "dispatch-requeue",
    })
    assert dispatch.status_code == 200
    claimed = client.post("/api/tasks/T-requeue/claim", json={
        "agent_id": "solver-1", "base_revision": dispatch.json()["revision"], "idempotency_key": "claim-requeue",
    })
    assert claimed.status_code == 200
    lease = claimed.json()["task"]["lease"]
    result = client.post("/api/tasks/T-requeue/result", json={
        "agent_id": "solver-1", "fencing_epoch": lease["fencing_epoch"], "status": "READY_FOR_REVIEW",
        "summary": "等待独立复核", "artifact_refs": ["artifact:retry-v1"], "evidence_refs": ["run:retry-v1"],
        "commands": ["python retry.py"], "result_hash": "sha256:" + "0" * 64,
        "target_revision": claimed.json()["revision"], "idempotency_key": "result-requeue",
    })
    assert result.status_code == 200
    review = client.post("/api/tasks/T-requeue/review", json={
        "reviewer_id": "validator", "verdict": "revise", "summary": "补充边界样本",
        "independence_basis": "independent rerun", "check_logs": ["review.log"],
        "evidence_refs": ["artifact:retry-v1"], "target_revision": result.json()["revision"],
        "idempotency_key": "review-requeue",
    })
    assert review.status_code == 200
    assert review.json()["task"]["status"] == "BLOCKED"
    requeue_payload = {
        "actor_id": "owner", "reason": "补充边界样本后重跑", "evidence_refs": ["artifact:boundary-note"],
        "target_revision": review.json()["revision"], "idempotency_key": "requeue-1",
    }
    requeued = client.post("/api/tasks/T-requeue/requeue", json=requeue_payload)
    assert requeued.status_code == 200
    body = requeued.json()
    assert body["event"]["type"] == "TASK_REQUEUED"
    assert body["task"]["status"] == "QUEUED"
    assert body["task"]["lease"] is None and body["task"]["claimed_by"] is None
    assert body["task"]["requeue_count"] == 1
    assert body["task"]["previous_result"]["status"] == "READY_FOR_REVIEW"
    replay = client.post("/api/tasks/T-requeue/requeue", json=requeue_payload)
    assert replay.status_code == 200
    assert replay.json()["event"]["event_id"] == body["event"]["event_id"]
    claim_again = client.post("/api/tasks/T-requeue/claim", json={
        "agent_id": "solver-1", "base_revision": body["revision"], "idempotency_key": "claim-requeue-again",
    })
    assert claim_again.status_code == 200
    assert claim_again.json()["task"]["status"] == "IN_PROGRESS"


def test_requeue_rejects_unauthorized_actor_and_invalid_state(client):
    dispatch = client.post(f"/api/projects/{api.PROJECT_ID}/dispatch", json={
        "task_id": "T-requeue-auth", "title": "重试权限", "owner_id": "solver-1", "objective": "x",
        "input_revision": VALID_MANIFEST, "idempotency_key": "dispatch-requeue-auth",
    })
    assert dispatch.status_code == 200
    api.store.tasks["T-requeue-auth"]["status"] = "BLOCKED"
    denied = client.post("/api/tasks/T-requeue-auth/requeue", json={
        "actor_id": "solver-2", "reason": "抢占", "evidence_refs": ["artifact:reason"],
        "target_revision": api.store.revision, "idempotency_key": "requeue-auth-denied",
    })
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "TASK_REQUEUE_FORBIDDEN"
    api.store.tasks["T-requeue-auth"]["status"] = "QUEUED"
    invalid_state = client.post("/api/tasks/T-requeue-auth/requeue", json={
        "actor_id": "owner", "reason": "重复入队", "evidence_refs": ["artifact:reason"],
        "target_revision": api.store.revision, "idempotency_key": "requeue-auth-invalid-state",
    })
    assert invalid_state.status_code == 409
    assert invalid_state.json()["detail"]["code"] == "TASK_REQUEUE_STATE_INVALID"


def test_artifact_gate_hashes_local_file_and_rejects_fake_paths(client):
    artifact_path = api.ROOT / "paper" / "t14-artifact.bin"
    artifact_path.write_bytes(b"t14 provenance")
    empty_hash = "sha256:" + hashlib.sha256(b"").hexdigest()
    try:
        artifact_hash = "sha256:" + hashlib.sha256(b"t14 provenance").hexdigest()
        valid = api.artifact_provenance_gate({
            "artifact_refs": ["artifact:paper-t14"], "evidence_refs": [],
            "target_revision": VALID_MANIFEST,
            "artifact_manifest": [{"ref": "artifact:paper-t14", "path": "paper/t14-artifact.bin",
                                    "sha256": artifact_hash, "command": "python write_artifact.py", "exit_code": 0,
                                    "target_revision": VALID_MANIFEST}],
        }, task_record={"write_set": ["paper"]})
        assert valid["ready"] is True
        assert valid["entry_checks"][0]["status"] == "VERIFIED_BYTES"
        mismatch = api.artifact_provenance_gate({
            "artifact_refs": ["artifact:paper-t14"], "evidence_refs": [], "target_revision": VALID_MANIFEST,
            "artifact_manifest": [{"ref": "artifact:paper-t14", "path": "paper/t14-artifact.bin",
                                    "sha256": "sha256:" + "0" * 64, "command": "python write_artifact.py", "exit_code": 0,
                                    "target_revision": VALID_MANIFEST}],
        })
        assert mismatch["ready"] is False
        assert "manifest_hash_mismatch" in mismatch["reasons"]
    finally:
        artifact_path.unlink(missing_ok=True)

    fabricated = api.artifact_provenance_gate({
        "artifact_refs": ["artifact:fake"], "evidence_refs": [], "target_revision": VALID_MANIFEST,
        "artifact_manifest": [{"ref": "artifact:fake", "path": "C:/Windows/System32/not-here.bin",
                                "sha256": empty_hash, "command": "echo fabricated", "exit_code": 0,
                                "target_revision": VALID_MANIFEST}],
    }, task_record={"write_set": ["paper"]})
    assert fabricated["ready"] is False
    assert "manifest_path_untrusted" in fabricated["reasons"]



def test_optional_json_journal_survives_restart():
    path = __import__("pathlib").Path(__file__).with_name("_test_collab_state.json")
    if path.exists():
        path.unlink()
    first = api.EventStore(str(path))

    async def write_once():
        return await first.append(actor_id="owner", event_type="MESSAGE", payload={"text": "persist me"}, idempotency_key="persist-1")

    try:
        event = asyncio.run(write_once())
        second = api.EventStore(str(path))
        assert second.events[0].event_id == event.event_id
        assert second.messages == []  # event-only append intentionally has no message projection
        assert second.revision.startswith("manifest:") and len(second.revision.split(":", 1)[1]) == 64
    finally:
        if path.exists():
            path.unlink()


def test_projection_digest_detects_out_of_band_edit(tmp_path):
    path = tmp_path / "collab-state.json"
    first = api.EventStore(str(path))

    async def write_once():
        return await first.append(actor_id="owner", event_type="MESSAGE", payload={"text": "integrity"}, idempotency_key="projection-1")

    asyncio.run(write_once())
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"]["G1"]["title"] = "tampered outside event log"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(RuntimeError, match="projection integrity"):
        api.EventStore(str(path))
