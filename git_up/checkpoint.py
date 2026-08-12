"""Crash-safe checkpoint store (component K). Subordinate to evidence."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import STATE_SCHEMA
from .errors import TransitionError
from .model import ALLOWED_TRANSITIONS, TaskState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
            task_id=str(d.get("task_id") or ""),
            state=str(d.get("state") or TaskState.DISCOVERED.value),
            validated_pass=bool(d.get("validated_pass", False)),
            in_progress=bool(d.get("in_progress", False)),
            last_classification=str(d.get("last_classification") or ""),
            evidence_refs=list(d.get("evidence_refs") or []),
            attempts=int(d.get("attempts") or 0),
            updated_at=str(d.get("updated_at") or ""),
        )


class StateStore:
    def __init__(self, path):
        self.path = Path(path)
        self.tasks: dict = {}
        self.last_checkpoint: str = ""
        self.repo_head: str = ""
        self.loaded = False

    def load(self) -> None:
        self.loaded = True
        if not self.path.is_file():
            self.tasks = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.tasks = {}
            return
        self.last_checkpoint = str(raw.get("last_checkpoint") or "")
        self.repo_head = str(raw.get("repo_head") or "")
        self.tasks = {}
        for rec in raw.get("tasks") or []:
            s = TaskRuntimeState.from_dict(rec)
            if s.task_id:
                self.tasks[s.task_id] = s

    def save(self, repo_head: str = "") -> None:
        self.repo_head = repo_head or self.repo_head
        self.last_checkpoint = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": STATE_SCHEMA,
            "last_checkpoint": self.last_checkpoint,
            "repo_head": self.repo_head,
            "tasks": [s.to_dict() for s in self.tasks.values()],
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        data = json.dumps(payload, indent=2) + "\n"
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp, self.path)

    def get(self, task_id: str) -> TaskRuntimeState:
        if task_id not in self.tasks:
            self.tasks[task_id] = TaskRuntimeState(task_id=task_id)
        return self.tasks[task_id]

    def transition(self, task_id: str, new_state: str) -> None:
        s = self.get(task_id)
        allowed = ALLOWED_TRANSITIONS.get(s.state, set())
        if new_state != s.state and new_state not in allowed:
            raise TransitionError(
                f"illegal transition {s.state} → {new_state} for {task_id}"
            )
        s.state = new_state
        s.last_classification = new_state
        s.updated_at = _now()

    def begin(self, task_id: str) -> None:
        self.transition(task_id, TaskState.IN_PROGRESS.value)
        s = self.get(task_id)
        s.in_progress = True
        s.attempts += 1

    def enter_validating(self, task_id: str) -> None:
        self.transition(task_id, TaskState.VALIDATING.value)
        self.get(task_id).in_progress = False

    def finish_pass(self, task_id: str, evidence_id: str) -> None:
        self.transition(task_id, TaskState.PASS.value)
        s = self.get(task_id)
        s.validated_pass = True
        s.in_progress = False
        if evidence_id and evidence_id not in s.evidence_refs:
            s.evidence_refs.append(evidence_id)

    def finish_fail(self, task_id: str, evidence_id: str) -> None:
        # FAIL is reachable from IN_PROGRESS or VALIDATING.
        s = self.get(task_id)
        if s.state == TaskState.IN_PROGRESS.value:
            self.transition(task_id, TaskState.FAIL.value)
        elif s.state == TaskState.VALIDATING.value:
            self.transition(task_id, TaskState.FAIL.value)
        else:
            raise TransitionError(
                f"cannot FAIL from {s.state} for {task_id}"
            )
        s = self.get(task_id)
        s.in_progress = False
        if evidence_id and evidence_id not in s.evidence_refs:
            s.evidence_refs.append(evidence_id)

    def demote_unbacked_pass(self, authoritative: set) -> list:
        demoted = []
        for tid, st in self.tasks.items():
            if st.validated_pass and tid not in authoritative:
                st.validated_pass = False
                st.state = TaskState.DISCOVERED.value
                st.in_progress = False
                st.updated_at = _now()
                demoted.append(tid)
        return demoted
