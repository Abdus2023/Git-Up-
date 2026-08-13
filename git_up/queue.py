"""Deterministic ready queue."""

from __future__ import annotations

from .model import TaskState


def build_ready_queue(tasks, classifications) -> list:
    ready = []
    for t in tasks:
        c = classifications.get(t.id)
        if c and c.effective_state == TaskState.READY.value:
            ready.append(t)
    ready.sort(key=lambda t: (t.priority, t.order, t.id))
    return [t.id for t in ready]
