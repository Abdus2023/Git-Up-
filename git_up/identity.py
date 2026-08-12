"""Contract and command identity (component F, spec 12)."""

from __future__ import annotations

from . import VALIDATOR_IDENTITY
from .canonical import sha256_json
from .model import Task


def command_identity(vc) -> str:
    return sha256_json({
        "id": vc.id,
        "command": vc.command,
        "expected_exit": vc.expected_exit,
    })


def source_identity(contract) -> str:
    """Hash of the loaded contract's semantic content (not a user-supplied id)."""
    payload = {
        "schema_version": contract.schema_version,
        "tasks": [_task_canon(t) for t in contract.tasks],
        "tools": sorted(
            ({"id": t.id, "available": t.available, "binary": t.binary,
              "version": t.version} for t in contract.tools),
            key=lambda x: x["id"],
        ),
        "requirements": sorted(
            ({"id": r.id,
              "specification_refs": sorted(r.specification_refs),
              "coverage": sorted(
                  (c.task_id, tuple(sorted(c.obligations))) for c in r.coverage),
              } for r in contract.requirements),
            key=lambda x: x["id"],
        ),
        "policy": {
            "timeout_seconds": contract.timeout_seconds,
            "concurrency": contract.policy.get("concurrency", "exclusive"),
            "failure_mode": contract.policy.get("failure_mode", "fail_closed"),
        },
        "provenance": {
            "producer": (contract.provenance or {}).get("producer", ""),
            "source_identity": (contract.provenance or {}).get("source_identity", ""),
            "parent_contracts": sorted(
                (contract.provenance or {}).get("parent_contracts") or []
            ),
        },
    }
    binding = repository_binding(contract)
    if binding:
        payload["repository"] = binding
    return sha256_json(payload)


def repository_binding(contract) -> dict:
    """Declared repository binding. Empty/absent is omitted from identity."""
    raw = getattr(contract, "repository", None) or {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    ident = str(raw.get("identity") or "")
    rev = str(raw.get("revision") or raw.get("head") or "")
    dirty = raw.get("dirty_state")
    if ident:
        out["identity"] = ident
    if rev:
        out["revision"] = rev
    if dirty not in (None, ""):
        out["dirty_state"] = dirty
    return out


def _task_canon(t: Task) -> dict:
    def keyf(x):
        return sha256_json(x) if not isinstance(x, str) else x

    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "scope": t.scope,
        "priority": t.priority,
        "order": t.order,
        "requirement_refs": sorted(t.requirement_refs),
        "required_tools": sorted(t.required_tools),
        "allowed_tools": sorted(t.allowed_tools),
        "implementation_targets": sorted(t.implementation_targets),
        "prohibited_scope": sorted(t.prohibited_scope),
        "spec_conflicts": sorted(str(x) for x in t.spec_conflicts),
        "spec_gaps": sorted(str(x) for x in t.spec_gaps),
        "source_authority": sorted(
            ({"path": a.path, "anchor": a.anchor,
              "requirement_id": a.requirement_id} for a in t.source_authority),
            key=keyf,
        ),
        "specification_refs": sorted(
            ({"path": a.path, "anchor": a.anchor} for a in t.specification_refs),
            key=keyf,
        ),
        "dependencies": sorted(
            ({"ref": d.ref, "required_state": d.required_state}
             for d in t.dependencies),
            key=keyf,
        ),
        "validation_commands": sorted(
            ({"id": v.id, "command": v.command, "expected_exit": v.expected_exit}
             for v in t.validation_commands),
            key=keyf,
        ),
        "acceptance_criteria": sorted(
            ({"id": c.id, "validator": c.validator} for c in t.acceptance_criteria),
            key=keyf,
        ),
        "expected_outputs": sorted(
            ({"path": e.path, "sha256": e.sha256} for e in t.expected_outputs),
            key=keyf,
        ),
        "declared_blockers": sorted(
            ({"category": b.category, "satisfied": b.satisfied}
             for b in t.declared_blockers),
            key=keyf,
        ),
        "rejected": t.rejected,
        "deferred": t.deferred,
    }


def contract_identity_for(task: Task, satisfied_deps: set, ctx: dict) -> str:
    dep_state = sorted(
        d.ref for d in task.dependencies
        if d.required_state == "PASS" and d.ref in satisfied_deps
    )
    tool_versions = ctx.get("tool_versions") or {}
    payload = {
        "validator": VALIDATOR_IDENTITY,
        "repository": ctx.get("repo_identity", ""),
        "head": ctx.get("head", ""),
        "source": ctx.get("source_identity", ""),
        "task_id": task.id,
        "requirements": sorted(task.requirement_refs),
        "specifications": sorted(f"{a.path}|{a.anchor}" for a in task.specification_refs),
        "targets": sorted(task.implementation_targets),
        "prohibited": sorted(task.prohibited_scope),
        "tools": sorted((tid, tool_versions.get(tid, "")) for tid in task.required_tools),
        "allowed_tools": sorted(task.allowed_tools),
        "commands": sorted(command_identity(v) for v in task.validation_commands),
        "criteria": sorted((c.id, c.validator) for c in task.acceptance_criteria),
        "expected_outputs": sorted((e.path, e.sha256) for e in task.expected_outputs),
        "dependency_state": dep_state,
        "policy": {
            "timeout_seconds": ctx.get("timeout_seconds", 600),
            "concurrency": "exclusive",
            "failure_mode": "fail_closed",
        },
    }
    return sha256_json(payload)


def provenance_context(repo_root, contract, *, create_identity: bool) -> dict:
    from .repository import ensure_repo_identity, read_repo_identity, repo_head

    ident = ensure_repo_identity(repo_root) if create_identity else read_repo_identity(repo_root)
    return {
        "repo_identity": ident,
        "head": repo_head(repo_root),
        "source_identity": source_identity(contract),
        "validator": VALIDATOR_IDENTITY,
        "tool_versions": {t.id: t.version for t in contract.tools},
        "timeout_seconds": contract.timeout_seconds,
        "requirement_ids": [r.id for r in contract.requirements if r.id],
    }
