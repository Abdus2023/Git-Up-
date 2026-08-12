"""Controller orchestrator. Lock is acquired BEFORE reconstruction (C1/C2)."""

from __future__ import annotations

import json

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import REPORT_SCHEMA, VALIDATOR_IDENTITY, __version__
from .authorize import (
    authoritative_pass, closure_gaps, coverage_identity,
    criterion_attestations, expected_outputs_hold, requirement_statuses,
    task_may_pass,
)
from .checkpoint import StateStore
from .classify import classify_all
from .contract import load_contract, validate_confinement, validate_repository_binding
from .errors import ContractError, LockAcquisitionError
from .evidence import EvidenceLog
from .execute import contract_tool_set, effective_allowlist, run_validation
from .identity import contract_identity_for, provenance_context
from .lock import FileLock
from .model import TaskState
from .queue import build_ready_queue
from .repository import porcelain, repo_head, target_hashes
from .safety import is_control_artifact, is_interpreter_residue, scope_violation_paths


@dataclass
class ControllerResult:
    report: dict
    classifications: dict
    ready_queue: list
    contracts: list = field(default_factory=list)
    new_evidence: list = field(default_factory=list)
    frontier: str = "PAUSED"
    result: str = "PASS"
    errors: list = field(default_factory=list)
    drift_notes: list = field(default_factory=list)
    phase_log: list = field(default_factory=list)
    exit_code: int = 0


