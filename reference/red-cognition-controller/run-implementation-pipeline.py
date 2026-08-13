#!/usr/bin/env python3
"""Implementation pipeline runner — Stage-5 orchestration.

Wires the hardened Implementation Execution Controller into the repository's
implementation pipeline as a four-stage evidence contract:

    Planner    --implementation-plan.json (task definitions, strict schema)
       |
    Controller -- classifications, READY queue, execution contracts (fail-closed)
       |
    Executor   -- performs work WITHIN a contract (never edits prohibited scope)
       |
    Validator  -- runs declared validation commands, captures tamper-evident
                  evidence (PASS only if exit==expected and hash chain intact)
       |
    Status     -- checkpoint + pipeline-status.json (traceability handoff)

The controller implements NO product features. Blocked tasks (the current four)
are immutable unless an authoritative prerequisite changes. This runner is the
CI entry point and the documented pipeline handoff.

Usage:
  python3 tools/run-implementation-pipeline.py --dry-run
  python3 tools/run-implementation-pipeline.py --execute --allow-tool python3
  python3 tools/run-implementation-pipeline.py --status-out docs/implementation/pipeline-status.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from impl_controller.controller import Controller                  # noqa: E402
from impl_controller.manifest import load_manifest, ManifestError   # noqa: E402

DEFAULT_MANIFEST = "docs/implementation/implementation-plan.json"
DEFAULT_STATUS = "docs/implementation/pipeline-status.json"
CONTRACT_VERSION = "1.0"


def _repo_root() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return str(Path.cwd())


def _planner_gate(manifest_path: str, repo_root: str) -> dict:
    """Stage 4 (Planner) gate: load + strict-validate the plan."""
    try:
        m = load_manifest(manifest_path)
        m.validate_paths(repo_root)
        return {"stage": "planner", "status": "OK",
                "task_count": len(m.tasks), "validation": "strict"}
    except ManifestError as e:
        return {"stage": "planner", "status": "REJECTED", "error": str(e)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run-implementation-pipeline",
                                description="Implementation pipeline (Stage-5) runner.")
    p.add_argument("--manifest", default=None,
                   help="implementation-plan manifest (default: <repo-root>/%s)" % DEFAULT_MANIFEST)
    p.add_argument("--repo-root", default=None)
    p.add_argument("--state", default=".impl_controller/state.json")
    p.add_argument("--evidence", default=".impl_controller/evidence.jsonl")
    p.add_argument("--status-out", default=None,
                   help="durable pipeline-status artifact (default: <repo-root>/%s)" % DEFAULT_STATUS)
    p.add_argument("--dry-run", action="store_true",
                   help="classify + queue + contracts, modify nothing")
    p.add_argument("--execute", action="store_true",
                   help="run declared validation for the top READY task")
    p.add_argument("--allow-tool", action="append", default=None)
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    repo_root = args.repo_root or _repo_root()
    # defaults resolve against the repo root (cwd-independent), so the pipeline
    # behaves identically regardless of the invoking working directory.
    manifest_path = args.manifest or str(Path(repo_root) / DEFAULT_MANIFEST)
    status_out = args.status_out or str(Path(repo_root) / DEFAULT_STATUS)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    planner = _planner_gate(manifest_path, repo_root)
    if planner["status"] != "OK":
        payload = {"contract_version": CONTRACT_VERSION, "started_at": started,
                   "planner": planner, "result": "FAIL"}
        if not args.quiet:
            print(json.dumps(payload, indent=2))
        return 2

    try:
        ctrl = Controller(manifest_path, repo_root, args.state, args.evidence,
                          execute_allow=args.allow_tool)
        res = ctrl.run(dry_run=args.dry_run, execute=args.execute)
    except Exception as e:  # pragma: no cover - defensive
        payload = {"contract_version": CONTRACT_VERSION, "started_at": started,
                   "planner": planner, "result": "FAIL",
                   "error": f"controller: {e}"}
        Path(status_out).parent.mkdir(parents=True, exist_ok=True)
        Path(status_out).write_text(json.dumps(payload, indent=2) + "\n",
                                     encoding="utf-8")
        if not args.quiet:
            print(json.dumps(payload, indent=2))
        return 3

    status = dict(res.report)
    status["contract_version"] = CONTRACT_VERSION
    status["started_at"] = started
    status["pipeline_result"] = res.result
    status["planner"] = planner

    Path(status_out).parent.mkdir(parents=True, exist_ok=True)
    Path(status_out).write_text(json.dumps(status, indent=2) + "\n",
                                 encoding="utf-8")

    if not args.quiet:
        summary = {
            "contract_version": CONTRACT_VERSION,
            "planner": planner,
            "controller": status["stages"]["controller"],
            "executor": status["stages"]["executor"],
            "validator": status["stages"]["validator"],
            "frontier": status["frontier"],
            "graph": status["graph"],
            "pipeline_result": res.result,
            "status_out": status_out,
        }
        print(json.dumps(summary, indent=2))

    return 1 if res.result == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
