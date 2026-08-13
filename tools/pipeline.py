#!/usr/bin/env python3
"""Dry-run pipeline: optional emit → validate → classify.

This is Git-Up! tooling, not the controller. It never acquires a lease,
never executes validators, and never authorizes PASS (ADR-0018).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from git_up.adapter import emit_contract_file  # noqa: E402
from git_up.contract import load_contract, validate_confinement  # noqa: E402
from git_up.controller import Controller  # noqa: E402
from git_up.errors import ContractError  # noqa: E402
from git_up.repository import git_toplevel  # noqa: E402


def run_pipeline(plan=None, contract=None, repo_root=None, out=None) -> dict:
    repo = str(Path(repo_root or git_toplevel()).resolve())
    emitted = None
    if plan:
        if not out:
            out = str(Path(repo) / ".git-up-pipeline.contract.json")
        emitted = emit_contract_file(plan, out)
        contract = out
    if not contract:
        raise ContractError("pipeline requires --plan or --contract")
    loaded = load_contract(contract)
    confine = validate_confinement(loaded, repo)
    ctrl = Controller(
        contract_path=contract,
        repo_root=repo,
        state_path=str(Path(repo) / ".git-up" / "state.json"),
        evidence_path=str(Path(repo) / ".git-up" / "evidence.jsonl"),
    )
    res = ctrl.run(dry_run=True, execute=False)
    return {
        "advisory": True,
        "emitted": bool(emitted),
        "contract": str(Path(contract).resolve()),
        "confinement_errors": confine,
        "frontier": res.frontier,
        "classifications": res.report.get("classifications"),
        "ready_queue": res.ready_queue,
        "result": "FAIL" if confine or res.result == "FAIL" else "PASS",
        "errors": list(res.errors) + [f"path confinement: {e}" for e in confine],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", default=None)
    p.add_argument("--contract", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--repo-root", default=None)
    args = p.parse_args(argv)
    try:
        payload = run_pipeline(
            plan=args.plan, contract=args.contract,
            repo_root=args.repo_root, out=args.out,
        )
    except ContractError as e:
        print(json.dumps({"result": "FAIL", "errors": [str(e)]}, indent=2))
        return 2
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("result") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
