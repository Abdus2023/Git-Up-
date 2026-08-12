"""Checkpoint / resume state store.

Persists per-task runtime state so the controller can be interrupted and
resumed. On restart it NEVER assumes prior state is still valid: it reloads,
recomputes dependencies, and invalidates stale READY/IN_PROGRESS states.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .model import TaskState, RECLASSIFIABLE_STATES


# Explicit lifecycle state machine. Security-critical invariant: PASS is
# reachable ONLY via IN_PROGRESS (never directly from READY, never from a
# checkpoint flag, never from an executor exit code alone).
ALLOWED_TRANSITIONS = {
    "DISCOVERED": {"PLANNED", "READY", "BLOCKED", "REJECTED", "DEFERRED"},
    "PLANNED": {"READY", "BLOCKED", "REJECTED", "DEFERRED"},
    "READY": {"IN_PROGRESS", "BLOCKED", "REJECTED", "DEFERRED"},
    "IN_PROGRESS": {"PASS", "FAIL", "BLOCKED", "READY"},
    "FAIL": {"READY", "BLOCKED", "IN_PROGRESS", "DISCOVERED"},
    "BLOCKED": {"READY", "BLOCKED", "IN_PROGRESS", "REJECTED", "DEFERRED"},
    "PASS": set(),        # terminal
    "REJECTED": set(),    # terminal
    "DEFERRED": set(),    # terminal
}


@dataclass
class TaskRuntimeState:
    task_id: str
    state: str = TaskState.DISCOVERED.value
    validated_pass: bool = False
    in_progress: bool = False
    last_classification: str = ""
    evidence_refs: list = field(default_factory=list)
    attempts: int = 0
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "state": self.state,
            "validated_pass": self.validated_pass,
            "in_progress": self.in_progress,
            "last_classification": self.last_classification,
            "evidence_refs": list(self.evidence_refs),
            "attempts": self.attempts,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskRuntimeState":
        return cls(
            task_id=str(d.get("task_id")),
            state=str(d.get("state", TaskState.DISCOVERED.value)),
            validated_pass=bool(d.get("validated_pass", False)),
            in_progress=bool(d.get("in_progress", False)),
            last_classification=str(d.get("last_classification", "")),
            evidence_refs=list(d.get("evidence_refs", [])),
            attempts=int(d.get("attempts", 0)),
            updated_at=str(d.get("updated_at", "")),
        )


class StateStore:
    """JSON-backed checkpoint store."""

    SCHEMA_VERSION = "1.0"

    def __init__(self, path):
        self.path = Path(path)
        self.tasks: dict = {}           # task_id -> TaskRuntimeState
        self.last_checkpoint: str = ""
        self.repo_head: str = ""
        self.loaded = False

    # ---- persistence -------------------------------------------------------
    def load(self) -> None:
        self.loaded = True
        if not self.path.is_file():
            self.tasks = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # corrupt checkpoint -> start clean (fail safe, not silent trust)
            self.tasks = {}
            return
        self.last_checkpoint = str(raw.get("last_checkpoint", ""))
        self.repo_head = str(raw.get("repo_head", ""))
        for rec in raw.get("tasks", []):
            s = TaskRuntimeState.from_dict(rec)
            self.tasks[s.task_id] = s

    def save(self, repo_head: str = "") -> None:
        self.repo_head = repo_head or self.repo_head
        self.last_checkpoint = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "last_checkpoint": self.last_checkpoint,
            "repo_head": self.repo_head,
            "tasks": [s.to_dict() for s in self.tasks.values()],
        }
        # Atomic checkpoint: write temp, flush, fsync, atomic rename. A crash
        # mid-write never leaves a half-written checkpoint (the old file stays
        # intact until os.replace succeeds atomically).
        tmp = self.path.with_name(self.path.name + ".tmp")
        data = json.dumps(payload, indent=2) + "\n"
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass  # fsync best-effort on some filesystems
        os.replace(tmp, self.path)

    # ---- access ------------------------------------------------------------
    def get(self, task_id: str) -> TaskRuntimeState:
        if task_id not in self.tasks:
            self.tasks[task_id] = TaskRuntimeState(task_id=task_id)
        return self.tasks[task_id]

    def set_state(self, task_id: str, classification_state: str,
                  validated_pass: Optional[bool] = None) -> None:
        s = self.get(task_id)
        s.state = classification_state
        s.last_classification = classification_state
        if validated_pass is not None:
            s.validated_pass = validated_pass
        s.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def begin(self, task_id: str) -> None:
        s = self.get(task_id)
        s.in_progress = True
        s.attempts += 1
        s.state = TaskState.IN_PROGRESS.value
        s.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def finish_pass(self, task_id: str, evidence_id: str) -> None:
        s = self.get(task_id)
        s.in_progress = False
        s.state = TaskState.PASS.value
        s.validated_pass = True
        if evidence_id not in s.evidence_refs:
            s.evidence_refs.append(evidence_id)
        s.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def finish_fail(self, task_id: str, evidence_id: str) -> None:
        s = self.get(task_id)
        s.in_progress = False
        s.state = TaskState.FAIL.value
        if evidence_id not in s.evidence_refs:
            s.evidence_refs.append(evidence_id)
        s.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def validated_pass_set(self) -> set:
        return {tid for tid, s in self.tasks.items() if s.validated_pass}

    # ---- resume discipline -------------------------------------------------
    def invalidate_stale(self, classifications: dict) -> list:
        """Reconcile persisted state with freshly recomputed classifications.

        Stale READY/IN_PROGRESS markers are demoted to the recomputed state.
        PASS/REJECTED/DEFERRED are terminal and preserved. Returns the list of
        task_ids whose persisted state changed.
        """
        changed = []
        for tid, cls in classifications.items():
            s = self.get(tid)
            new_eff = cls.effective_state
            # terminal persisted states are sticky
            if s.state in {TaskState.PASS.value, TaskState.REJECTED.value,
                           TaskState.DEFERRED.value}:
                continue
            if s.state != new_eff:
                changed.append(tid)
                s.state = new_eff
                s.last_classification = new_eff
                s.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            # an IN_PROGRESS task whose reclassification is not READY must drop
            if s.in_progress and new_eff != TaskState.READY.value:
                if not s.in_progress is False:
                    changed.append(tid)
                s.in_progress = False
        return changed
