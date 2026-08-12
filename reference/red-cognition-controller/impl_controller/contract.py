"""Execution-contract generation for READY tasks.

A contract fully constrains what the execution agent may do. It is generated
only for READY tasks; the controller never auto-executes a BLOCKED task.
"""
from __future__ import annotations

from .model import Task, TaskState
from .provenance import contract_identity_for, default_context


def build_execution_contract(task: Task, classifications: dict,
                             tool_registry, ctx=None,
                             satisfied_deps=None) -> dict:
    """Build the execution contract for a READY task.

    Raises ValueError if the task is not READY (fail closed).
    """
    cls = classifications.get(task.task_id)
    if cls is None or cls.effective_state != TaskState.READY.value:
        raise ValueError(
            f"refuse contract: task {task.task_id} is not READY "
            f"(state={cls.effective_state if cls else 'UNKNOWN'})")

    ctx = ctx if ctx is not None else default_context()
    satisfied = satisfied_deps if satisfied_deps is not None else set()
    cid = contract_identity_for(task, satisfied, ctx)

    satisfied_deps_view = [
        {"ref": d.ref, "required_state": d.required_state,
         "satisfied": (d.required_state == TaskState.PASS.value)}
        for d in task.dependency_refs
    ]

    return {
        "contract_id": cid,
        "task_id": task.task_id,
        "title": task.title,
        "scope": task.scope,
        "provenance_context": {
            "repository_identity": ctx.get("repo_identity", ""),
            "head": ctx.get("head", ""),
            "manifest_hash": ctx.get("manifest_hash", ""),
            "validator": ctx.get("validator", ""),
        },
        "files_allowed_to_change": list(task.implementation_targets),
        "authoritative_requirements": [
            {"doc": a.doc, "anchor": a.anchor, "requirement_id": a.requirement_id}
            for a in task.source_authority
        ],
        "requirement_refs": list(task.requirement_refs),
        "specification_refs": [
            {"doc": a.doc, "anchor": a.anchor} for a in task.specification_refs
        ],
        "dependencies": satisfied_deps_view,
        "required_tools": [
            {"id": tid, "available": tool_registry.available(tid)}
            for tid in task.required_tools
        ],
        "validation_commands": [
            {"id": v.id, "command": v.command,
             "expected_exit": v.expected_exit, "purpose": v.purpose}
            for v in task.validation_commands
        ],
        "acceptance_criteria": [
            {"id": a.id, "criterion": a.criterion}
            for a in task.acceptance_criteria
        ],
        "prohibited_scope": list(task.prohibited_scope),
        "allowed_tools": list(task.allowed_tools),
        "required_evidence": [
            "contract_id", "command", "stdout", "stderr", "exit_status",
            "result", "timestamp", "repository_identity", "head",
            "manifest_hash", "validator"
        ],
        "provenance": task.provenance,
    }
