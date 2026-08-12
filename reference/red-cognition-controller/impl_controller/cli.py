"""Command-line interface for the Implementation Execution Controller."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .controller import Controller
from .manifest import ManifestError


def _default_repo_root() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return str(Path.cwd())


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="impl-controller",
        description="Implementation Execution Controller — plan -> fail-closed "
                    "task queue. Implements NO product features.")
    p.add_argument("--manifest", default="docs/implementation/implementation-plan.json",
                   help="path to implementation-plan manifest (JSON)")
    p.add_argument("--repo-root", default=None,
                   help="repository root (default: git toplevel)")
    p.add_argument("--state", default=".impl_controller/state.json",
                   help="checkpoint state file")
    p.add_argument("--evidence", default=".impl_controller/evidence.jsonl",
                   help="append-only evidence log file")
    p.add_argument("--report", default=None,
                   help="write the JSON report to this path as well as stdout")
    p.add_argument("--dry-run", action="store_true",
                   help="classify + queue + contracts, modify nothing")
    p.add_argument("--execute", action="store_true",
                   help="run declared validation for the top READY task and "
                        "record evidence (never edits product files)")
    p.add_argument("--allow-tool", action="append", default=None,
                   help="allowed command prefix for --execute (repeatable)")
    p.add_argument("--self-test", action="store_true",
                   help="run the controller's unittest suite and exit")
    p.add_argument("--quiet", action="store_true",
                   help="suppress stdout report (still writes --report)")
    return p


def _run_self_test() -> int:
    import unittest
    loader = unittest.TestLoader()
    # tests live alongside this package
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))  # so `tests` is importable
    suite = loader.discover(start_dir=str(here / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    if args.self_test:
        return _run_self_test()

    repo_root = args.repo_root or _default_repo_root()
    try:
        ctrl = Controller(
            manifest_path=args.manifest, repo_root=repo_root,
            state_path=args.state, evidence_path=args.evidence,
            execute_allow=args.allow_tool)
        res = ctrl.run(dry_run=args.dry_run, execute=args.execute)
    except ManifestError as e:
        print(json.dumps({"result": "FAIL", "errors": [f"manifest: {e}"]},
                         indent=2))
        return 2
    except Exception as e:  # pragma: no cover - defensive top-level guard
        print(json.dumps({"result": "FAIL", "errors": [f"controller: {e}"]},
                         indent=2))
        return 3

    out = dict(res.report)
    out["result"] = res.result
    out["errors"] = res.errors
    if not args.quiet:
        print(json.dumps(out, indent=2))
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(out, indent=2) + "\n",
                                     encoding="utf-8")
    # exit code: FAIL on validation errors; otherwise success (PAUSED is success)
    return 1 if res.result == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
