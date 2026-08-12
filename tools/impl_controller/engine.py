"""Deterministic, fail-closed dependency engine.

Evaluation order (per the execution protocol) determines the *primary*
blocker class:

    rejected            -> REJECTED
    spec conflict/gap   -> BLOCKED  (SPECIFICATION)
    dependency not PASS -> BLOCKED  (DEPENDENCY)
    tool unavailable    -> BLOCKED  (TOOLCHAIN)
    authority missing   -> BLOCKED  (INSUFFICIENT_TASK_DEFINITION)
    declared blocker    -> BLOCKED  (declared category)
    otherwise           -> READY

Every applicable reason is collected (fail closed: report all blockers).
A BLOCKED task is never READY and never auto-executed. A task whose
authoritative source documents do not exist on disk is INSUFFICIENT.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .model import (
    Task, ToolRegistry, TaskState, BlockerCategory, Classification,
    TERMINAL_STATES,
)


# Mapping of tool ids to the executable name used to VERIFY availability on
# PATH. A tool is usable only if its claim is true AND the binary is found.
KNOWN_TOOL_BINARIES = {
    "rebol-278": "rebol", "rebol": "rebol", "rebol2": "rebol",
    "r3": "r3", "r3-make": "r3-make",
    "python3": "python3", "python": "python",
    "gcc": "gcc", "clang": "clang", "cc": "cc",
    "make": "make", "cmake": "cmake",
}


def _tool_binary(tool, tid: str) -> str:
    if tool is not None and getattr(tool, "binary", ""):
        return tool.binary
    return KNOWN_TOOL_BINARIES.get(tid, tid)


def tool_path_available(tool, tid: str) -> bool:
    """True iff an executable for the tool is actually present on PATH."""
    return shutil.which(_tool_binary(tool, tid)) is not None


@dataclass
class SelfBlockers:
    """Blockers derivable from a task in isolation (no dependency graph)."""

    reasons: list = field(default_factory=list)   # BlockerCategory values
    detail: list = field(default_factory=list)    # strings


def _authority_exists(task: Task, repo_root: Path) -> list:
    """Return list of authoritative doc paths that are missing OR not a
    readable file inside the repository (fail closed).

    Rejects: nonexistent path, path replaced by a directory, unreadable file,
    and any path that resolves outside the repository (escape).
    """
    missing = []
    root = repo_root.resolve()
    for ref in list(task.source_authority) + list(task.specification_refs):
        p = root / ref.doc
        try:
            resolved = p.resolve(strict=False)
            resolved.relative_to(root)            # confinement
        except (ValueError, OSError):
            missing.append(ref.doc)
            continue
        if not (p.is_file() and os.access(p, os.R_OK)):
            missing.append(ref.doc)
    return missing


def authority_problems(task: Task, repo_root: Path) -> list:
    """Public alias for the authority existence/confinement check."""
    return _authority_exists(task, repo_root)


def _coverage_gaps(task: Task) -> list:
    """Semantic coverage gaps (opt-in criterion<->validator mapping).

    A task is in "strict coverage" mode when ANY acceptance criterion declares a
    `validator`. In that mode every criterion must name a declared validation
    command and every command must cover >=1 criterion. Tasks that declare no
    validators use the legacy presence-based contract (grandfathered) and are
    NOT inferred — missing semantics is never guessed.
    """
    gaps = []
    crits = task.acceptance_criteria
    cmd_ids = {c.id for c in task.validation_commands}
    if not any(c.validator for c in crits):
        return gaps  # legacy presence-based contract; no coverage asserted
    for c in crits:
        if not c.validator:
            gaps.append(f"acceptance criterion '{c.id}' declares no validator "
                        "(criterion is untested)")
        elif c.validator not in cmd_ids:
            gaps.append(f"criterion '{c.id}' validator '{c.validator}' is not a "
                        "declared validation command")
    covered = {c.validator for c in crits if c.validator in cmd_ids}
    for cmd in task.validation_commands:
        if cmd.id not in covered:
            gaps.append(f"validator '{cmd.id}' covers no acceptance criterion "
                        "(command has no semantic purpose)")
    return gaps


def self_blockers(task: Task, tool_registry: ToolRegistry,
                  repo_root: Path) -> SelfBlockers:
    """Compute blockers independent of other tasks' states."""
    sb = SelfBlockers()

    # --- specification conflicts / gaps -------------------------------------
    if task.spec_conflicts:
        sb.reasons.append(BlockerCategory.SPECIFICATION_CONFLICT.value)
        sb.detail.append(f"specification conflicts: {task.spec_conflicts}")
    if task.spec_gaps:
        sb.reasons.append(BlockerCategory.INCOMPLETE_SPECIFICATION.value)
        sb.detail.append(f"incomplete specification (gaps): {task.spec_gaps}")

    # --- toolchain ----------------------------------------------------------
    # A required tool blocks unless it is CLAIMED available AND its executable
    # is actually present on PATH (ground truth, not a planner claim).
    for tid in task.required_tools:
        tool = tool_registry.get(tid)
        if tool is None or not tool.available or not tool_path_available(tool, tid):
            sb.reasons.append(BlockerCategory.TOOLCHAIN.value)
            sb.detail.append(
                f"required tool unavailable: {tid}"
                + (f" (claimed available but not on PATH)" if (tool and tool.available) else "")
            )
            break

    # --- authoritative definition ------------------------------------------
    if not task.source_authority or not task.requirement_refs:
        sb.reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        sb.detail.append(
            "missing source_authority or requirement_refs — "
            "no authoritative behavioral contract")
    if not task.specification_refs:
        # traceability invariant: every requirement must trace to a spec
        sb.reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        sb.detail.append(
            "requirement lacks specification_refs — traceability gap "
            "(requirement without specification)")
    missing_docs = _authority_exists(task, repo_root)
    if missing_docs:
        sb.reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        sb.detail.append(f"authoritative doc(s) not found on disk: {missing_docs}")
    if not task.validation_commands:
        sb.reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        sb.detail.append("no validation_commands — acceptance is not executable")
    if not task.acceptance_criteria:
        sb.reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        sb.detail.append("no acceptance_criteria — success is undefined")
    for gap in _coverage_gaps(task):
        sb.reasons.append(BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value)
        sb.detail.append(gap)

    # --- declared (evidence-grounded) blockers -----------------------------
    for b in task.declared_blockers:
        if not b.satisfied:
            sb.reasons.append(b.category)
            sb.detail.append(f"declared blocker [{b.category}] — {b.detail}")

    # de-duplicate reasons preserving order
    seen = set()
    sb.reasons = [r for r in sb.reasons if not (r in seen or seen.add(r))]
    return sb


