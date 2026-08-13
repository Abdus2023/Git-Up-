"""Implementation Execution Controller — infrastructure package.

Transforms an implementation plan (task manifest) into a deterministic,
fail-closed executable task queue. This package implements NO Red/Cognition
product features; it only models, classifies, schedules, contracts, and
records evidence for implementation tasks.

Design constraints honored:
  * Standard library only (no PyYAML, no pytest) — runs on CPython 3.11.
  * Fail closed: unknown / insufficient / conflicting tasks are BLOCKED,
    never silently READY or auto-executed.
  * BLOCKED tasks are never automatically executed.
  * Reuses existing repository result-object conventions
    (``{..., "result": "PASS|FAIL", "errors": [...]}``).
"""

from .model import (
    Task, Tool, AuthorityRef, DependencyRef, DeclaredBlocker,
    ValidationCommand, AcceptanceCriterion, ToolRegistry,
    TaskState, BlockerCategory, Classification,
    TERMINAL_STATES, RECLASSIFIABLE_STATES,
)
from .manifest import Manifest, load_manifest, ManifestError
from .engine import classify_all, classify_task, blocking_chain, SelfBlockers
from .queue import build_ready_queue, dependency_depth
from .contract import build_execution_contract
from .evidence import EvidenceRecord, EvidenceLog, EvidenceError
from .checkpoint import StateStore, TaskRuntimeState
from .safety import validate_command, validate_targets, SafetyError, within_repo
from .locking import FileLock, LockAcquisitionError
from .provenance import (
    provenance_context, default_context, manifest_identity, repo_identity,
    repo_head, contract_identity_for, closure_gaps, VALIDATOR_IDENTITY,
)
from .controller import Controller, ControllerResult

__all__ = [
    "Task", "Tool", "AuthorityRef", "DependencyRef", "DeclaredBlocker",
    "ValidationCommand", "AcceptanceCriterion", "ToolRegistry",
    "TaskState", "BlockerCategory", "Classification",
    "TERMINAL_STATES", "RECLASSIFIABLE_STATES",
    "Manifest", "load_manifest", "ManifestError",
    "classify_all", "classify_task", "blocking_chain", "SelfBlockers",
    "build_ready_queue", "dependency_depth",
    "build_execution_contract",
    "EvidenceRecord", "EvidenceLog", "EvidenceError",
    "StateStore", "TaskRuntimeState",
    "validate_command", "validate_targets", "SafetyError", "within_repo",
    "FileLock", "LockAcquisitionError",
    "provenance_context", "default_context", "manifest_identity",
    "repo_identity", "repo_head", "contract_identity_for", "closure_gaps",
    "VALIDATOR_IDENTITY",
    "Controller", "ControllerResult",
]

__version__ = "2.0.0"
