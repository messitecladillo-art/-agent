#!/usr/bin/env python3
"""Run the repository Skill v2 regression gates in one deterministic command.

The runner is intentionally an orchestrator for read-only validators.  It
does not execute material-pack code, call a model provider, or mutate source
inputs.  The invalid fixture is expected to fail; that negative result is a
part of the acceptance evidence rather than a test error.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"


def _run(label: str, args: Sequence[str], *, expected: int = 0) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            list(args),
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output = completed.stdout or ""
        ok = completed.returncode == expected
        print(f"[{ 'PASS' if ok else 'FAIL' }] {label} (exit={completed.returncode}, expected={expected})")
        if not ok or output.strip():
            lines = output.rstrip().splitlines()
            for line in lines[-12:]:
                print(f"  {line}")
        return {"label": label, "ok": ok, "exit_code": completed.returncode, "expected": expected, "output_tail": output.rstrip().splitlines()[-12:]}
    except OSError as exc:
        print(f"[FAIL] {label}: {exc}")
        return {"label": label, "ok": False, "exit_code": None, "expected": expected, "error": str(exc)}


def _python(*parts: str) -> List[str]:
    return [sys.executable, "-X", "utf8", *parts]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-quick-validate", action="store_true", help="skip Codex skill-creator quick validation")
    parser.add_argument("--skip-backend", action="store_true", help="skip backend pytest (useful when optional deps are absent)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print a machine-readable summary after the human log")
    args = parser.parse_args(argv)

    results: List[Dict[str, Any]] = []
    results.append(_run("registry strict validation", _python("skills/scripts/validate_registry.py", "--strict")))

    if not args.skip_quick_validate:
        quick = Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
        if quick.is_file():
            entries = []
            registry = json.loads((SKILLS / "registry.json").read_text(encoding="utf-8"))
            for section in ("skills", "workflows"):
                entries.extend(item for item in registry.get(section, []) if isinstance(item, dict))
            for entry in entries:
                entry_path = ROOT / str(entry["path"]).replace("/", "\\")
                results.append(_run(f"quick_validate {entry['id']}", _python(str(quick), str(entry_path.parent))))
        else:
            print(f"[FAIL] skill-creator quick validator missing: {quick}")
            results.append({"label": "skill-creator quick validation", "ok": False, "error": "missing validator"})

    fixture = SKILLS / "tests" / "fixtures"
    checks = [
        ("valid workflow assembly", ["skills/scripts/audit_workflow_artifact.py", str(fixture / "valid-assembly.json"), "--strict"], 0),
        ("invalid workflow assembly is rejected", ["skills/scripts/audit_workflow_artifact.py", str(fixture / "invalid-assembly.json"), "--strict"], 1),
        ("valid data contract", ["skills/03-data-and-evidence/scripts/validate_data_contract.py", str(fixture / "valid-data-contract.json"), "--strict"], 0),
        ("valid run manifest", ["skills/06-solver-reproducibility/scripts/validate_run_manifest.py", str(fixture / "valid-run-manifest.json"), "--strict"], 0),
        ("valid reconstruction artifact", ["skills/12-evidence-reconstruction/scripts/validate_reconstruction.py", str(fixture / "valid-reconstruction-v2.json"), "--strict"], 0),
        ("historical step contract", ["skills/12-evidence-reconstruction/scripts/validate_step_contract.py"], 0),
        ("paper positive/negative fixtures", ["skills/08-paper-and-typesetting/evals/run_eval.py"], 0),
    ]
    for label, command, expected in checks:
        results.append(_run(label, _python(*command), expected=expected))

    node = shutil.which("node")
    if node:
        results.append(_run("node syntax app.js", [node, "--check", "app.js"]))
        results.append(_run("node syntax workflow-puzzle.js", [node, "--check", "workflow-puzzle.js"]))
    else:
        print("[WARN] node is not installed; JavaScript syntax checks skipped")

    if not args.skip_backend:
        results.append(_run("backend pytest", _python("-m", "pytest", "backend", "-q", "--basetemp", ".pytest-tmp-skill-regression")))

    failed = [item for item in results if not item.get("ok")]
    summary = {"schema_version": "skill-regression/v1", "root": str(ROOT), "checks": results, "passed": len(results) - len(failed), "failed": len(failed), "valid": not failed}
    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Skill regression: {'PASS' if not failed else 'FAIL'} · {summary['passed']}/{len(results)} checks")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
