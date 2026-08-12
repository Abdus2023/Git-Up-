"""Task, contract, and state types (components A, C, D)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class TaskState(str, Enum):
    DISCOVERED = "DISCOVERED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    VALIDATING = "VALIDATING"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


TERMINAL = {TaskState.PASS, TaskState.REJECTED, TaskState.DEFERRED}

ALLOWED_TRANSITIONS = {
    "DISCOVERED": {"READY", "BLOCKED", "REJECTED", "DEFERRED"},
    "READY": {"IN_PROGRESS", "BLOCKED", "REJECTED", "DEFERRED"},
    "IN_PROGRESS": {"VALIDATING", "FAIL", "BLOCKED"},
    "VALIDATING": {"PASS", "FAIL"},
    "FAIL": {"READY", "BLOCKED", "IN_PROGRESS", "DISCOVERED"},
    "BLOCKED": {"READY", "BLOCKED", "REJECTED", "DEFERRED"},
    "PASS": set(),
    "REJECTED": set(),
    "DEFERRED": set(),
}


class BlockerCategory(str, Enum):
    INSUFFICIENT_TASK_DEFINITION = "INSUFFICIENT_TASK_DEFINITION"
    SPECIFICATION_CONFLICT = "SPECIFICATION_CONFLICT"
    INCOMPLETE_SPECIFICATION = "INCOMPLETE_SPECIFICATION"
    DEPENDENCY = "DEPENDENCY"
    TOOLCHAIN = "TOOLCHAIN"
    ARCHITECTURE = "ARCHITECTURE"
    PROVISIONING = "PROVISIONING"
    AUTHORIZATION = "AUTHORIZATION"
    ENVIRONMENT = "ENVIRONMENT"
    TRACEABILITY = "TRACEABILITY"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    IMPLEMENTATION = "IMPLEMENTATION"
    TEST = "TEST"
    INTEGRATION = "INTEGRATION"


PRECEDENCE = [
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


@dataclass
class AuthorityRef:
    path: str
    anchor: str = ""
    requirement_id: str = ""


@dataclass
class DependencyRef:
    ref: str
    required_state: str = "PASS"


@dataclass
class DeclaredBlocker:
    category: str
    satisfied: bool
    evidence: str = ""
    detail: str = ""


@dataclass
class ValidationCommand:
    id: str
    command: str
    expected_exit: int = 0
    purpose: str = ""


@dataclass
class AcceptanceCriterion:
    id: str
    statement: str
    validator: str = ""


@dataclass
class ExpectedOutput:
    path: str
    sha256: str


@dataclass
class Tool:
    id: str
    available: bool = False
    binary: str = ""
    version: str = ""
    evidence: str = ""
    detail: str = ""


@dataclass
class CoverageEntry:
    task_id: str
    obligations: list = field(default_factory=list)


@dataclass
class Requirement:
    id: str
    specification_refs: list = field(default_factory=list)
    coverage: list = field(default_factory=list)


@dataclass
class Task:
    id: str
    title: str = ""
    description: str = ""
    scope: str = ""
    priority: int = 100
    order: int = 0
    source_authority: list = field(default_factory=list)
    requirement_refs: list = field(default_factory=list)
    specification_refs: list = field(default_factory=list)
    implementation_targets: list = field(default_factory=list)
    prohibited_scope: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    required_tools: list = field(default_factory=list)
    allowed_tools: list = field(default_factory=list)
    validation_commands: list = field(default_factory=list)
    acceptance_criteria: list = field(default_factory=list)
    expected_outputs: list = field(default_factory=list)
    declared_blockers: list = field(default_factory=list)
    spec_conflicts: list = field(default_factory=list)
    spec_gaps: list = field(default_factory=list)
    rejected: bool = False
    deferred: bool = False


@dataclass
class Classification:
    task_id: str
    effective_state: str
    ready: bool = False
    blocker_class: Optional[str] = None
    reasons: list = field(default_factory=list)
    detail: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "effective_state": self.effective_state,
            "ready": self.ready,
            "blocker_class": self.blocker_class,
            "reasons": list(self.reasons),
            "detail": list(self.detail),
        }


@dataclass
class Contract:
    schema_version: str
    source_path: str
    tasks: List[Task]
    tools: List[Tool]
    requirements: List[Requirement]
    timeout_seconds: int = 600
    policy: dict = field(default_factory=dict)

    def task_by_id(self) -> dict:
        return {t.id: t for t in self.tasks}

    def tool_map(self) -> dict:
        return {t.id: t for t in self.tools}
