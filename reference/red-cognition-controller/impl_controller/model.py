"""Task model, schema, and enums for the Implementation Execution Controller.

The schema is the minimum necessary to express an implementation task with
full traceability. Missing authoritative fields never yield guessed values;
they surface as ``INSUFFICIENT_TASK_DEFINITION`` in the dependency engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskState(str, Enum):
    """Lifecycle states a task may hold."""

    DISCOVERED = "DISCOVERED"
    PLANNED = "PLANNED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    PASS = "PASS"          # terminal success — counts as a satisfied dependency
    FAIL = "FAIL"          # validation failed (non-terminal; reclassified each cycle)
    BLOCKED = "BLOCKED"    # cannot proceed (recomputed each cycle)
    DEFERRED = "DEFERRED"  # parked by explicit decision
    REJECTED = "REJECTED"  # explicitly rejected


# States that override engine recomputation (sticky).
TERMINAL_STATES = {TaskState.PASS, TaskState.REJECTED, TaskState.DEFERRED}
# States the engine reclassifies from data every cycle.
RECLASSIFIABLE_STATES = {
    TaskState.DISCOVERED, TaskState.PLANNED, TaskState.READY,
    TaskState.IN_PROGRESS, TaskState.FAIL, TaskState.BLOCKED,
}


class BlockerCategory(str, Enum):
    """Failure / blocker classes. Specification sub-classes are kept distinct."""

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


# Canonical failure classes (coarser than BlockerCategory) used in evidence.
FAILURE_CLASS = {
    BlockerCategory.INSUFFICIENT_TASK_DEFINITION: "INSUFFICIENT_TASK_DEFINITION",
    BlockerCategory.SPECIFICATION_CONFLICT: "SPECIFICATION",
    BlockerCategory.INCOMPLETE_SPECIFICATION: "SPECIFICATION",
    BlockerCategory.DEPENDENCY: "DEPENDENCY",
    BlockerCategory.TOOLCHAIN: "TOOLCHAIN",
    BlockerCategory.ARCHITECTURE: "ARCHITECTURE",
    BlockerCategory.PROVISIONING: "PROVISIONING",
    BlockerCategory.AUTHORIZATION: "AUTHORIZATION",
    BlockerCategory.ENVIRONMENT: "ENVIRONMENT",
    BlockerCategory.TRACEABILITY: "TRACEABILITY",
    BlockerCategory.INFRASTRUCTURE: "INFRASTRUCTURE",
    BlockerCategory.IMPLEMENTATION: "IMPLEMENTATION",
    BlockerCategory.TEST: "TEST",
    BlockerCategory.INTEGRATION: "INTEGRATION",
}


@dataclass
class AuthorityRef:
    """A reference to an authoritative document in the repository."""

    doc: str                       # repository-relative path
    anchor: str = ""               # section / line / requirement id
    requirement_id: str = ""


@dataclass
class DependencyRef:
    """A dependency on another task reaching a required state."""

    ref: str                       # referenced task_id
    required_state: str = "PASS"   # typically PASS


@dataclass
class DeclaredBlocker:
    """An evidence-grounded blocker declared on the task.

    These preserve authoritative human classifications (e.g. ARCHITECTURE,
    PROVISIONING, AUTHORIZATION) without inventing them; the engine never
    auto-satisfies a declared blocker.
    """

    category: str                  # BlockerCategory value
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
    criterion: str
    validator: str = ""   # validation command id that covers this criterion
    # (opt-in semantic coverage; when any criterion declares a validator the
    # controller enforces full criterion<->validator coverage).


@dataclass
class ExpectedOutput:
    """A required implementation output that must exist with a declared hash."""
    path: str
    sha256: str


@dataclass
class CoverageEntry:
    """A declared obligation binding: requirement obligation -> task."""
    task_id: str
    obligations: list = field(default_factory=list)   # list[str]


@dataclass
class Requirement:
    """An authoritative requirement with explicit coverage declarations."""
    id: str
    specification_refs: list = field(default_factory=list)   # list[str]
    coverage: list = field(default_factory=list)             # list[CoverageEntry]


@dataclass
class Tool:
    id: str
    available: bool
    evidence: str = ""
    detail: str = ""
    binary: str = ""     # executable name used to VERIFY availability on PATH
    version: str = ""    # declared tool version (semantic contract input)


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

# Fields required for a task to be READY (else INSUFFICIENT_TASK_DEFINITION).
REQUIRED_FOR_DEFINITION = ("source_authority", "requirement_refs",
                           "validation_commands", "acceptance_criteria")


@dataclass
class Task:
    task_id: str
    title: str
    description: str
    priority: int = 100                 # lower = higher priority
    plan_order: int = 0                 # plan-imposed ordering (tie-break)
    scope: str = ""
    source_authority: list = field(default_factory=list)   # list[AuthorityRef]
    requirement_refs: list = field(default_factory=list)   # list[str]
    specification_refs: list = field(default_factory=list) # list[AuthorityRef]
    implementation_targets: list = field(default_factory=list)  # files allowed to change
    dependency_refs: list = field(default_factory=list)    # list[DependencyRef]
    required_tools: list = field(default_factory=list)     # tool ids
    validation_commands: list = field(default_factory=list)  # list[ValidationCommand]
    acceptance_criteria: list = field(default_factory=list)  # list[AcceptanceCriterion]
    evidence_refs: list = field(default_factory=list)
    spec_conflicts: list = field(default_factory=list)     # conflict ids / descriptions
    spec_gaps: list = field(default_factory=list)          # gap ids / descriptions
    declared_blockers: list = field(default_factory=list)  # list[DeclaredBlocker]
    allowed_tools: list = field(default_factory=list)
    prohibited_scope: list = field(default_factory=list)   # files/areas that must NOT change
    expected_outputs: list = field(default_factory=list)  # list[ExpectedOutput]
    provenance: str = ""
    rejected: bool = False
    deferred: bool = False

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "plan_order": self.plan_order,
            "scope": self.scope,
            "source_authority": [a.__dict__ for a in self.source_authority],
            "requirement_refs": list(self.requirement_refs),
            "specification_refs": [a.__dict__ for a in self.specification_refs],
            "implementation_targets": list(self.implementation_targets),
            "dependency_refs": [d.__dict__ for d in self.dependency_refs],
            "required_tools": list(self.required_tools),
            "validation_commands": [v.__dict__ for v in self.validation_commands],
            "acceptance_criteria": [a.__dict__ for a in self.acceptance_criteria],
            "evidence_refs": list(self.evidence_refs),
            "spec_conflicts": list(self.spec_conflicts),
            "spec_gaps": list(self.spec_gaps),
            "declared_blockers": [b.__dict__ for b in self.declared_blockers],
            "allowed_tools": list(self.allowed_tools),
            "prohibited_scope": list(self.prohibited_scope),
            "expected_outputs": [e.__dict__ for e in self.expected_outputs],
            "provenance": self.provenance,
            "rejected": self.rejected,
            "deferred": self.deferred,
        }


@dataclass
class Classification:
    """Result of the dependency engine for one task."""

    task_id: str
    effective_state: str                # TaskState value
    ready: bool = False
    blocker_class: Optional[str] = None  # primary BlockerCategory value
    reasons: list = field(default_factory=list)   # all applicable BlockerCategory values
    detail: list = field(default_factory=list)    # human-readable reason strings

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "effective_state": self.effective_state,
            "ready": self.ready,
            "blocker_class": self.blocker_class,
            "reasons": list(self.reasons),
            "detail": list(self.detail),
        }


class ToolRegistry:
    """Maps tool id -> Tool with availability (evidence-grounded)."""

    def __init__(self, tools=None):
        self._tools = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: Tool) -> None:
        self._tools[tool.id] = tool

    def get(self, tool_id: str) -> Optional[Tool]:
        return self._tools.get(tool_id)

    def available(self, tool_id: str) -> bool:
        t = self._tools.get(tool_id)
        return bool(t and t.available)

    def to_dict(self) -> dict:
        return {tid: {"available": t.available, "binary": t.binary,
                      "version": t.version, "evidence": t.evidence,
                      "detail": t.detail}
                for tid, t in self._tools.items()}
