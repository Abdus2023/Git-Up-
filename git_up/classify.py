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
    elif not (task.allowed_tools or task.required_tools):
        reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        detail.append(
            "validation_commands present but allowed_tools and required_tools "
            "are empty — no tool is authorized"
        )
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


def cyclic_tasks(tasks) -> dict:
    """Strongly connected components that are real cycles (spec 07 §4).

    Returns task_id → one closed path (A → B → A). Isolated self-loops included.
    """
    ids = {t.id for t in tasks}
    graph = {
        t.id: [d.ref for d in t.dependencies if d.ref in ids]
        for t in tasks
    }
    index, lowlink, stack, onstack = {}, {}, [], set()
    i = [0]
    sccs = []

    def strongconnect(v):
        index[v] = lowlink[v] = i[0]
        i[0] += 1
        stack.append(v)
        onstack.add(v)
        for w in graph[v]:
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in onstack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                onstack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for v in sorted(graph):
        if v not in index:
            strongconnect(v)

    out = {}
    for comp in sccs:
        if len(comp) > 1:
            ordered = sorted(comp)
            path = ordered + [ordered[0]]
            for n in comp:
                out[n] = path
        elif len(comp) == 1 and comp[0] in graph[comp[0]]:
            out[comp[0]] = [comp[0], comp[0]]
    return out


def classify_task(task: Task, satisfied_deps: set, tools: dict, repo_root,
                  cycle=None) -> Classification:
    if task.rejected:
        return Classification(task_id=task.id, effective_state=TaskState.REJECTED.value)
    if task.deferred:
        return Classification(task_id=task.id, effective_state=TaskState.DEFERRED.value)

    reasons, detail = self_blockers(task, tools, Path(repo_root))

    dep_blocked = False
    if cycle:
        dep_blocked = True
        detail.append("dependency cycle: " + " → ".join(cycle))
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
    cycles = cyclic_tasks(tasks)
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
            # Contract terminal flags outrank reconstructed PASS (spec 08 §5).
            if t.rejected:
                cls = Classification(
                    task_id=t.id, effective_state=TaskState.REJECTED.value
                )
            elif t.deferred:
                cls = Classification(
                    task_id=t.id, effective_state=TaskState.DEFERRED.value
                )
            elif t.id in validated_pass:
                cls = Classification(
                    task_id=t.id, effective_state=TaskState.PASS.value, ready=False
                )
            else:
                cls = classify_task(
                    t, satisfied, tools, repo_root, cycle=cycles.get(t.id),
                )
            new[t.id] = cls
        for tid, cls in new.items():
            prev = classifications.get(tid)
            if prev is None or prev.effective_state != cls.effective_state:
                changed = True
        classifications = new
    return classifications