# Precedence for selecting the PRIMARY blocker class (matches protocol order).
_PRECEDENCE = [
    BlockerCategory.SPECIFICATION_CONFLICT.value,
    BlockerCategory.INCOMPLETE_SPECIFICATION.value,
    BlockerCategory.DEPENDENCY.value,
    BlockerCategory.TOOLCHAIN.value,
    BlockerCategory.INSUFFICIENT_TASK_DEFINITION.value,
    BlockerCategory.TRACEABILITY.value,
    BlockerCategory.ARCHITECTURE.value,
    BlockerCategory.PROVISIONING.value,
    BlockerCategory.AUTHORIZATION.value,
    BlockerCategory.ENVIRONMENT.value,
    BlockerCategory.INFRASTRUCTURE.value,
]


def _primary_class(reasons: list, dependency_blocked: bool) -> Optional[str]:
    if dependency_blocked and BlockerCategory.DEPENDENCY.value not in reasons:
        reasons = reasons + [BlockerCategory.DEPENDENCY.value]
    for cat in _PRECEDENCE:
        if cat in reasons:
            return cat
    return reasons[0] if reasons else None


def classify_task(task: Task, satisfied_deps: set, tool_registry: ToolRegistry,
                  repo_root: Path, terminal_state: Optional[TaskState] = None) -> Classification:
    """Classify a single task.

    ``satisfied_deps`` is the set of dependency task_ids whose required_state
    is currently met. ``terminal_state`` (if in TERMINAL_STATES) overrides
    recomputation.
    """
    if task.rejected:
        return Classification(task_id=task.task_id,
                              effective_state=TaskState.REJECTED.value)

    if terminal_state in TERMINAL_STATES:
        return Classification(task_id=task.task_id,
                              effective_state=terminal_state.value,
                              ready=(terminal_state == TaskState.READY))

    if task.deferred:
        return Classification(task_id=task.task_id,
                              effective_state=TaskState.DEFERRED.value)

    sb = self_blockers(task, tool_registry, repo_root)

    # --- dependency resolution ---------------------------------------------
    dep_reasons = []
    dep_detail = []
    dependency_blocked = False
    for dep in task.dependency_refs:
        # A dependency is satisfied only if its required_state is met.
        # PASS deps are satisfied via the satisfied_deps set; other required
        # states are not modeled as auto-satisfiable (fail closed).
        if dep.required_state == TaskState.PASS.value:
            if dep.ref not in satisfied_deps:
                dependency_blocked = True
                dep_detail.append(
                    f"dependency '{dep.ref}' not PASS (required_state=PASS)")
        else:
            dependency_blocked = True
            dep_detail.append(
                f"dependency '{dep.ref}' required_state={dep.required_state} "
                "is not auto-satisfiable")
    if dependency_blocked:
        dep_reasons = [BlockerCategory.DEPENDENCY.value]

    all_reasons = sb.reasons + dep_reasons
    all_detail = sb.detail + dep_detail

    if all_reasons:
        primary = _primary_class(all_reasons, dependency_blocked)
        # full reason set, de-duplicated, ordered by precedence then discovery
        ordered = [c for c in _PRECEDENCE if c in all_reasons]
        tail = [r for r in all_reasons if r not in ordered]
        full_reasons = ordered + tail
        return Classification(
            task_id=task.task_id,
            effective_state=TaskState.BLOCKED.value,
            ready=False,
            blocker_class=primary,
            reasons=full_reasons,
            detail=all_detail,
        )

    return Classification(task_id=task.task_id,
                          effective_state=TaskState.READY.value,
                          ready=True)


