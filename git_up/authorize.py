"""PASS authorization predicate, closure, and derived ledger (J, M)."""

from __future__ import annotations

from . import VALIDATOR_IDENTITY
from .canonical import sha256_json
from .classify import authority_missing
from .evidence import EvidenceLog
from .identity import command_identity, contract_identity_for
from .repository import target_hashes


def criterion_attestations(task, contract_id: str, task_evidence: list) -> list:
    if not any(c.validator for c in task.acceptance_criteria):
        return []
    cmd_by_id = {vc.id: vc for vc in task.validation_commands}
    pass_cmd_ids = {
        e.get("command_id") for e in task_evidence
        if e.get("contract_id") == contract_id
        and e.get("task_id") == task.id
        and e.get("result") == "PASS"
    }
    out = []
    for c in task.acceptance_criteria:
        vc = cmd_by_id.get(c.validator)
        cmd_id = command_identity(vc) if vc else None
        attested = bool(cmd_id and cmd_id in pass_cmd_ids)
        ce_id = ""
        if attested:
            ce_id = sha256_json({
                "contract_id": contract_id,
                "task_id": task.id,
                "criterion_id": c.id,
                "validator": c.validator,
                "command_id": cmd_id,
                "result": "PASS",
            })
        out.append({
            "criterion_id": c.id,
            "validator": c.validator,
            "command_id": cmd_id or "",
            "attested": attested,
            "criterion_evidence_id": ce_id,
            "gap": None if attested else "NO_CRITERION_ATTESTATION",
        })
    return out


def closure_gaps(task, contract_id: str, task_evidence: list, ctx: dict) -> list:
    gaps = []
    if not task.requirement_refs:
        gaps.append("requirement missing (requirement -> specification)")
    if not task.specification_refs:
        gaps.append("specification missing (specification -> task)")
    if not task.validation_commands:
        gaps.append("validation missing (task -> validation)")
    if not task.acceptance_criteria:
        gaps.append("acceptance criteria missing (validation -> acceptance)")
    if any(c.validator for c in task.acceptance_criteria):
        for att in criterion_attestations(task, contract_id, task_evidence):
            if att["gap"]:
                gaps.append(
                    f"criterion '{att['criterion_id']}' {att['gap']} "
                    "(criterion -> evidence)"
                )
    else:
        pass_cmd_ids = {
            e.get("command_id") for e in task_evidence
            if e.get("contract_id") == contract_id
            and e.get("task_id") == task.id
            and e.get("result") == "PASS"
        }
        for vc in task.validation_commands:
            if command_identity(vc) not in pass_cmd_ids:
                gaps.append(
                    f"command '{vc.id}' has no PASS evidence bound to "
                    "current contract_id"
                )
    for e in task_evidence:
        if e.get("contract_id") == contract_id and e.get("validator") != VALIDATOR_IDENTITY:
            gaps.append("evidence validator identity mismatch")
            break
    return gaps


def expected_outputs_hold(task, repo_root) -> bool:
    if not task.expected_outputs:
        return True
    return all(
        target_hashes([eo.path], repo_root).get(eo.path) == eo.sha256
        for eo in task.expected_outputs
    )


def task_may_pass(task, contract_id, evs, auth, ctx, repo_root) -> bool:
    """Authorization predicate minus predecessor-state (that's the store's job)."""
    if not (task.acceptance_criteria and task.validation_commands):
        return False
    if authority_missing(task, repo_root):
        return False
    if not all(
        d.ref in auth for d in task.dependencies if d.required_state == "PASS"
    ):
        return False
    if closure_gaps(task, contract_id, evs, ctx):
        return False
    if task.implementation_targets:
        cur = target_hashes(task.implementation_targets, repo_root)
        if not any(
            e.get("target_hashes") == cur
            and e.get("contract_id") == contract_id
            and e.get("result") == "PASS"
            for e in evs
        ):
            return False
    if not expected_outputs_hold(task, repo_root):
        return False
    return True


def authoritative_pass(contract, log: EvidenceLog, ctx: dict, repo_root) -> set:
    """Least fixpoint of the authorization predicate over the task graph."""
    by_id = contract.task_by_id()
    pass_ev = {}
    for rec in log.verified_records():
        if rec.get("result") == "PASS" and EvidenceLog.is_structural_pass(rec):
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
            cid = contract_identity_for(task, auth, ctx)
            if task_may_pass(task, cid, evs, auth, ctx, repo_root):
                auth.add(tid)
                changed = True
    return auth


def requirement_statuses(requirements, pass_task_ids: set) -> list:
    out = []
    for r in requirements or []:
        tasks = [c.task_id for c in r.coverage]
        if not tasks:
            out.append({
                "requirement_id": r.id, "status": "NO_COVERAGE",
                "tasks": [], "pass_tasks": [],
            })
            continue
        pass_t = [t for t in tasks if t in pass_task_ids]
        if len(pass_t) == len(tasks):
            status = "SATISFIED"
        elif pass_t:
            status = "PARTIAL"
        else:
            status = "BLOCKED"
        out.append({
            "requirement_id": r.id, "status": status,
            "tasks": tasks, "pass_tasks": pass_t,
        })
    return out


def coverage_identity(requirements) -> str:
    payload = [
        {
            "id": r.id,
            "specification_refs": sorted(r.specification_refs),
            "coverage": sorted(
                (c.task_id, tuple(sorted(c.obligations))) for c in r.coverage
            ),
        }
        for r in (requirements or [])
    ]
    payload = sorted(payload, key=lambda r: r["id"])
    return sha256_json(payload)
