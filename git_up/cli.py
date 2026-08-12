"""git-up CLI (spec 17)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .controller import Controller
from .errors import ContractError, GitUpError
from .repository import git_toplevel


_COMMANDS = (
    "inspect", "reconstruct", "plan", "classify", "ready",
    "run", "verify", "evidence", "status", "recover", "audit", "trace",
    "contract",
)


def _flag_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="git-up",
        description="Git-Up! — contract-driven implementation controller.",
        epilog="commands: inspect reconstruct plan classify ready run "
               "verify evidence status recover audit trace | contract validate",
    )
    p.add_argument("--version", action="version", version=f"git-up {__version__}")
    p.add_argument("--contract", default="git-up.contract.json",
                   help="implementation contract (JSON)")
    p.add_argument("--repo-root", default=None)
    p.add_argument("--state", default=".git-up/state.json")
    p.add_argument("--evidence", default=".git-up/evidence.jsonl")
    p.add_argument("--report", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--allow-tool", action="append", default=None)
    return p


def _parse(argv):
    """Flags may appear before or after the subcommand."""
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = _flag_parser()
    args, unknown = parser.parse_known_args(raw)
    cmd = None
    contract_cmd = None
    leftover = []
    i = 0
    while i < len(unknown):
        tok = unknown[i]
        if tok in _COMMANDS and cmd is None:
            cmd = tok
            if cmd == "contract" and i + 1 < len(unknown) and unknown[i + 1] == "validate":
                contract_cmd = "validate"
                i += 2
                continue
            i += 1
            continue
        leftover.append(tok)
        i += 1
    if leftover:
        parser.error("unrecognized arguments: " + " ".join(leftover))
    args.command = cmd
    args.contract_cmd = contract_cmd
    return parser, args


def _controller(args) -> Controller:
    repo = args.repo_root or str(git_toplevel())
    return Controller(
        contract_path=args.contract,
        repo_root=repo,
        state_path=args.state,
        evidence_path=args.evidence,
        execute_allow=args.allow_tool,
    )


def _emit(args, payload, code: int) -> int:
    text = json.dumps(payload, indent=2) + "\n"
    if not args.quiet:
        sys.stdout.write(text)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
    return code


def main(argv=None) -> int:
    _parser, args = _parse(argv)
    cmd = args.command
    if cmd is None:
        _parser.print_help()
        return 2
    if cmd == "contract":
        if args.contract_cmd != "validate":
            print(json.dumps({
                "result": "FAIL",
                "errors": ["usage: git-up contract validate"],
            }, indent=2))
            return 2
        cmd = "contract-validate"

    dry_default = cmd in {
        "inspect", "plan", "classify", "ready", "contract-validate",
        "evidence", "status", "audit", "trace",
    }
    dry_run = bool(args.dry_run or dry_default)
    if cmd == "reconstruct" and not args.dry_run:
        # reconstruct without --dry-run writes a checkpoint (spec 17)
        dry_run = False
    execute = cmd == "run" and not dry_run
    if cmd == "run" and args.dry_run:
        execute = False
        dry_run = True

    try:
        ctrl = _controller(args)
        if cmd == "evidence":
            payload = {
                "schema_version": "git-up.report.v1",
                "mode": "dry-run",
                "advisory": True,
                "integrity": ctrl.log.verify_integrity(),
                "trusted": ctrl.log.verified_records(),
                "result": "PASS",
                "errors": [],
            }
            return _emit(args, payload, 0)

        res = ctrl.run(dry_run=dry_run, execute=execute)
    except ContractError as e:
        return _emit(args, {"result": "FAIL", "errors": [f"contract: {e}"]}, 2)
    except GitUpError as e:
        return _emit(args, {"result": "FAIL", "errors": [f"git-up: {e}"]}, 3)
    except Exception as e:  # pragma: no cover
        return _emit(args, {"result": "FAIL", "errors": [f"controller: {e}"]}, 3)

    out = dict(res.report)
    out["result"] = res.result
    out["errors"] = res.errors
    if cmd == "ready":
        out = {
            "schema_version": "git-up.report.v1",
            "mode": "dry-run",
            "advisory": True,
            "ready_queue": res.ready_queue,
            "result": res.result,
            "errors": res.errors,
        }
    if cmd == "classify":
        out = {
            "schema_version": "git-up.report.v1",
            "mode": "dry-run",
            "advisory": True,
            "classifications": res.report.get("classifications"),
            "graph": res.report.get("graph"),
            "result": res.result,
            "errors": res.errors,
        }
    if cmd == "trace":
        out = {
            "schema_version": "git-up.report.v1",
            "mode": res.report.get("mode"),
            "advisory": res.report.get("advisory"),
            "traceability": res.report.get("traceability"),
            "requirement_ledger": res.report.get("requirement_ledger"),
            "result": res.result,
            "errors": res.errors,
        }
    if cmd == "audit":
        out = {
            "schema_version": "git-up.report.v1",
            "mode": "dry-run",
            "advisory": True,
            "evidence_integrity": res.report.get("evidence_integrity"),
            "drift_notes": res.drift_notes,
            "phase_log": res.phase_log,
            "result": res.result,
            "errors": res.errors,
        }
    if cmd == "status":
        out = {
            "schema_version": "git-up.report.v1",
            "mode": res.report.get("mode"),
            "advisory": res.report.get("advisory"),
            "frontier": res.frontier,
            "graph": res.report.get("graph"),
            "drift_notes": res.drift_notes,
            "result": res.result,
            "errors": res.errors,
        }

    code = res.exit_code
    if code == 0 and res.result == "FAIL":
        code = 1
    return _emit(args, out, code)


if __name__ == "__main__":
    sys.exit(main())
