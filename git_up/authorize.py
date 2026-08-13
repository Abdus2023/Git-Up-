"""PASS authorization predicate, closure, and derived ledger (J, M)."""

from __future__ import annotations

from . import VALIDATOR_IDENTITY
from .canonical import sha256_json
from .classify import authority_missing
from .evidence import EvidenceLog
from .identity import command_identity, contract_identity_for
from .repository import target_hashes
from .safety import scope_violation_paths


def evidence_bound_to_context(rec: dict, ctx: dict) -> bool:
    """Spec 06 §6: authorizing evidence names the current HEAD / repo / source."""
    if rec.get("head") != ctx.get("head", ""):
        return False
    if rec.get("repository_identity") != ctx.get("repo_identity", ""):
        return False
    if rec.get("source_identity") != ctx.get("source_identity", ""):
        return False
    if rec.get("validator") != VALIDATOR_IDENTITY:
        return False
    return True


def criterion_attestations(task, contract_id: str, task_evidence: list,
                          ctx=None) -> list:
    if not any(c.validator for c in task.acceptance_criteria):
        return []
    cmd_by_id = {vc.id: vc for vc in task.validation_commands}
    pass_cmd_ids = {
        e.get("command_id") for e in task_evidence
        if e.get("contract_id") == contract_id
        and e.get("task_id") == task.id
        and EvidenceLog.is_structural_pass(e)
        and (ctx is None or evidence_bound_to_context(e, ctx))
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
    declared = (ctx or {}).get("requirement_ids")
    if declared is not None:
        declared_set = set(declared)
        for ref in task.requirement_refs:
            if ref not in declared_set:
                gaps.append(
                    f"requirement '{ref}' is not declared "
                    "(requirement -> specification)"
                )
    if not task.specification_refs:
        gaps.append("specification missing (specification -> task)")
    if not task.validation_commands:
        gaps.append("validation missing (task -> validation)")
    if not task.acceptance_criteria:
        gaps.append("acceptance criteria missing (validation -> acceptance)")
    if any(c.validator for c in task.acceptance_criteria):
        for att in criterion_attestations(
            task, contract_id, task_evidence, ctx=ctx,
        ):
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
            and EvidenceLog.is_structural_pass(e)
            and evidence_bound_to_context(e, ctx)
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
    if task.rejected or task.deferred:
        return False
    if not (task.acceptance_criteria and task.validation_commands):
        return False
    extra = (ctx or {}).get("authority_sources") or []
    if authority_missing(task, repo_root, extra_refs=extra):
        return False
    if not all(
        d.ref in auth for d in task.dependencies if d.required_state == "PASS"
    ):
        return False
    if closure_gaps(task, contract_id, evs, ctx):
        return False
    bound = [
        e for e in evs
        if e.get("contract_id") == contract_id
        and EvidenceLog.is_structural_pass(e)
        and evidence_bound_to_context(e, ctx)
    ]
    if task.implementation_targets:
        cur = target_hashes(task.implementation_targets, repo_root)
        if not any(e.get("target_hashes") == cur for e in bound):
            return False
    if not expected_outputs_hold(task, repo_root):
        return False
    # spec 11 §5.9: a PASS record that still carries a scope/prohibited
    # delta cannot authorize.
    for e in bound:
        if scope_violation_paths(e.get("observed_delta") or [], task):
            return False
    return True


def explain_task(task, contract_id, evs, auth, ctx, repo_root) -> dict:
    """Derived breakdown of the authorization predicate. Never authorizes."""
    extra = (ctx or {}).get("authority_sources") or []
    missing_auth = authority_missing(task, repo_root, extra_refs=extra)
    gaps = closure_gaps(task, contract_id, evs, ctx)
    deps_ok = all(
        d.ref in auth for d in task.dependencies if d.required_state == "PASS"
    )
    outputs_ok = expected_outputs_hold(task, repo_root)
    bound = [
        e for e in evs
        if e.get("contract_id") == contract_id
        and EvidenceLog.is_structural_pass(e)
        and evidence_bound_to_context(e, ctx)
    ]
    targets_ok = True
    if task.implementation_targets:
        cur = target_hashes(task.implementation_targets, repo_root)
        targets_ok = any(e.get("target_hashes") == cur for e in bound)
    scope_ok = not any(
        scope_violation_paths(e.get("observed_delta") or [], task) for e in bound
    )
    structural = [e.get("command_id") for e in bound]
    return {
        "task_id": task.id,
        "contract_id": contract_id,
        "would_pass": task_may_pass(task, contract_id, evs, auth, ctx, repo_root),
        "defined": bool(task.acceptance_criteria and task.validation_commands),
        "authority_missing": list(missing_auth),
        "dependencies_satisfied": deps_ok,
        "closure_gaps": gaps,
        "expected_outputs_ok": outputs_ok,
        "target_hashes_ok": targets_ok,
        "scope_ok": scope_ok,
        "context_bound": bool(bound) or not evs,
        "structural_pass_commands": structural,
    }


def predicate_report(contract, log: EvidenceLog, ctx: dict, repo_root) -> list:
    auth = authoritative_pass(contract, log, ctx, repo_root)
    trusted = log.verified_records()
    out = []
    for task in contract.tasks:
        evs = [r for r in trusted if r.get("task_id") == task.id]
        cid = contract_identity_for(task, auth, ctx)
        out.append(explain_task(task, cid, evs, auth, ctx, repo_root))
    return out


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