def classify_all(tasks: list, tool_registry: ToolRegistry, repo_root: Path,
                 validated_pass: Optional[set] = None) -> dict:
    """Classify every task to a fixpoint.

    ``validated_pass`` is the set of task_ids with a validated PASS evidence
    record (terminal success). These are the only tasks that satisfy PASS
    dependencies; the engine never auto-promotes a task to PASS.

    Returns: {task_id: Classification}.
    """
    validated_pass = set(validated_pass or set())
    by_id = {t.task_id: t for t in tasks}
    classifications = {}

    # Iterative fixpoint: a dependency can only be satisfied by a PASS task,
    # and PASS only comes from validated_pass, so this converges immediately;
    # we still iterate to a bounded fixpoint for generality.
    changed = True
    iterations = 0
    max_iter = len(tasks) + 2
    while changed and iterations <= max_iter:
        changed = False
        iterations += 1
        satisfied = set(validated_pass)
        for t in tasks:
            c = classifications.get(t.task_id)
            if c is not None and c.effective_state == TaskState.PASS.value:
                satisfied.add(t.task_id)
        new = {}
        for t in tasks:
            if t.task_id in validated_pass:
                # Validated PASS is terminal success: it is not recomputed
                # (it represents recorded evidence) and is never re-queued.
                cls = Classification(task_id=t.task_id,
                                     effective_state=TaskState.PASS.value,
                                     ready=False)
            else:
                cls = classify_task(t, satisfied, tool_registry, repo_root)
            new[t.task_id] = cls
        # detect change
        for tid, cls in new.items():
            prev = classifications.get(tid)
            cur = cls.effective_state
            if prev is None or prev.effective_state != cur:
                changed = True
        classifications = new

    return classifications


def blocking_chain(task_id: str, classifications: dict, by_id: dict) -> list:
    """Return the dependency blocking chain starting at ``task_id``.

    Walks the first non-PASS dependency at each step until a leaf or cycle is
    reached. Terminates on cycles (defensive). Example: A -> B -> C -> A
    returns the cycle without ever yielding READY.
    """
    chain = [task_id]
    cur = task_id
    seen = {task_id}
    while cur in by_id:
        nxt = None
        for dep in by_id[cur].dependency_refs:
            dc = classifications.get(dep.ref)
            if dc is None or dc.effective_state != TaskState.PASS.value:
                nxt = dep.ref
                break
        if nxt is None or nxt in seen:
            if nxt is not None:
                chain.append(nxt)          # close the cycle for reporting
            break
        chain.append(nxt)
        seen.add(nxt)
        cur = nxt
    return chain
