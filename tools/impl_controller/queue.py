"""Deterministic READY queue construction.

Ordering uses ONLY documented metadata:
    1. explicit priority (lower number = higher priority)
    2. dependency depth (shallower first)
    3. implementation-plan ordering (plan_order)
    4. stable task_id

No task is selected because it "looks useful". No priority is manufactured.
"""
from __future__ import annotations

from .model import Classification, TaskState


def dependency_depth(task_id: str, by_id: dict, cache: dict) -> int:
    """Longest chain length from this task to a dependency leaf."""
    if task_id in cache:
        return cache[task_id]
    task = by_id.get(task_id)
    if task is None or not task.dependency_refs:
        cache[task_id] = 0
        return 0
    # guard against cycles defensively
    cache[task_id] = 0
    depth = 0
    for dep in task.dependency_refs:
        d = dependency_depth(dep.ref, by_id, cache) + 1
        if d > depth:
            depth = d
    cache[task_id] = depth
    return depth


def build_ready_queue(tasks: list, classifications: dict) -> list:
    """Return the list of READY task_ids in deterministic order."""
    by_id = {t.task_id: t for t in tasks}
    depth_cache: dict = {}

    ready = [t for t in tasks
             if classifications.get(t.task_id)
             and classifications[t.task_id].effective_state == TaskState.READY.value]

    def key(t):
        return (
            t.priority,
            dependency_depth(t.task_id, by_id, depth_cache),
            t.plan_order,
            t.task_id,
        )

    ready.sort(key=key)
    return [t.task_id for t in ready]
