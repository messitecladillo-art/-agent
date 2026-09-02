#!/usr/bin/env python3
"""Validate the machine-readable seven-step MHAgent reconstruction contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_LEVELS = {"OBSERVED", "INFERRED", "HYPOTHESIS"}
ALLOWED_CHECKPOINTS = {"approve", "feedback", "none", "unknown"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
REQUIRED_STEP_FIELDS = {
    "id",
    "display_name",
    "order",
    "status_observed",
    "evidence_confidence",
    "inputs",
    "outputs",
    "responsibilities",
    "method_chain",
    "validation_gates",
    "checkpoint_declared",
    "handoff_to",
    "evidence_refs",
    "open_questions",
    "failure_policy",
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def validate(contract: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(contract, dict):
        return ["root must be an object"]

    for field in ("schema_version", "source_kind", "source_artifact", "status", "steps"):
        if field not in contract:
            fail(errors, f"missing root field: {field}")
    if contract.get("schema_version") != "mhagent-reconstruction/v1":
        fail(errors, "schema_version must be mhagent-reconstruction/v1")
    if contract.get("status") not in {"READY_FOR_REVIEW", "ACCEPTED"}:
        fail(errors, "status must be READY_FOR_REVIEW or ACCEPTED")

    steps = contract.get("steps")
    if not isinstance(steps, list):
        return errors + ["steps must be an array"]
    if len(steps) != 7:
        fail(errors, f"expected 7 steps, got {len(steps)}")

    ids: list[str] = []
    orders: list[int] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            fail(errors, f"steps[{index}] must be an object")
            continue
        missing = sorted(REQUIRED_STEP_FIELDS - set(step))
        if missing:
            fail(errors, f"steps[{index}] missing fields: {', '.join(missing)}")
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            fail(errors, f"steps[{index}].id must be a non-empty string")
        else:
            if step_id in ids:
                fail(errors, f"duplicate step id: {step_id}")
            ids.append(step_id)

        order = step.get("order")
        if not isinstance(order, int) or isinstance(order, bool):
            fail(errors, f"steps[{index}].order must be an integer")
        else:
            orders.append(order)

        confidence = step.get("evidence_confidence")
        if confidence not in ALLOWED_CONFIDENCE:
            fail(errors, f"steps[{index}].evidence_confidence is invalid: {confidence!r}")

        for field in ("inputs", "outputs", "responsibilities", "method_chain", "validation_gates"):
            value = step.get(field)
            if not isinstance(value, list) or not value:
                fail(errors, f"steps[{index}].{field} must be a non-empty array")
            elif field != "validation_gates":
                for item_index, item in enumerate(value):
                    if not isinstance(item, str) or not item.strip():
                        fail(errors, f"steps[{index}].{field}[{item_index}] must be non-empty text")
        gates = step.get("validation_gates", [])
        if isinstance(gates, list):
            for gate_index, gate in enumerate(gates):
                if not isinstance(gate, dict):
                    fail(errors, f"steps[{index}].validation_gates[{gate_index}] must be an object")
                    continue
                for gate_field in ("id", "check", "level"):
                    if gate_field not in gate:
                        fail(errors, f"steps[{index}].validation_gates[{gate_index}] missing {gate_field}")
                if not isinstance(gate.get("id"), str) or not gate.get("id", "").strip():
                    fail(errors, f"steps[{index}].validation_gates[{gate_index}].id must be non-empty text")
                if not isinstance(gate.get("check"), str) or not gate.get("check", "").strip():
                    fail(errors, f"steps[{index}].validation_gates[{gate_index}].check must be non-empty text")
        checkpoint = step.get("checkpoint_declared")
        if checkpoint not in ALLOWED_CHECKPOINTS:
            fail(errors, f"steps[{index}].checkpoint_declared is invalid: {checkpoint!r}")
        if not isinstance(step.get("failure_policy"), str) or not step.get("failure_policy", "").strip():
            fail(errors, f"steps[{index}].failure_policy must be non-empty text")
        refs = step.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            fail(errors, f"steps[{index}].evidence_refs must be a non-empty array")
        elif any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            fail(errors, f"steps[{index}].evidence_refs entries must be non-empty text")
        questions = step.get("open_questions")
        if not isinstance(questions, list):
            fail(errors, f"steps[{index}].open_questions must be an array")
        elif any(not isinstance(item, str) or not item.strip() for item in questions):
            fail(errors, f"steps[{index}].open_questions entries must be text")
        handoffs = step.get("handoff_to")
        if not isinstance(handoffs, list):
            fail(errors, f"steps[{index}].handoff_to must be an array")
        elif any(not isinstance(item, str) or not item.strip() for item in handoffs):
            fail(errors, f"steps[{index}].handoff_to entries must be non-empty text")
        for gate in gates if isinstance(gates, list) else []:
            if isinstance(gate, dict) and gate.get("level") not in ALLOWED_LEVELS:
                fail(errors, f"steps[{index}] has invalid evidence level: {gate.get('level')!r}")

    if sorted(orders) != list(range(7)):
        fail(errors, f"orders must be exactly 0..6, got {orders}")
    known_ids = set(ids)
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        handoffs = step.get("handoff_to", [])
        if not isinstance(handoffs, list):
            continue
        for target in handoffs:
            if target not in known_ids:
                fail(errors, f"steps[{index}] handoff target is unknown: {target!r}")
    return errors


def main() -> int:
    default_path = Path(__file__).resolve().parent.parent / "references" / "step-contracts.json"
    path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_path
    try:
        with path.open("r", encoding="utf-8") as handle:
            contract = json.load(handle)
    except FileNotFoundError:
        print(f"ERROR: contract not found: {path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON at {path}: {exc}", file=sys.stderr)
        return 2

    errors = validate(contract)
    if errors:
        print(f"INVALID: {path}")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"VALID: {path} | schema={contract['schema_version']} | "
        f"steps={len(contract['steps'])} | status={contract['status']}"
    )
    for step in sorted(contract["steps"], key=lambda item: item["order"]):
        print(
            f"  {step['order']}: {step['id']} | "
            f"checkpoint={step['checkpoint_declared']} | "
            f"gates={len(step['validation_gates'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
