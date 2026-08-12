"""git-up CLI (spec 17)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import REPORT_SCHEMA, __version__
from .authorize import predicate_report
from .contract import load_contract, validate_confinement
from .controller import Controller
from .errors import ContractError, GitUpError
from .model import ALLOWED_TRANSITIONS, TaskState
from .repository import git_toplevel, porcelain, read_repo_identity, repo_head


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
               "verify evidence status recover audit trace | "
               "contract validate | contract emit",
    )
    p.add_argument("--version", action="version", version=f"git-up {__version__}")
    p.add_argument("--contract", default="git-up.contract.json",
                   help="implementation contract (JSON)")
    p.add_argument("--repo-root", default=None)
    p.add_argument("--state", default=".git-up/state.json")
    p.add_argument("--evidence", default=".git-up/evidence.jsonl")
    p.add_argument("--report", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--write", action="store_true",
                   help="reconstruct: persist checkpoint (spec 17)")
    p.add_argument("--until-paused", action="store_true",
                   help="run: drain the READY queue under one lease (ADR-0013)")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--allow-tool", action="append", default=None)
    p.add_argument("--from", dest="from_path", default=None,
                   help="contract emit: source plan path")
    p.add_argument("--out", dest="out_path", default=None,
                   help="contract emit: write contract JSON here")
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
            if cmd == "contract" and i + 1 < len(unknown) and unknown[i + 1] in (
                "validate", "emit",
            ):
                contract_cmd = unknown[i + 1]
                i += 2
                continue
            i += 1
            continue
        leftover.append(tok)
        i += 1
    args.command = cmd
    args.contract_cmd = contract_cmd
    args.leftover = leftover
    return parser, args


def _resolve_under_repo(repo: Path, p) -> Path:
    path = Path(p)
    return path if path.is_absolute() else repo / path


def _controller(args) -> Controller:
    repo = Path(args.repo_root or git_toplevel()).resolve()
    return Controller(
        contract_path=args.contract,
        repo_root=str(repo),
        state_path=str(_resolve_under_repo(repo, args.state)),
        evidence_path=str(_resolve_under_repo(repo, args.evidence)),
        execute_allow=args.allow_tool,
    )


def _emit(args, payload, code: int) -> int:
    text = json.dumps(payload, indent=2) + "\n"
    if not getattr(args, "quiet", False):
        sys.stdout.write(text)
    if args.report and code != 2:
        # dry-run writes outside .git-up/ only; mutating reports are written
        # under the lease by the controller when the path is inside .git-up/.
        repo = Path(args.repo_root or git_toplevel()).resolve()
        dest = Path(args.report)
        dest = dest if dest.is_absolute() else Path.cwd() / dest
        try:
            dest.resolve().relative_to(repo / ".git-up")
            inside = True
        except ValueError:
            inside = False
        if inside:
            return code
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return code


def _envelope(**extra) -> dict:
    out = {
        "schema_version": REPORT_SCHEMA,
        "controller": "git-up",
        "controller_version": __version__,
        "result": extra.pop("result", "PASS"),
        "errors": extra.pop("errors", []),
        "drift_notes": extra.pop("drift_notes", []),
    }
    out.update(extra)
    return out


def _report_inside_control_plane(args) -> bool:
    if not args.report:
        return False
    repo = Path(args.repo_root or git_toplevel()).resolve()
    dest = Path(args.report)
    dest = dest if dest.is_absolute() else Path.cwd() / dest
    try:
        dest.resolve().relative_to(repo / ".git-up")
        return True
    except ValueError:
        return False


def _expected_evidence(res) -> list:
    out = []
    by_cls = {c["task_id"]: c for c in res.report.get("classifications") or []}
    for c in res.contracts:
        tid = c["task_id"]
        cls = by_cls.get(tid) or {}
        out.append({
            "task_id": tid,
            "contract_id": c.get("contract_id"),
            "if_executed": cls.get("effective_state") == "READY",
            "required_fields": list(c.get("required_evidence") or []),
            "commands": [v["id"] for v in c.get("validation_commands") or []],
        })
    return out


def _audit_notes(res, args) -> list:
    notes = list(res.drift_notes)
    repo = Path(args.repo_root or git_toplevel()).resolve()
    state_path = _resolve_under_repo(repo, args.state)
    if state_path.is_file():
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            notes.append("checkpoint is not valid JSON (treated as empty on load)")
            raw = {}
        for rec in raw.get("tasks") or []:
            st = rec.get("state")
            if st not in {s.value for s in TaskState}:
                notes.append(f"unknown stored state {st!r} for {rec.get('task_id')}")
            if rec.get("validated_pass") and st != TaskState.PASS.value:
                notes.append(
                    f"checkpoint validated_pass without PASS state for {rec.get('task_id')}"
                )
            if st == TaskState.PASS.value and rec.get("task_id") not in {
                c["task_id"] for c in res.report.get("classifications") or []
                if c.get("effective_state") == "PASS"
            }:
                notes.append(
                    f"checkpoint PASS not in reconstructed set: {rec.get('task_id')}"
                )
            if st in ALLOWED_TRANSITIONS and rec.get("validated_pass") and st == "READY":
                notes.append(f"illegal READY+validated_pass for {rec.get('task_id')}")
    integ = res.report.get("evidence_integrity") or {}
    if integ and not integ.get("intact", True):
        notes.append(f"evidence chain broken at {integ.get('broken_at')}")
    return notes


def main(argv=None) -> int:
    _parser, args = _parse(argv)
    cmd = args.command
    if getattr(args, "leftover", None):
        return _emit(args, _envelope(
            result="FAIL",
            errors=[f"unknown command or arguments: {args.leftover}"],
            mode="dry-run",
        ), 2)
    if cmd is None:
        _parser.print_help()
        return 2
    if cmd == "contract":
        if args.contract_cmd == "validate":
            cmd = "contract-validate"
        elif args.contract_cmd == "emit":
            cmd = "contract-emit"
        else:
            return _emit(args, _envelope(
                result="FAIL",
                errors=["usage: git-up contract validate | git-up contract emit --from PLAN"],
            ), 2)

    dry_default = cmd in {
        "inspect", "plan", "classify", "ready", "contract-validate",
        "evidence", "status", "audit", "trace",
    }
    dry_run = bool(args.dry_run or dry_default)
    if cmd == "reconstruct":
        dry_run = not bool(args.write or (not args.dry_run and args.write))
        if args.write:
            dry_run = False
        else:
            dry_run = True
    if cmd == "verify":
        dry_run = bool(args.dry_run)
    execute = cmd == "run" and not dry_run
    if cmd == "run" and args.dry_run:
        execute = False
        dry_run = True

    if dry_run and _report_inside_control_plane(args):
        return _emit(args, _envelope(
            result="FAIL",
            errors=["--report inside .git-up/ requires a lease; refused in dry-run"],
            mode="dry-run",
        ), 2)

    mode = {
        "inspect": "dry-run",
        "plan": "plan",
        "classify": "dry-run",
        "ready": "dry-run",
        "contract-validate": "dry-run",
        "evidence": "dry-run",
        "status": "dry-run",
        "audit": "dry-run",
        "trace": "dry-run",
        "reconstruct": "recover" if not dry_run else "dry-run",
        "recover": "recover",
        "verify": "verify",
        "run": "dry-run" if dry_run else "execute",
    }.get(cmd, "dry-run")

    try:
        if cmd == "contract-emit":
            from .adapter import emit_contract_file
            if not args.from_path:
                return _emit(args, _envelope(
                    result="FAIL",
                    errors=["usage: git-up contract emit --from PLAN [--out CONTRACT]"],
                ), 2)
            doc = emit_contract_file(args.from_path, args.out_path)
            payload = _envelope(
                mode="dry-run",
                advisory=True,
                frontier="PAUSED",
                producer="git-up.adapter.plan",
                out=args.out_path,
                task_count=len(doc.get("tasks") or []),
                contract=doc,
            )
            return _emit(args, payload, 0)

        if cmd == "contract-validate":
            repo = args.repo_root or str(git_toplevel())
            contract = load_contract(args.contract)
            confine = validate_confinement(contract, repo)
            payload = _envelope(
                mode="dry-run",
                advisory=True,
                frontier="PAUSED",
                contract=str(Path(args.contract).resolve()),
                schema_version_contract=contract.schema_version,
                task_count=len(contract.tasks),
                confinement_errors=confine,
                result="FAIL" if confine else "PASS",
                errors=[f"path confinement: {e}" for e in confine],
            )
            return _emit(args, payload, 2 if confine else 0)

        ctrl = _controller(args)
        if cmd == "evidence":
            payload = _envelope(
                mode="dry-run",
                advisory=True,
                frontier="PAUSED",
                integrity=ctrl.log.verify_integrity(),
                trusted=ctrl.log.verified_records(),
            )
            return _emit(args, payload, 0)

        locked_report = args.report if (args.report and not dry_run
                                        and _report_inside_control_plane(args)) else None
        res = ctrl.run(dry_run=dry_run, execute=execute, mode=mode,
                       report_path=locked_report,
                       until_paused=bool(getattr(args, "until_paused", False)
                                         and execute))
    except ContractError as e:
        return _emit(args, _envelope(result="FAIL", errors=[f"contract: {e}"]), 2)
    except GitUpError as e:
        return _emit(args, _envelope(result="FAIL", errors=[f"git-up: {e}"]), 3)
    except Exception as e:  # pragma: no cover
        return _emit(args, _envelope(result="FAIL", errors=[f"controller: {e}"]), 3)

    repo = Path(args.repo_root or git_toplevel())
    out = dict(res.report)
    out["result"] = res.result
    out["errors"] = res.errors

    if cmd == "inspect":
        out = _envelope(
            mode="dry-run",
            advisory=True,
            frontier=res.frontier,
            contract=str(Path(args.contract).resolve()),
            schema_version_contract=getattr(ctrl.contract, "schema_version", ""),
            task_ids=[t.id for t in (ctrl.contract.tasks if ctrl.contract else [])],
            repository_identity=read_repo_identity(repo),
            head=repo_head(repo),
            dirty_paths=sorted(porcelain(repo)),
            evidence_integrity=res.report.get("evidence_integrity"),
            result=res.result,
            errors=res.errors,
        )
    elif cmd == "ready":
        out = _envelope(
            mode="dry-run", advisory=True, frontier=res.frontier,
            ready_queue=res.ready_queue, result=res.result, errors=res.errors,
        )
    elif cmd == "classify":
        out = _envelope(
            mode="dry-run", advisory=True, frontier=res.frontier,
            classifications=res.report.get("classifications"),
            graph=res.report.get("graph"),
            result=res.result, errors=res.errors,
        )
    elif cmd == "plan":
        out = _envelope(
            mode="plan", advisory=True, frontier=res.frontier,
            classifications=res.report.get("classifications"),
            ready_queue=res.ready_queue,
            execution_contracts=res.contracts,
            expected_evidence=_expected_evidence(res),
            result=res.result, errors=res.errors,
        )
    elif cmd == "reconstruct":
        pass_ids = [
            c["task_id"] for c in res.report.get("classifications") or []
            if c.get("effective_state") == "PASS"
        ]
        out = _envelope(
            mode=mode, advisory=dry_run, frontier=res.frontier,
            authoritative_pass=pass_ids,
            graph=res.report.get("graph"),
            drift_notes=res.drift_notes,
            result=res.result, errors=res.errors,
        )
    elif cmd == "trace":
        out = _envelope(
            mode=res.report.get("mode"), advisory=res.report.get("advisory"),
            frontier=res.frontier,
            traceability=res.report.get("traceability"),
            requirement_ledger=res.report.get("requirement_ledger"),
            result=res.result, errors=res.errors,
        )
    elif cmd == "audit":
        notes = _audit_notes(res, args)
        out = _envelope(
            mode="dry-run", advisory=True, frontier=res.frontier,
            evidence_integrity=res.report.get("evidence_integrity"),
            drift_notes=notes,
            phase_log=res.phase_log,
            result="FAIL" if any("broken" in n or "illegal" in n or "unknown" in n
                                 for n in notes) else res.result,
            errors=res.errors,
        )
    elif cmd == "status":
        out = _envelope(
            mode=res.report.get("mode"), advisory=res.report.get("advisory"),
            frontier=res.frontier, graph=res.report.get("graph"),
            drift_notes=res.drift_notes, result=res.result, errors=res.errors,
        )
    elif cmd == "verify":
        pass_ids = [
            c["task_id"] for c in res.report.get("classifications") or []
            if c.get("effective_state") == "PASS"
        ]
        out = _envelope(
            mode="verify",
            advisory=dry_run,
            frontier=res.frontier,
            authoritative_pass=pass_ids,
            predicate=predicate_report(
                ctrl.contract, ctrl.log, ctrl.ctx, repo
            ),
            classifications=res.report.get("classifications"),
            drift_notes=res.drift_notes,
            result=res.result,
            errors=res.errors,
        )

    code = res.exit_code
    if code == 0 and out.get("result") == "FAIL":
        code = 1
    return _emit(args, out, code)


if __name__ == "__main__":
    sys.exit(main())
