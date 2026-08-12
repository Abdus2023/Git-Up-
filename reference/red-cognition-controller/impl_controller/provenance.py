"""Provenance identity model for the Stage-5 pipeline.

The central invariant: a task may reach PASS only when every provenance edge is
valid, identity-consistent, repository-consistent, temporally valid, and
cryptographically bound. A successful command alone is NEVER sufficient.

contract_id cryptographically binds the immutable execution inputs:

    contract_id = SHA256(canonical(
        validator, repository_identity, HEAD, manifest_identity,
        task_id, requirements, specifications, dependency_state,
        tools, commands(+expected_exit), targets, prohibited, criteria))

Evidence records carry contract_id (+ repository_identity, HEAD, manifest_hash,
validator) so they cannot be replayed across tasks, repos, commits, or
manifests. PASS requires a chain-verified PASS evidence whose contract_id
matches the task's CURRENT contract_id, plus a closed traceability chain.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

VALIDATOR_IDENTITY = "impl_controller"


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Repository identity
# ---------------------------------------------------------------------------

def repo_head(repo_root) -> str:
    """Current git HEAD commit, or '' if not a git repo."""
    try:
        out = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def repo_identity(repo_root) -> str:
    """Stable per-working-tree identity (UUID stored in the repo).

    No network. Two different checkouts get different identities, so evidence
    generated in one cannot be replayed into another. If the identity file
    cannot be written, fall back to a deterministic path hash.
    """
    root = Path(repo_root).resolve()
    iddir = root / ".impl_controller"
    idfile = iddir / "repo.identity"
    try:
        if idfile.is_file():
            existing = idfile.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        iddir.mkdir(parents=True, exist_ok=True)
        ident = "repo-" + uuid.uuid4().hex
        idfile.write_text(ident, encoding="utf-8")
        return ident
    except OSError:
        return "path-" + sha256_hex(str(root).encode("utf-8"))[:32]


# ---------------------------------------------------------------------------
# Manifest identity
# ---------------------------------------------------------------------------

def _canonical_task_dict(t) -> dict:
    """Order-independent (canonical) task representation for identity hashing.

    Every multi-valued field whose declaration order is non-semantic is sorted,
    so reordering requirements/specs/tools/commands/deps/etc. does NOT change
    identity. Scalar/semantic fields (task_id, title, description, priority,
    scope, provenance, rejected, deferred) are preserved.
    """
    d = t.to_dict()
    def keyf(x):
        return json.dumps(x, sort_keys=True, ensure_ascii=False)
    for k in ("requirement_refs", "required_tools", "allowed_tools",
              "implementation_targets", "prohibited_scope", "spec_conflicts",
              "spec_gaps", "evidence_refs"):
        d[k] = sorted(d.get(k, []))
    for k in ("specification_refs", "source_authority", "dependency_refs",
              "declared_blockers", "validation_commands", "acceptance_criteria",
              "expected_outputs"):
        d[k] = sorted(d.get(k, []), key=keyf)
    return d


def manifest_identity(manifest) -> str:
    """SHA-256 over the canonical (order-independent) manifest content.

    Changes if any semantic task field or tool-registry entry changes. Reordering
    non-semantic lists (requirements/specs/tools/commands/dependencies) does NOT
    change identity. Excludes nondeterministic documentation fields.
    """
    payload = {
        "schema_version": manifest.schema_version,
        "project": manifest.project,
        "tasks": [_canonical_task_dict(t) for t in manifest.tasks],
        "tool_registry": manifest.tool_registry.to_dict(),
    }
    return sha256_hex(canonical(payload))


# ---------------------------------------------------------------------------
# Command identity & Contract identity
# ---------------------------------------------------------------------------

def command_identity(vc) -> str:
    """Deterministic identity of a single validation command (order-independent).

    Validation commands are independent checks that ALL must pass; their
    declaration order is non-semantic and canonicalized away. Content
    (id/command/expected_exit) IS semantic.
    """
    return sha256_hex(canonical({"id": vc.id, "command": vc.command,
                                 "expected_exit": vc.expected_exit}))


def criterion_attestations(task, contract_id: str, task_evidence: list,
                           ctx: dict) -> list:
    """Per-criterion attestation view for STRICT tasks (derived; reuses command
    evidence + declared criterion->validator coverage — no new storage, no
    inference). Returns one entry per criterion; an attested criterion carries a
    deterministic ``criterion_evidence_id`` bound to (contract, task, criterion,
    validator, command, result). Legacy tasks (no declared validators) return [].
    """
    if not any(c.validator for c in task.acceptance_criteria):
        return []
    cmd_by_id = {vc.id: vc for vc in task.validation_commands}
    pass_cmd_ids = {e.get("command_id") for e in task_evidence
                    if e.get("contract_id") == contract_id
                    and e.get("task_id") == task.task_id
                    and e.get("result") == "PASS"}
    out = []
    for c in task.acceptance_criteria:
        vc = cmd_by_id.get(c.validator)
        cmd_id = command_identity(vc) if vc else None
        attested = bool(cmd_id and cmd_id in pass_cmd_ids)
        ce_id = ""
        if attested:
            ce_id = sha256_hex(canonical({
                "contract_id": contract_id, "task_id": task.task_id,
                "criterion_id": c.id, "validator": c.validator,
                "command_id": cmd_id, "result": "PASS",
            }))
        out.append({"criterion_id": c.id, "validator": c.validator,
                    "command_id": cmd_id or "", "attested": attested,
                    "criterion_evidence_id": ce_id,
                    "gap": None if attested else "NO_CRITERION_ATTESTATION"})
    return out


def contract_identity_for(task, satisfied_deps: set, ctx: dict) -> str:
    """Deterministic contract_id for a task under a provenance context.

    ``satisfied_deps`` is the set of PASS dependency task_ids (dependency_state).
    ``ctx`` = {"repo_identity", "head", "manifest_hash", "tool_versions"}.

    All multi-valued inputs are canonicalized (sorted) so declaration order and
    JSON key order do NOT affect identity. Command ORDER is non-semantic
    (independent checks); command CONTENT is semantic.
    """
    dep_state = sorted(d.ref for d in task.dependency_refs
                       if d.required_state == "PASS" and d.ref in satisfied_deps)
    tool_versions = ctx.get("tool_versions", {}) or {}
    payload = {
        "validator": VALIDATOR_IDENTITY,
        "repository": ctx.get("repo_identity", ""),
        "head": ctx.get("head", ""),
        "manifest": ctx.get("manifest_hash", ""),
        "task_id": task.task_id,
        "requirements": sorted(task.requirement_refs),
        "specifications": sorted(f"{a.doc}|{a.anchor}" for a in task.specification_refs),
        "targets": sorted(task.implementation_targets),
        "prohibited": sorted(task.prohibited_scope),
        # tool IDENTITY is semantic: id + declared version (PATH-presence is
        # enforced separately at classification time).
        "tools": sorted((tid, tool_versions.get(tid, ""))
                        for tid in task.required_tools),
        "allowed_tools": sorted(task.allowed_tools),
        # commands: order-INDEPENDENT (sorted set of command identities);
        # content (id/command/expected_exit) is semantic.
        "commands": sorted(command_identity(v) for v in task.validation_commands),
        "criteria": sorted((a.id, a.validator) for a in task.acceptance_criteria),
        "expected_outputs": sorted((e.path, e.sha256) for e in task.expected_outputs),
        "dependency_state": dep_state,
    }
    return sha256_hex(canonical(payload))


# ---------------------------------------------------------------------------
# Traceability closure
# ---------------------------------------------------------------------------

def closure_gaps(task, contract_id: str, task_evidence: list, ctx: dict) -> list:
    """Return provenance gaps that prevent PASS (empty list == closed chain).

    PASS requires EVERY validation command to have a chain-verified PASS
    evidence record bound to the task's CURRENT contract_id and task_id (with
    matching command_id). A single passing command is never sufficient when a
    task declares multiple commands.
    """
    gaps = []
    if not task.requirement_refs:
        gaps.append("requirement missing (requirement -> specification)")
    if not task.specification_refs:
        gaps.append("specification missing (specification -> task)")
    if not task.validation_commands:
        gaps.append("validation missing (task -> validation)")
    if not task.acceptance_criteria:
        gaps.append("acceptance criteria missing (validation -> acceptance)")
    # evidence edge: strict tasks use per-CRITERION attestation closure; legacy
    # tasks use per-COMMAND closure. (Strict coverage makes these equivalent,
    # but per-criterion yields explicit criterion->evidence edges + ids.)
    if any(c.validator for c in task.acceptance_criteria):
        for att in criterion_attestations(task, contract_id, task_evidence, ctx):
            if att["gap"]:
                gaps.append(f"criterion '{att['criterion_id']}' {att['gap']} "
                            "(criterion -> evidence)")
    else:
        pass_cmd_ids = {e.get("command_id") for e in task_evidence
                        if e.get("contract_id") == contract_id
                        and e.get("task_id") == task.task_id
                        and e.get("result") == "PASS"}
        for vc in task.validation_commands:
            if command_identity(vc) not in pass_cmd_ids:
                gaps.append(f"command '{vc.id}' has no PASS evidence bound to "
                            "current contract_id")
    # validator binding
    for e in task_evidence:
        if e.get("contract_id") == contract_id and e.get("validator") != VALIDATOR_IDENTITY:
            gaps.append("evidence validator identity mismatch")
            break
    return gaps


def provenance_context(repo_root, manifest) -> dict:
    """Build the provenance context used across a single run."""
    return {
        "repo_identity": repo_identity(repo_root),
        "head": repo_head(repo_root),
        "manifest_hash": manifest_identity(manifest),
        "validator": VALIDATOR_IDENTITY,
        "tool_versions": {tid: t.version for tid, t in manifest.tool_registry._tools.items()},
    }


def default_context() -> dict:
    return {"repo_identity": "", "head": "", "manifest_hash": "",
            "validator": VALIDATOR_IDENTITY, "tool_versions": {}}


# ---------------------------------------------------------------------------
# Cross-task requirement coverage (Phase 25) — DERIVED, never authoritative
# ---------------------------------------------------------------------------

def coverage_identity(requirements) -> str:
    """Deterministic identity over the declared requirement coverage graph.
    Requirement declaration order is non-semantic (sorted by id)."""
    payload = [{"id": r.id,
                "specification_refs": sorted(r.specification_refs),
                "coverage": sorted((c.task_id, tuple(sorted(c.obligations)))
                                   for c in r.coverage)}
               for r in (requirements or [])]
    payload = sorted(payload, key=lambda r: r["id"])
    return sha256_hex(canonical(payload))


def requirement_statuses(requirements, pass_task_ids: set) -> list:
    """Derived requirement ledger. TASK PASS does NOT imply REQUIREMENT SATISFIED
    unless ALL declared coverage tasks are PASS. This is a DERIVED view — it can
    never authorize task PASS. The ledger is recomputed each run from
    authoritative task PASS state; it is never trusted as authority."""
    out = []
    for r in (requirements or []):
        tasks = [c.task_id for c in r.coverage]
        if not tasks:
            out.append({"requirement_id": r.id, "status": "NO_COVERAGE",
                        "tasks": [], "pass_tasks": []})
            continue
        pass_t = [t for t in tasks if t in pass_task_ids]
        if len(pass_t) == len(tasks):
            status = "SATISFIED"
        elif pass_t:
            status = "PARTIAL"
        else:
            status = "BLOCKED"
        out.append({"requirement_id": r.id, "status": status,
                    "tasks": tasks, "pass_tasks": pass_t})
    return out
