"""Controller orchestrator: plan -> graph -> classify -> queue -> contract.

The controller implements NO product features. In ``dry_run`` mode it writes
nothing (no lock, read-only). In normal/execute mode it acquires an exclusive
repository-local lease, persists a checkpoint, and may run declared validation
commands for the highest-priority READY task — but it NEVER edits
implementation targets (that is the execution agent's role, within the emitted
contract).

PASS is evidence-authoritative: a task is PASS only if chain-verified PASS
evidence exists AND the task definition (acceptance criteria + validation
commands) is intact. A checkpoint that claims PASS without such evidence is
demoted (never trusted blindly).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .manifest import Manifest, load_manifest, ManifestError
from .model import TaskState
from .engine import classify_all
from .queue import build_ready_queue
from .contract import build_execution_contract
from .evidence import EvidenceLog, EvidenceRecord, classify_exit
from .safety import validate_command, target_hashes, SafetyError
from .locking import FileLock, LockAcquisitionError
from .checkpoint import StateStore
from .provenance import (
    provenance_context, contract_identity_for, closure_gaps,
    default_context, command_identity, criterion_attestations,
    coverage_identity, requirement_statuses, VALIDATOR_IDENTITY,
)


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


class Controller:
    def __init__(self, manifest_path, repo_root, state_path, evidence_path,
                 execute_allow=None):
        self.manifest_path = str(manifest_path)
        self.repo_root = Path(repo_root).resolve()
        self.state_path = Path(state_path)
        self.evidence_path = Path(evidence_path)
        self.lock_path = Path(state_path).with_name("controller.lock")
        self.execute_allow = list(execute_allow or [])
        self.manifest: Optional[Manifest] = None
        self.store = StateStore(self.state_path)
        self.log = EvidenceLog(self.evidence_path)
        self.ctx: dict = default_context()

    # ---- helpers -----------------------------------------------------------
    def _repo_head(self) -> str:
        try:
            out = subprocess.run(
                ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10)
            if out.returncode == 0:
                return out.stdout.strip()
        except Exception:
            pass
        return ""

    def _graph_counts(self, classifications: dict) -> dict:
        counts = {s.value: 0 for s in TaskState}
        for c in classifications.values():
            counts[c.effective_state] = counts.get(c.effective_state, 0) + 1
        return counts

    # ---- write-scope guard (attack 9) -------------------------------------
    def _git_porcelain(self) -> set:
        """Best-effort set of changed paths (tracked mods + untracked)."""
        try:
            out = subprocess.run(
                ["git", "-C", str(self.repo_root), "status", "--porcelain"],
                capture_output=True, text=True, timeout=15)
            if out.returncode != 0:
                return set()
        except Exception:
            return set()
        paths = set()
        for line in out.stdout.splitlines():
            if len(line) > 3:
                paths.add(line[3:].strip().strip('"'))
        return paths

    def _controller_artifact_prefixes(self) -> set:
        """Repo-relative prefixes to exclude from the scope guard (the
        controller's own state/evidence/lock artifacts)."""
        root = self.repo_root.resolve()
        prefs = set()
        for p in (self.state_path, self.evidence_path, self.lock_path):
            try:
                rel = Path(p).resolve().relative_to(root)
                prefs.add(str(rel))
                if rel.parent != Path("."):
                    prefs.add(str(rel.parent) + "/")
            except ValueError:
                pass  # outside repo -> not seen by porcelain anyway
        return prefs

    def _scope_violations(self, before: set, task) -> list:
        after = self._git_porcelain()
        new = after - before
        excl = self._controller_artifact_prefixes()
        targets = [t.rstrip("/") for t in task.implementation_targets]

        def within(p):
            if any(p == e or p.startswith(e) for e in excl):
                return True
            for t in targets:
                if p == t or p.startswith(t + "/"):
                    return True
            return False

        return sorted(p for p in new if not within(p))

    def _authoritative_pass(self) -> set:
        """Provenance-authoritative PASS set (fail-closed fixpoint).

        A task is PASS only if ALL hold:
          * chain-verified, structurally-valid PASS evidence exists for it;
          * the task definition is intact (acceptance_criteria + validation_commands);
          * authority documents exist/readable inside the repo;
          * every PASS dependency is itself authoritatively PASS;
          * an evidence record is bound to the task's CURRENT contract_id
            (cryptographically binding repo identity, HEAD, manifest identity,
            task inputs, dependency state, tools, commands, targets);
          * the traceability closure has no gaps.
        A successful command alone is never sufficient.
        """
        from .engine import authority_problems
        ctx = self.ctx
        by_id = {t.task_id: t for t in self.manifest.tasks}
        pass_ev = {}
        for rec in self.log.verified_records():
            if rec.get("result") == "PASS" and EvidenceLog._is_valid_pass(rec):
                pass_ev.setdefault(rec.get("task_id"), []).append(rec)

        auth = set()
        changed = True
        while changed:
            changed = False
            for tid, evs in pass_ev.items():
                if tid in auth:
                    continue
                task = by_id.get(tid)
                if task is None:
                    continue
                if not (task.acceptance_criteria and task.validation_commands):
                    continue
                if authority_problems(task, self.repo_root):
                    continue
                if not all(d.ref in auth for d in task.dependency_refs
                           if d.required_state == "PASS"):
                    continue
                cid = contract_identity_for(task, auth, ctx)
                if closure_gaps(task, cid, evs, ctx):
                    continue
                # Result integrity: a successful exit alone is never sufficient.
                # The validated target STATE must still hold, and any declared
                # required outputs must currently exist with their declared hashes.
                if task.implementation_targets:
                    cur_th = target_hashes(task.implementation_targets, self.repo_root)
                    if not any(e.get("target_hashes") == cur_th
                               for e in evs
                               if e.get("contract_id") == cid
                               and e.get("result") == "PASS"):
                        continue
                if task.expected_outputs and not all(
                        target_hashes([eo.path], self.repo_root).get(eo.path) == eo.sha256
                        for eo in task.expected_outputs):
                    continue
                auth.add(tid)
                changed = True
        return auth

    def _reconcile_checkpoint_pass(self, authoritative: set) -> list:
        """Demote any checkpoint-claimed PASS not backed by current evidence."""
        demoted = []
        for tid, st in self.store.tasks.items():
            if st.validated_pass and tid not in authoritative:
                st.validated_pass = False
                st.state = TaskState.DISCOVERED.value  # force reclassification
                st.in_progress = False
                demoted.append(tid)
        return demoted

    def recover(self) -> "ControllerResult":
        """Idempotent recovery entry.

        Recomputes authoritative state purely from the evidence log + provenance
        (manifest, repository identity, HEAD), demotes any checkpoint claim not
        backed by valid evidence, and persists a fresh atomic checkpoint. It
        executes nothing and duplicates no evidence. Safe to call repeatedly.
        """
        return self.run(dry_run=False, execute=False)

    # ---- main entry --------------------------------------------------------
    def run(self, dry_run: bool = False, execute: bool = False) -> ControllerResult:
        errors = []
        drift_notes = []
        self.manifest = load_manifest(self.manifest_path)
        self.manifest.validate_paths(self.repo_root)            # fail closed on escape
        self.ctx = provenance_context(self.repo_root, self.manifest)

        auth_pass = self._authoritative_pass()
        lock = None
        if not dry_run:
            self.store.load()
            demoted = self._reconcile_checkpoint_pass(auth_pass)
            if demoted:
                drift_notes.append(
                    f"demoted checkpoint PASS lacking evidence: {demoted}")
            if self.store.repo_head and self.store.repo_head != self._repo_head():
                drift_notes.append(
                    f"repository HEAD changed since last checkpoint "
                    f"({self.store.repo_head[:12]} -> {self._repo_head()[:12]}); "
                    "recomputing all states")
            try:
                lock = FileLock(self.lock_path)
                lock.acquire()
            except LockAcquisitionError as e:
                return ControllerResult(
                    report={"result": "FAIL",
                            "errors": [f"concurrency lock unavailable: {e}"],
                            "frontier": "PAUSED"},
                    classifications={}, ready_queue=[], frontier="PAUSED",
                    result="FAIL", errors=[str(e)])

        try:
            classifications = classify_all(
                self.manifest.tasks, self.manifest.tool_registry,
                self.repo_root, auth_pass)

            if not dry_run:
                self.store.invalidate_stale(classifications)

            ready_queue = build_ready_queue(self.manifest.tasks, classifications)
            contracts = []
            new_evidence = []
            executed_task = None
            frontier = "READY" if ready_queue else "PAUSED"

            by_id = {t.task_id: t for t in self.manifest.tasks}
            for tid in ready_queue:
                contracts.append(build_execution_contract(
                    by_id[tid], classifications, self.manifest.tool_registry,
                    self.ctx, auth_pass))

            if execute and ready_queue:
                tid = ready_queue[0]
                executed_task = tid
                task = by_id[tid]
                allow = list(dict.fromkeys(list(task.allowed_tools)
                                           + self.execute_allow))
                exec_cid = contract_identity_for(task, auth_pass, self.ctx)
                scope_before = self._git_porcelain()
                if not dry_run:
                    self.store.begin(tid)
                for vc in task.validation_commands:
                    # Per-command idempotency: a command already verified PASS
                    # for the current contract is never re-executed/re-recorded.
                    if command_identity(vc) in self.log.pass_command_ids(
                            task.task_id, exec_cid):
                        continue
                    rec = self._run_validation(task.task_id, vc, allow, exec_cid)
                    # write-scope guard: a validation command that writes
                    # outside declared targets invalidates the validation.
                    violations = self._scope_violations(scope_before, task)
                    if violations:
                        rec.result = "FAIL"
                        rec.failure_class = "INTEGRATION"
                        rec.notes = (rec.notes + " | " if rec.notes else "") + \
                            f"scope violation: writes outside implementation_targets {violations}"
                    _post = self._git_porcelain()
                    _excl = self._controller_artifact_prefixes()
                    rec.observed_delta = sorted(
                        p for p in (_post - scope_before)
                        if not any(p == e or p.startswith(e) for e in _excl))
                    # bind PASS to the validated target STATE (not just exit status)
                    rec.target_hashes = target_hashes(
                        task.implementation_targets, self.repo_root)
                    scope_before = _post
                    new_evidence.append(rec)
                    if not dry_run:
                        self.log.append(rec)
                        s = self.store.get(tid)
                        if rec.evidence_id not in s.evidence_refs:
                            s.evidence_refs.append(rec.evidence_id)
                        if rec.result != "PASS":
                            self.store.finish_fail(tid, rec.evidence_id)
                            why = ("scope violation" if violations
                                   else f"exit {rec.exit_status}")
                            errors.append(
                                f"validation FAIL for {tid}: {vc.id} ({why})")
                            break
                else:
                    if not dry_run and new_evidence:
                        # positive result verification: declared expected_outputs
                        # must exist with their hashes (exit status alone is
                        # never sufficient).
                        if task.expected_outputs and not all(
                                target_hashes([eo.path], self.repo_root).get(eo.path) == eo.sha256
                                for eo in task.expected_outputs):
                            self.store.finish_fail(tid, new_evidence[-1].evidence_id)
                            errors.append(
                                f"result-integrity FAIL for {tid}: declared "
                                "expected_outputs not satisfied")
                        else:
                            self.store.finish_pass(tid, new_evidence[-1].evidence_id)

            # If execution produced new PASS evidence, recompute classifications
            # so the report reflects the new terminal PASS state (the executed
            # task leaves READY). Authority/dependency state is unchanged here,
            # so this only promotes the just-validated task to PASS.
            if new_evidence and any(e.result == "PASS" for e in new_evidence):
                auth_pass = self._authoritative_pass()
                classifications = classify_all(
                    self.manifest.tasks, self.manifest.tool_registry,
                    self.repo_root, auth_pass)
                if not dry_run:
                    self.store.invalidate_stale(classifications)
                ready_queue = build_ready_queue(self.manifest.tasks, classifications)
                contracts = [build_execution_contract(
                    by_id[tid], classifications, self.manifest.tool_registry,
                    self.ctx, auth_pass)
                    for tid in ready_queue]
                frontier = "READY" if ready_queue else "PAUSED"

            if not dry_run:
                self.store.save(self._repo_head())
        finally:
            if lock is not None:
                lock.release()

        report = self._build_report(
            classifications, ready_queue, contracts, dry_run, execute,
            errors, drift_notes, new_evidence, executed_task)
        result = "FAIL" if (errors or any(e.result == "FAIL"
                                          for e in new_evidence)) else "PASS"
        return ControllerResult(
            report=report, classifications=classifications,
            ready_queue=ready_queue, contracts=contracts,
            new_evidence=[e.to_dict() for e in new_evidence],
            frontier=frontier, result=result, errors=errors,
            drift_notes=drift_notes)

    # ---- validation execution ---------------------------------------------
    def _run_validation(self, task_id: str, vc, allow: list,
                        contract_id: str = "") -> EvidenceRecord:
        """Run one declared validation command (shell=False) and capture evidence.

        Refuses unsafe commands (fail closed) via safety.validate_command. The
        evidence is cryptographically bound to the task's contract_id, the
        repository identity, HEAD, and manifest identity (provenance binding).
        """
        try:
            tokens = validate_command(vc.command, allow)
            proc = subprocess.run(
                tokens, cwd=str(self.repo_root), shell=False,
                capture_output=True, text=True, timeout=600)
            exit_status, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
            result = classify_exit(vc.command, exit_status, vc.expected_exit)
        except SafetyError as e:
            exit_status, stdout, stderr, result = None, "", str(e), "BLOCKED"
        except subprocess.TimeoutExpired as e:
            exit_status, stdout, stderr = None, "", f"timeout: {e}", "FAIL"
        except FileNotFoundError as e:
            exit_status, stdout, stderr = None, "", f"tool not found: {e}", "BLOCKED"
        except Exception as e:  # pragma: no cover - defensive
            exit_status, stdout, stderr = None, "", f"exec error: {e}", "BLOCKED"

        return EvidenceRecord(
            evidence_id="",
            task_id=task_id,
            command=vc.command,
            stdout=stdout[-4000:], stderr=stderr[-4000:],
            exit_status=exit_status, result=result,
            failure_class="TEST" if result == "FAIL" else None,
            expected_exit=vc.expected_exit,
            contract_id=contract_id,
            repository_identity=self.ctx.get("repo_identity", ""),
            head=self.ctx.get("head", ""),
            manifest_hash=self.ctx.get("manifest_hash", ""),
            validator=VALIDATOR_IDENTITY,
            command_id=command_identity(vc),
        )

    # ---- report ------------------------------------------------------------
    def _traceability(self, classifications, dry_run) -> list:
        """Per-task traceability handoff with provenance closure status:
        requirement -> spec -> task -> contract -> validation -> evidence ->
        status. Includes the current contract_id and any closure gaps."""
        pass_set = {tid for tid, c in classifications.items()
                    if c.effective_state == TaskState.PASS.value}
        out = []
        for t in self.manifest.tasks:
            ev_refs = list(t.evidence_refs)
            task_ev = []
            if not dry_run:
                for e in self.store.get(t.task_id).evidence_refs:
                    if e not in ev_refs:
                        ev_refs.append(e)
                task_ev = [r for r in self.log.verified_records()
                           if r.get("task_id") == t.task_id]
            cid = contract_identity_for(t, pass_set, self.ctx)
            c = classifications.get(t.task_id)
            gaps = closure_gaps(t, cid, task_ev, self.ctx)
            out.append({
                "task_id": t.task_id,
                "status": c.effective_state if c else "UNKNOWN",
                "contract_id": cid,
                "closure": "CLOSED" if not gaps else "OPEN",
                "closure_gaps": gaps,
                "criterion_attestations": criterion_attestations(t, cid, task_ev, self.ctx),
                "requirement_refs": list(t.requirement_refs),
                "specification_refs": [a.doc for a in t.specification_refs],
                "source_authority": [a.doc for a in t.source_authority],
                "implementation_targets": list(t.implementation_targets),
                "validation_commands": [v.id for v in t.validation_commands],
                "evidence_refs": ev_refs,
                "blocker_class": c.blocker_class if c else None,
                "blocker_reasons": c.reasons if c else [],
                "provenance": t.provenance,
            })
        return out

    def _build_report(self, classifications, ready_queue, contracts,
                      dry_run, execute, errors, drift_notes,
                      new_evidence=None, executed_task=None) -> dict:
        new_evidence = new_evidence or []
        ev_pass = sum(1 for e in new_evidence if e.result == "PASS")
        ev_fail = sum(1 for e in new_evidence if e.result == "FAIL")
        attempted = executed_task is not None
        return {
            "schema_version": "1.0",
            "controller": "impl_controller",
            "controller_version": "2.0.0",
            "project": self.manifest.project,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "manifest": self.manifest.source_path,
            "repo_head": self._repo_head(),
            "provenance_context": {
                "repository_identity": self.ctx.get("repo_identity", ""),
                "head": self.ctx.get("head", ""),
                "manifest_hash": self.ctx.get("manifest_hash", ""),
                "validator": self.ctx.get("validator", ""),
            },
            "mode": ("dry-run" if dry_run else ("execute" if execute else "plan")),
            "tool_registry": self.manifest.tool_registry.to_dict(),
            "task_count": len(self.manifest.tasks),
            "graph": self._graph_counts(classifications),
            "classifications": [classifications[t.task_id].to_dict()
                                for t in self.manifest.tasks],
            "ready_queue": list(ready_queue),
            "execution_contracts": contracts,
            "frontier": "READY" if ready_queue else "PAUSED",
            "evidence_integrity": self.log.verify_integrity(),
            "drift_notes": list(drift_notes),
            # ---- pipeline stage contract (planner -> controller -> executor
            # -> validator -> evidence/status) ----
            "stages": {
                "planner": {"artifact": "implementation-plan.json",
                            "task_count": len(self.manifest.tasks),
                            "validation": "strict (fail-closed)"},
                "controller": {"classifications": len(classifications),
                               "ready": len(ready_queue),
                               "frontier": "READY" if ready_queue else "PAUSED",
                               "contracts_emitted": len(contracts)},
                "executor": {"attempted": attempted,
                             "task": executed_task},
                "validator": {"new_evidence": len(new_evidence),
                              "pass": ev_pass, "fail": ev_fail},
                "evidence": self.log.verify_integrity(),
            },
            "traceability": self._traceability(classifications, dry_run),
            "blocker_policy": "Blockers are immutable unless an authoritative "
                              "prerequisite changes (tool availability, spec "
                              "reconciliation, dependency PASS, or a new "
                              "authorized requirement).",
            "requirement_ledger": requirement_statuses(
                getattr(self.manifest, "requirements", []),
                {tid for tid, c in classifications.items()
                 if c.effective_state == TaskState.PASS.value}),
            "coverage_identity": coverage_identity(
                getattr(self.manifest, "requirements", [])),
            "result": "PASS" if not errors else "FAIL",
            "errors": list(errors),
        }
