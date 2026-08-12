"""Fail-closed classifier (component E). Never writes PASS."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .model import (
    BlockerCategory, Classification, PRECEDENCE, Task, TaskState,
)


def tool_path_available(tool, tid: str) -> bool:
    binary = (tool.binary if tool and tool.binary else tid)
    return shutil.which(binary) is not None


def authority_missing(task: Task, repo_root: Path) -> list:
    missing = []
    root = Path(repo_root).resolve()
    for ref in list(task.source_authority) + list(task.specification_refs):
        p = root / ref.path
        try:
            resolved = p.resolve(strict=False)
            resolved.relative_to(root)
        except (ValueError, OSError):
            missing.append(ref.path)
            continue
        if not (p.is_file() and os.access(p, os.R_OK)):
            missing.append(ref.path)
    return missing


def coverage_gaps(task: Task) -> list:
    gaps = []
    crits = task.acceptance_criteria
    cmd_ids = {c.id for c in task.validation_commands}
    if not any(c.validator for c in crits):
        return gaps
    for c in crits:
        if not c.validator:
            gaps.append(
                f"acceptance criterion '{c.id}' declares no validator "
                "(criterion is untested)"
            )
        elif c.validator not in cmd_ids:
            gaps.append(
                f"criterion '{c.id}' validator '{c.validator}' is not a "
                "declared validation command"
            )
    covered = {c.validator for c in crits if c.validator in cmd_ids}
    for cmd in task.validation_commands:
        if cmd.id not in covered:
            gaps.append(
                f"validator '{cmd.id}' covers no acceptance criterion "
                "(command has no semantic purpose)"
            )
    return gaps


def self_blockers(task: Task, tools: dict, repo_root: Path):
    reasons, detail = [], []

    if task.spec_conflicts:
        reasons.append(BlockerCategory.SPECIFICATION_CONFLICT.value)
        detail.append(f"specification conflicts: {task.spec_conflicts}")
    if task.spec_gaps:
        reasons.append(BlockerCategory.INCOMPLETE_SPECIFICATION.value)
        detail.append(f"incomplete specification (gaps): {task.spec_gaps}")

    for tid in task.required_tools:
        tool = tools.get(tid)
        if tool is None or not tool.available or not tool_path_available(tool, tid):
            reasons.append(BlockerCategory.TOOLCHAIN.value)
            extra = ""
            if tool and tool.available:
                extra = " (claimed available but not on PATH)"
            detail.append(f"required tool unavailable: {tid}{extra}")
            break

    if not task.source_authority or not task.requirement_refs:
        reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        detail.append("missing source_authority or requirement_refs")
    if not task.specification_refs:
        reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        detail.append("requirement lacks specification_refs")
    missing_docs = authority_missing(task, repo_root)
    if missing_docs:
        reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        detail.append(f"authoritative doc(s) not found on disk: {missing_docs}")
    if not task.validation_commands:
        reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        detail.append("no validation_commands — acceptance is not executable")
    if not task.acceptance_criteria:
        reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        detail.append("no acceptance_criteria — success is undefined")
    for gap in coverage_gaps(task):
        reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        detail.append(gap)

    for b in task.declared_blockers:
        if not b.satisfied:
            reasons.append(b.category)
            detail.append(f"declared blocker [{b.category}] — {b.detail}")

    seen = set()
    reasons = [r for r in reasons if not (r in seen or seen.add(r))]
    return reasons, detail


def _primary(reasons: list) -> str:
    for cat in PRECEDENCE:
        if cat in reasons:
            return cat
    return reasons[0] if reasons else None


def classify_task(task: Task, satisfied_deps: set, tools: dict, repo_root) -> Classification:
    if task.rejected:
        return Classification(task_id=task.id, effective_state=TaskState.REJECTED.value)
    if task.deferred:
        return Classification(task_id=task.id, effective_state=TaskState.DEFERRED.value)

    reasons, detail = self_blockers(task, tools, Path(repo_root))

    dep_blocked = False
    for dep in task.dependencies:
        if dep.required_state == TaskState.PASS.value:
            if dep.ref not in satisfied_deps:
                dep_blocked = True
                detail.append(f"dependency '{dep.ref}' not PASS")
        else:
            dep_blocked = True
            detail.append(
                f"dependency '{dep.ref}' required_state={dep.required_state} "
                "is not auto-satisfiable"
            )
    if dep_blocked:
        reasons.append(BlockerCategory.DEPENDENCY.value)

    seen = set()
    reasons = [r for r in reasons if not (r in seen or seen.add(r))]
    if reasons:
        ordered = [c for c in PRECEDENCE if c in reasons]
        tail = [r for r in reasons if r not in ordered]
        return Classification(
            task_id=task.id,
            effective_state=TaskState.BLOCKED.value,
            ready=False,
            blocker_class=_primary(reasons),
            reasons=ordered + tail,
            detail=detail,
        )
    return Classification(
        task_id=task.id, effective_state=TaskState.READY.value, ready=True
    )


def classify_all(tasks, tools: dict, repo_root, validated_pass=None) -> dict:
    """Classify every task. PASS only enters via validated_pass (reconstruction)."""
    validated_pass = set(validated_pass or [])
    classifications = {}
    changed = True
    iterations = 0
    max_iter = len(tasks) + 2
    while changed and iterations <= max_iter:
        changed = False
        iterations += 1
        satisfied = set(validated_pass)
        new = {}
        for t in tasks:
            if t.id in validated_pass:
                cls = Classification(
                    task_id=t.id, effective_state=TaskState.PASS.value, ready=False
                )
            else:
                cls = classify_task(t, satisfied, tools, repo_root)
            new[t.id] = cls
        for tid, cls in new.items():
            prev = classifications.get(tid)
            if prev is None or prev.effective_state != cls.effective_state:
                changed = True
        classifications = new
    return classifications
