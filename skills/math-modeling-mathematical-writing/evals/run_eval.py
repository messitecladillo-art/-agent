#!/usr/bin/env python3
"""Run the small forward fixtures shipped with the Skill."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
PYTHON = sys.executable


def run(*args: str) -> tuple[int, str]:
    completed = subprocess.run([PYTHON, *args], cwd=str(SKILL), text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.returncode, completed.stdout


def main() -> int:
    latex = str(SKILL / "scripts" / "audit_latex_math.py")
    contract = str(SKILL / "scripts" / "audit_paper_contract.py")
    good_tex = str(HERE / "good.tex")
    bad_tex = str(HERE / "bad.tex")
    good_contract = str(HERE / "good_contract.json")
    bad_contract = str(HERE / "bad_contract.json")

    checks = [
        ("good LaTeX", 0, run(latex, good_tex, "--release", "--json")),
        ("bad LaTeX", 1, run(latex, bad_tex, "--release")),
        ("good contract", 0, run(contract, good_contract, "--strict", "--json")),
        ("bad contract", 1, run(contract, bad_contract, "--strict")),
    ]
    for name, expected, (actual, output) in checks:
        if actual != expected:
            print(f"FAIL {name}: expected exit {expected}, got {actual}\n{output}")
            return 1
        print(f"PASS {name}: exit {actual}")

    # Regression for the evidence-chain bug found by the independent forward
    # auditor: a non-empty but unknown claim reference must not pass strict.
    with tempfile.TemporaryDirectory(prefix="paper-contract-unknown-") as temp_dir:
        payload = json.loads((HERE / "good_contract.json").read_text(encoding="utf-8"))
        payload["claims"][0]["evidence_refs"] = ["fig:missing"]
        mutated = Path(temp_dir) / "unknown-evidence.json"
        mutated.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        actual, output = run(contract, str(mutated), "--strict", "--json")
        if actual != 1 or "UNKNOWN_EVIDENCE_REF" not in output:
            print(f"FAIL unknown claim evidence reference: exit {actual}\n{output}")
            return 1
        print("PASS unknown claim evidence reference: blocked")

    with tempfile.TemporaryDirectory(prefix="paper-contract-revision-") as temp_dir:
        stale = Path(temp_dir) / "stale-registry.json"
        stale.write_text(json.dumps({"schema": "equation-registry/v1", "input_revision": "git:stale"}), encoding="utf-8")
        actual, output = run(contract, str(HERE / "good_contract.json"), "--strict", "--registry", str(stale), "--json")
        if actual != 1 or "REVISION_MISMATCH" not in output:
            print(f"FAIL stale registry revision: exit {actual}\n{output}")
            return 1
        print("PASS stale registry revision: blocked")

    # Verify machine output is valid JSON and contains the expected clean status.
    actual, output = run(latex, good_tex, "--release", "--json")
    if actual != 0 or json.loads(output)["summary"]["status"] != "PASS":
        print("FAIL good LaTeX JSON status")
        return 1
    actual, output = run(contract, good_contract, "--strict", "--json")
    if actual != 0 or json.loads(output)["summary"]["status"] != "PASS":
        print("FAIL good contract JSON status")
        return 1
    print("All forward fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