class Controller:
    def __init__(self, contract_path, repo_root, state_path, evidence_path,
                 execute_allow=None, probe=None):
        self.contract_path = str(contract_path)
        self.repo_root = Path(repo_root).resolve()
        self.state_path = Path(state_path)
        self.evidence_path = Path(evidence_path)
        self.lock_path = Path(state_path).with_name("controller.lock")
        # None = no CLI refinement. A list (even empty) is an explicit intersect.
        self.execute_allow = None if execute_allow is None else list(execute_allow)
        self.store = StateStore(self.state_path)
        self.log = EvidenceLog(self.evidence_path)
        self.contract = None
        self.ctx = {}
        self.probe = probe or (lambda _event: None)

    def _note(self, event: str, phase_log: list) -> None:
        phase_log.append(event)
        self.probe(event)

    def _artifact_prefixes(self) -> set:
        root = self.repo_root
        prefs = set()
        for p in (self.state_path, self.evidence_path, self.lock_path,
                  root / ".git-up"):
            try:
                rel = Path(p).resolve().relative_to(root)
                prefs.add(str(rel))
                if rel.parent != Path("."):
                    prefs.add(str(rel.parent) + "/")
            except ValueError:
                pass
        prefs.add(".git-up/")
        return prefs

    def _product_delta(self, before: set, after: set) -> list:
        """Newly dirty product paths: porcelain minus residue and control artifacts."""
        extra = self._artifact_prefixes()
        out = []
        for path in sorted(after - before):
            if is_interpreter_residue(path) or is_control_artifact(path):
                continue
            if any(path == e.rstrip("/") or path.startswith(e) for e in extra):
                continue
            out.append(path)
        return out

    def _scope_violations(self, before: set, task) -> list:
        after = porcelain(self.repo_root)
        return scope_violation_paths(
            after - before, task,
            extra_ignore_prefixes=self._artifact_prefixes(),
        )

    def _build_execution_contract(self, task, classifications, auth):
        cls = classifications.get(task.id)
        if cls is None or cls.effective_state != TaskState.READY.value:
            raise ContractError(
                f"refuse contract: task {task.id} is not READY "
                f"(state={cls.effective_state if cls else 'UNKNOWN'})"
            )
        cid = contract_identity_for(task, auth, self.ctx)
        tools = self.contract.tool_map()
        return {
            "contract_id": cid,
            "task_id": task.id,
            "title": task.title,
            "scope": task.scope,
            "provenance_context": {
                "repository_identity": self.ctx.get("repo_identity", ""),
                "head": self.ctx.get("head", ""),
                "source_identity": self.ctx.get("source_identity", ""),
                "validator": VALIDATOR_IDENTITY,
            },
            "files_allowed_to_change": list(task.implementation_targets),
            "prohibited_scope": list(task.prohibited_scope),
            "authoritative_requirements": [
                {"path": a.path, "anchor": a.anchor,
                 "requirement_id": a.requirement_id}
                for a in task.source_authority
            ],
            "requirement_refs": list(task.requirement_refs),
            "specification_refs": [
                {"path": a.path, "anchor": a.anchor} for a in task.specification_refs
            ],
            "dependencies": [
                {"ref": d.ref, "required_state": d.required_state,
                 "satisfied": d.ref in auth and d.required_state == "PASS"}
                for d in task.dependencies
            ],
            "required_tools": [
                {"id": tid, "available": bool(tools.get(tid) and tools[tid].available)}
                for tid in task.required_tools
            ],
            "allowed_tools": list(task.allowed_tools),
            "contract_tool_set": contract_tool_set(task),
            "cli_allow_tool": (
                list(self.execute_allow) if self.execute_allow is not None else None
            ),
            "effective_allowlist": effective_allowlist(task, self.execute_allow),
            "validation_commands": [
                {"id": v.id, "command": v.command,
                 "expected_exit": v.expected_exit, "purpose": v.purpose}
                for v in task.validation_commands
            ],
            "acceptance_criteria": [
                {"id": c.id, "statement": c.statement, "validator": c.validator}
                for c in task.acceptance_criteria
            ],
            "required_evidence": [
                "contract_id", "command", "stdout", "stderr", "exit_status",
                "result", "timestamp", "repository_identity", "head",
                "source_identity", "validator",
            ],
        }

    def _traceability(self, classifications, auth, dry_run):
        out = []
        for t in self.contract.tasks:
            evs = [] if dry_run else [
                r for r in self.log.verified_records() if r.get("task_id") == t.id
            ]
            cid = contract_identity_for(t, auth, self.ctx)
            c = classifications.get(t.id)
            gaps = closure_gaps(t, cid, evs, self.ctx)
            ev_refs = list(self.store.get(t.id).evidence_refs) if not dry_run else []
            out.append({
                "task_id": t.id,
                "status": c.effective_state if c else "UNKNOWN",
                "contract_id": cid,
                "closure": "CLOSED" if not gaps else "OPEN",
                "closure_gaps": gaps,
                "criterion_attestations": criterion_attestations(
                    t, cid, evs, ctx=self.ctx,
                ),
                "requirement_refs": list(t.requirement_refs),
                "specification_refs": [a.path for a in t.specification_refs],
                "source_authority": [a.path for a in t.source_authority],
                "implementation_targets": list(t.implementation_targets),
                "validation_commands": [v.id for v in t.validation_commands],
                "evidence_refs": ev_refs,
                "blocker_class": c.blocker_class if c else None,
                "blocker_reasons": c.reasons if c else [],
            })
        return out

    def _report(self, classifications, ready_queue, contracts, dry_run, execute,
                errors, drift_notes, new_evidence, executed_task, auth, phase_log,
                report_mode=""):
        new_evidence = new_evidence or []
        ev_pass = sum(1 for e in new_evidence if e.result == "PASS")
        ev_fail = sum(1 for e in new_evidence if e.result == "FAIL")
        mode = report_mode or (
            "dry-run" if dry_run else ("execute" if execute else "recover")
        )
        return {
            "schema_version": REPORT_SCHEMA,
            "controller": "git-up",
            "controller_version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "contract": self.contract.source_path,
            "repo_head": repo_head(self.repo_root),
            "provenance_context": {
                "repository_identity": self.ctx.get("repo_identity", ""),
                "head": self.ctx.get("head", ""),
                "source_identity": self.ctx.get("source_identity", ""),
                "validator": VALIDATOR_IDENTITY,
            },
            "mode": mode,
            "advisory": bool(dry_run),
            "task_count": len(self.contract.tasks),
            "graph": _graph_counts(classifications),
            "classifications": [
                classifications[t.id].to_dict() for t in self.contract.tasks
            ],
            "ready_queue": list(ready_queue),
            "execution_contracts": contracts,
            "frontier": "READY" if ready_queue else "PAUSED",
            "evidence_integrity": self.log.verify_integrity(),
            "drift_notes": list(drift_notes),
            "phase_log": list(phase_log),
            "traceability": self._traceability(classifications, auth, dry_run),
            "requirement_ledger": requirement_statuses(
                self.contract.requirements, auth
            ),
            "coverage_identity": coverage_identity(self.contract.requirements),
            "stages": {
                "contract": {"path": self.contract.source_path,
                             "task_count": len(self.contract.tasks)},
                "controller": {"classifications": len(classifications),
                               "ready": len(ready_queue),
                               "frontier": "READY" if ready_queue else "PAUSED"},
                "executor": {"attempted": executed_task is not None,
                             "task": executed_task},
                "validator": {"new_evidence": len(new_evidence),
                              "pass": ev_pass, "fail": ev_fail},
                "evidence": self.log.verify_integrity(),
            },
            "result": "FAIL" if errors else "PASS",
            "errors": list(errors),
        }

    def _write_report_locked(self, report_path, report: dict) -> None:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def _authorizing_evidence_id(self, task_id: str, task, auth) -> str:
        if task is None:
            return ""
        cid = contract_identity_for(task, auth, self.ctx)
        last = ""
        for rec in self.log.verified_records():
            if (
                rec.get("task_id") == task_id
                and rec.get("contract_id") == cid
                and EvidenceLog.is_structural_pass(rec)
            ):
                last = rec.get("evidence_id") or ""
        return last

    def _reconcile_runtime(self, auth) -> list:
        """Spec 14: persist reconstructed PASS via VALIDATING; clear crashed runtime."""
        notes = []
        by_id = self.contract.task_by_id()
        for tid in sorted(auth):
            st = self.store.get(tid)
            if st.state == TaskState.PASS.value and st.validated_pass:
                continue
            eid = self._authorizing_evidence_id(tid, by_id.get(tid), auth)
            self.store.record_reconstructed_pass(tid, eid)
            notes.append(f"reconstructed PASS via VALIDATING for {tid}")
        for tid, st in list(self.store.tasks.items()):
            if tid in auth:
                continue
            if st.in_progress or st.state in (
                TaskState.IN_PROGRESS.value,
                TaskState.VALIDATING.value,
            ):
                self.store.clear_crashed_runtime(tid)
                notes.append(f"cleared crashed runtime state for {tid}")
        return notes

    def recover(self) -> ControllerResult:
        return self.run(dry_run=False, execute=False)

    def run(self, dry_run: bool = False, execute: bool = False,
            mode: str = "", report_path=None, until_paused: bool = False) -> ControllerResult:
        errors, drift_notes, phase_log = [], [], []
        lock = None

        # Dry-run: no lock, no mutation. Mutating: lock FIRST (C1/C2).
        if not dry_run:
            self._note("acquire", phase_log)
            try:
                lock = FileLock(self.lock_path)
                lock.acquire()
            except LockAcquisitionError as e:
                return ControllerResult(
                    report={"schema_version": REPORT_SCHEMA,
                            "controller": "git-up",
                            "result": "FAIL",
                            "frontier": "PAUSED",
                            "errors": [f"concurrency lock unavailable: {e}"],
                            "mode": "execute" if execute else "recover"},
                    classifications={}, ready_queue=[], frontier="PAUSED",
                    result="FAIL", errors=[str(e)], phase_log=phase_log,
                    exit_code=4,
                )
            self._note("acquired", phase_log)

        try:
            return self._run_locked(
                dry_run, execute, errors, drift_notes, phase_log,
                mode=mode, report_path=report_path,
                until_paused=until_paused,
            )
        finally:
            if lock is not None:
                self._note("release", phase_log)
                lock.release()

    def _run_locked(self, dry_run, execute, errors, drift_notes, phase_log,
                    mode="", report_path=None, until_paused=False):
        self.contract = load_contract(self.contract_path)
        confine = validate_confinement(self.contract, self.repo_root)
        if confine:
            raise ContractError("path confinement: " + "; ".join(confine))
        bind = validate_repository_binding(self.contract, self.repo_root)
        if bind:
            raise ContractError("repository binding: " + "; ".join(bind))

        self._note("reconstruct", phase_log)
        self.ctx = provenance_context(
            self.repo_root, self.contract, create_identity=not dry_run
        )
        if not dry_run and not self.ctx.get("head"):
            errors.append("empty HEAD; mutating operations require a git repository")
            report = {
                "schema_version": REPORT_SCHEMA,
                "controller": "git-up",
                "mode": "execute" if execute else "recover",
                "result": "FAIL",
                "errors": list(errors),
                "frontier": "PAUSED",
            }
            return ControllerResult(
                report=report, classifications={}, ready_queue=[],
                frontier="PAUSED", result="FAIL", errors=errors,
                phase_log=phase_log, exit_code=1,
            )

        auth = authoritative_pass(
            self.contract, self.log, self.ctx, self.repo_root
        )

        if not dry_run:
            self._note("checkpoint_load", phase_log)
            self.store.load()
            demoted = self.store.demote_unbacked_pass(auth)
            if demoted:
                drift_notes.append(
                    f"demoted checkpoint PASS lacking evidence: {demoted}"
                )
            for note in self._reconcile_runtime(auth):
                drift_notes.append(note)
            head = repo_head(self.repo_root)
            if self.store.repo_head and self.store.repo_head != head:
                drift_notes.append(
                    f"repository HEAD changed since last checkpoint "
                    f"({self.store.repo_head[:12]} -> {head[:12]})"
                )

        self._note("classify", phase_log)
        tools = self.contract.tool_map()
        req_ids = {r.id for r in self.contract.requirements}
        sources = list(self.contract.authority_sources or [])
        classifications = classify_all(
            self.contract.tasks, tools, self.repo_root, auth,
            requirement_ids=req_ids,
            authority_sources=sources,
        )
        ready_queue = build_ready_queue(self.contract.tasks, classifications)
        by_id = self.contract.task_by_id()
        contracts = []
        for tid in ready_queue:
            contracts.append(
                self._build_execution_contract(by_id[tid], classifications, auth)
            )

        new_evidence = []
        executed_task = None
        frontier = "READY" if ready_queue else "PAUSED"

        if execute and not dry_run and ready_queue:
            budget = len(self.contract.tasks) + 1
            while ready_queue and budget > 0:
                budget -= 1
                tid = ready_queue[0]
                executed_task = tid
                task = by_id[tid]
                allow = effective_allowlist(task, self.execute_allow)
                exec_cid = contract_identity_for(task, auth, self.ctx)
                scope_before = porcelain(self.repo_root)
                st = self.store.get(tid)
                if st.state in (
                    TaskState.DISCOVERED.value,
                    TaskState.BLOCKED.value,
                    TaskState.FAIL.value,
                ):
                    self.store.transition(tid, TaskState.READY.value)
                self.store.begin(tid)
                failed = False
                last_eid = ""
                for vc in task.validation_commands:
                    if command_identity_skip(self.log, task.id, exec_cid, vc):
                        continue
                    rec = run_validation(
                        task.id, vc, allow, exec_cid, self.ctx,
                        self.repo_root, self.contract.timeout_seconds,
                    )
                    violations = self._scope_violations(scope_before, task)
                    if violations:
                        rec.result = "FAIL"
                        rec.failure_class = "INTEGRATION"
                        extra = f"scope violation: {violations}"
                        rec.notes = (rec.notes + " | " if rec.notes else "") + extra
                    post = porcelain(self.repo_root)
                    rec.observed_delta = self._product_delta(scope_before, post)
                    rec.target_hashes = target_hashes(
                        task.implementation_targets, self.repo_root
                    )
                    scope_before = post
                    new_evidence.append(rec)
                    self.log.append(rec)
                    last_eid = rec.evidence_id
                    s = self.store.get(tid)
                    if rec.evidence_id not in s.evidence_refs:
                        s.evidence_refs.append(rec.evidence_id)
                    if rec.result != "PASS":
                        self.store.finish_fail(tid, rec.evidence_id)
                        why = "scope violation" if violations else f"exit {rec.exit_status}"
                        errors.append(f"validation FAIL for {tid}: {vc.id} ({why})")
                        failed = True
                        break
                if not failed:
                    self.store.enter_validating(tid)
                    auth = authoritative_pass(
                        self.contract, self.log, self.ctx, self.repo_root
                    )
                    evs = [r for r in self.log.verified_records() if r.get("task_id") == tid]
                    cid = contract_identity_for(task, auth, self.ctx)
                    if task_may_pass(task, cid, evs, auth, self.ctx, self.repo_root):
                        self.store.finish_pass(tid, last_eid)
                    else:
                        self.store.finish_fail(tid, last_eid)
                        if not expected_outputs_hold(task, self.repo_root):
                            errors.append(
                                f"result-integrity FAIL for {tid}: declared "
                                "expected_outputs not satisfied"
                            )
                        else:
                            errors.append(
                                f"authorization predicate FAIL for {tid}"
                            )
                        failed = True

                auth = authoritative_pass(
                    self.contract, self.log, self.ctx, self.repo_root
                )
                classifications = classify_all(
                    self.contract.tasks, tools, self.repo_root, auth,
                    requirement_ids=req_ids,
                    authority_sources=sources,
                )
                ready_queue = build_ready_queue(self.contract.tasks, classifications)
                contracts = [
                    self._build_execution_contract(by_id[x], classifications, auth)
                    for x in ready_queue
                ]
                frontier = "READY" if ready_queue else "PAUSED"
                if failed or not until_paused:
                    break

        if not dry_run:
            self._note("checkpoint_save", phase_log)
            self.store.save(repo_head(self.repo_root))

        report = self._report(
            classifications, ready_queue, contracts, dry_run, execute,
            errors, drift_notes, new_evidence, executed_task, auth, phase_log,
            report_mode=mode,
        )
        result = "FAIL" if (errors or any(e.result == "FAIL" for e in new_evidence)) else "PASS"
        report["result"] = result
        if report_path and not dry_run:
            self._write_report_locked(report_path, report)
        return ControllerResult(
            report=report, classifications=classifications,
            ready_queue=ready_queue, contracts=contracts,
            new_evidence=[e.to_dict() for e in new_evidence],
            frontier=frontier, result=result, errors=errors,
            drift_notes=drift_notes, phase_log=phase_log,
            exit_code=1 if result == "FAIL" else 0,
        )


def command_identity_skip(log, task_id, contract_id, vc) -> bool:
    from .identity import command_identity
    return command_identity(vc) in log.pass_command_ids(task_id, contract_id)


def _graph_counts(classifications) -> dict:
    counts = {s.value: 0 for s in TaskState}
    for c in classifications.values():
        counts[c.effective_state] = counts.get(c.effective_state, 0) + 1
    return counts
