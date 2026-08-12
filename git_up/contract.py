"""Load and structurally validate an implementation contract (component A)."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

_SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")

from . import CONTRACT_SCHEMA
from .errors import ContractError
from .model import (
    AcceptanceCriterion, AuthorityRef, Contract, CoverageEntry,
    DeclaredBlocker, DependencyRef, ExpectedOutput, Requirement, Task, Tool,
    ValidationCommand,
)
from .safety import validate_targets


def _require_unique(ids, label: str) -> None:
    ids = [str(i) for i in ids]
    if any(not i for i in ids):
        raise ContractError(f"empty {label}")
    if len(ids) != len(set(ids)):
        raise ContractError(f"duplicate {label}")


def coerce_command(raw, *, where: str, allow_empty: bool = False) -> str:
    """Normalize spec 05 argv-or-string into a single command string.

    A list is joined with ``shlex.join`` so ``shlex.split`` at execute
    time recovers the same tokens. Invalid types fail closed.
    """
    if raw is None:
        cmd = ""
    elif isinstance(raw, str):
        cmd = raw
    elif isinstance(raw, (list, tuple)):
        if not raw:
            cmd = ""
        else:
            tokens = []
            for i, tok in enumerate(raw):
                if not isinstance(tok, str):
                    raise ContractError(f"{where}: argv[{i}] must be a string")
                if tok == "":
                    raise ContractError(f"{where}: argv[{i}] is empty")
                tokens.append(tok)
            cmd = shlex.join(tokens)
    else:
        raise ContractError(f"{where}: command must be a string or argv list")
    if not allow_empty and not str(cmd).strip():
        raise ContractError(f"{where}: empty command")
    return cmd


def _auth(item, where="authority") -> AuthorityRef:
    if isinstance(item, str):
        return AuthorityRef(path=item)
    if not isinstance(item, dict):
        raise ContractError(f"{where} must be a string or object")
    return AuthorityRef(
        path=str(item.get("path") or item.get("doc") or ""),
        anchor=str(item.get("anchor") or ""),
        requirement_id=str(item.get("requirement_id") or ""),
    )


def _task(raw: dict) -> Task:
    if not isinstance(raw, dict) or not raw.get("id"):
        raise ContractError("task missing id")
    tid = str(raw.get("id") or "")
    crits = []
    for c in raw.get("acceptance_criteria") or []:
        if not isinstance(c, dict):
            raise ContractError(f"task {tid}: acceptance_criteria entries must be objects")
        crits.append(AcceptanceCriterion(
            id=str(c.get("id") or ""),
            statement=str(c.get("statement") or c.get("criterion") or ""),
            validator=str(c.get("validator") or ""),
        ))
    cmds = []
    for v in raw.get("validation_commands") or []:
        if not isinstance(v, dict):
            raise ContractError(f"task {tid}: validation_commands entries must be objects")
        cid = str(v.get("id") or "")
        cmd = coerce_command(
            v.get("command"),
            where=f"task {tid}: validation command {cid!r}",
            allow_empty=not cid,
        )
        if cid and not cmd.strip():
            raise ContractError(
                f"task {tid}: validation command {cid!r} has an empty command"
            )
        cmds.append(ValidationCommand(
            id=cid,
            command=cmd,
            expected_exit=int(v.get("expected_exit", 0)),
            purpose=str(v.get("purpose") or ""),
        ))
    deps = []
    for d in raw.get("dependencies") or raw.get("dependency_refs") or []:
        if isinstance(d, str):
            deps.append(DependencyRef(ref=d, required_state="PASS"))
            continue
        if not isinstance(d, dict):
            raise ContractError(f"task {tid}: dependency must be a string or object")
        deps.append(DependencyRef(
            ref=str(d.get("ref") or d.get("id") or ""),
            required_state=str(d.get("required_state") or "PASS"),
        ))
    blockers = []
    for b in raw.get("declared_blockers") or []:
        if not isinstance(b, dict):
            raise ContractError(f"task {tid}: declared_blockers entries must be objects")
        blockers.append(DeclaredBlocker(
            category=str(b.get("category") or ""),
            satisfied=bool(b.get("satisfied", False)),
            evidence=str(b.get("evidence") or ""),
            detail=str(b.get("detail") or ""),
        ))
    eouts = []
    for e in raw.get("expected_outputs") or []:
        if not isinstance(e, dict):
            raise ContractError(f"task {tid}: expected_outputs entries must be objects")
        path = str(e.get("path") or "")
        digest = str(e.get("sha256") or "")
        if not path or not digest:
            raise ContractError(
                f"task {tid}: expected_outputs entries need path and sha256"
            )
        if not _SHA256_HEX.match(digest):
            raise ContractError(
                f"task {tid}: expected_outputs sha256 must be 64 hex characters"
            )
        eouts.append(ExpectedOutput(path=path, sha256=digest.lower()))
    _require_unique((c.id for c in cmds), f"task {tid} validation command id")
    _require_unique((c.id for c in crits), f"task {tid} acceptance criterion id")
    return Task(
        id=str(raw["id"]),
        title=str(raw.get("title") or ""),
        description=str(raw.get("description") or ""),
        scope=str(raw.get("scope") or ""),
        priority=int(raw.get("priority", 100)),
        order=int(raw.get("order") or raw.get("plan_order") or 0),
        source_authority=[
            _auth(a, f"task {tid} source_authority")
            for a in (raw.get("source_authority") or [])
        ],
        requirement_refs=[str(x) for x in (raw.get("requirement_refs") or [])],
        specification_refs=[
            _auth(a, f"task {tid} specification_refs")
            for a in (raw.get("specification_refs") or [])
        ],
        implementation_targets=[str(x) for x in (raw.get("implementation_targets") or [])],
        prohibited_scope=[str(x) for x in (raw.get("prohibited_scope") or [])],
        dependencies=deps,
        required_tools=[str(x) for x in (raw.get("required_tools") or [])],
        allowed_tools=[str(x) for x in (raw.get("allowed_tools") or [])],
        validation_commands=cmds,
        acceptance_criteria=crits,
        expected_outputs=eouts,
        declared_blockers=blockers,
        spec_conflicts=list(raw.get("spec_conflicts") or []),
        spec_gaps=list(raw.get("spec_gaps") or []),
        rejected=bool(raw.get("rejected", False)),
        deferred=bool(raw.get("deferred", False)),
    )


def load_contract(path) -> Contract:
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ContractError(f"cannot load contract {p}: {e}") from e
    if not isinstance(raw, dict):
        raise ContractError("contract must be a JSON object")
    ver = str(raw.get("schema_version") or "")
    if ver != CONTRACT_SCHEMA:
        raise ContractError(
            f"unknown schema_version {ver!r}; expected {CONTRACT_SCHEMA!r}"
        )
    policy = raw.get("policy") or {}
    if str(policy.get("failure_mode") or "fail_closed") != "fail_closed":
        raise ContractError("policy.failure_mode must be fail_closed")
    if str(policy.get("concurrency") or "exclusive") != "exclusive":
        raise ContractError("policy.concurrency must be exclusive")

    tools = []
    for t in raw.get("tools") or raw.get("tool_registry") or []:
        if not isinstance(t, dict):
            raise ContractError("tools entries must be objects")
        if not t.get("id"):
            raise ContractError("tool missing id")
        tools.append(Tool(
            id=str(t.get("id") or ""),
            available=bool(t.get("available", False)),
            binary=str(t.get("binary") or t.get("id") or ""),
            version=str(t.get("version") or ""),
            evidence=str(t.get("evidence") or ""),
            detail=str(t.get("detail") or ""),
        ))
    _require_unique((t.id for t in tools), "tool id")

    reqs = []
    for r in raw.get("requirements") or []:
        if not isinstance(r, dict):
            raise ContractError("requirements entries must be objects")
        if not r.get("id"):
            raise ContractError("requirement missing id")
        cov = []
        for c in r.get("coverage") or []:
            if not isinstance(c, dict):
                raise ContractError(
                    f"requirement {r['id']}: coverage entries must be objects"
                )
            cov.append(CoverageEntry(
                task_id=str(c.get("task_id") or ""),
                obligations=list(c.get("obligations") or []),
            ))
        reqs.append(Requirement(
            id=str(r.get("id") or ""),
            specification_refs=[str(x) for x in (r.get("specification_refs") or [])],
            coverage=cov,
        ))
    _require_unique((r.id for r in reqs), "requirement id")

    tasks_raw = raw.get("tasks")
    if tasks_raw is None and isinstance(raw.get("task"), dict):
        tasks_raw = [raw["task"]]
    if not tasks_raw:
        raise ContractError("contract has no tasks")
    tasks = [_task(t) for t in tasks_raw]
    _require_unique((t.id for t in tasks), "task id")
    task_ids = {t.id for t in tasks}
    for r in reqs:
        for c in r.coverage:
            if not c.task_id:
                raise ContractError(f"requirement {r.id}: coverage missing task_id")
            if c.task_id not in task_ids:
                raise ContractError(
                    f"requirement {r.id}: coverage task_id {c.task_id!r} "
                    "is not a declared task"
                )

    timeout = int((policy.get("timeout_seconds") if isinstance(policy, dict) else None)
                  or raw.get("timeout_seconds") or 600)
    prov = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}
    repo = raw.get("repository") if isinstance(raw.get("repository"), dict) else {}
    auth_block = raw.get("authority") if isinstance(raw.get("authority"), dict) else {}
    sources_raw = auth_block.get("sources")
    if sources_raw is None:
        sources_raw = raw.get("authority_sources") or []
    if sources_raw and not isinstance(sources_raw, list):
        raise ContractError("authority.sources must be a list")
    authority_sources = [
        _auth(item, "authority.sources") for item in (sources_raw or [])
    ]
    return Contract(
        schema_version=ver,
        source_path=str(p.resolve()),
        tasks=tasks,
        tools=tools,
        requirements=reqs,
        timeout_seconds=timeout,
        policy=dict(policy) if isinstance(policy, dict) else {},
        provenance={
            "producer": str(prov.get("producer") or ""),
            "source_identity": str(prov.get("source_identity") or ""),
            "parent_contracts": list(prov.get("parent_contracts") or []),
        },
        repository=dict(repo),
        authority_sources=authority_sources,
    )


def validate_confinement(contract: Contract, repo_root) -> list:
    """Fail-closed path checks (spec 06 §4 / 16 §4)."""
    errors = []
    for t in contract.tasks:
        for field, vals in (
            ("implementation_targets", t.implementation_targets),
            ("prohibited_scope", t.prohibited_scope),
            ("source_authority", [a.path for a in t.source_authority]),
            ("specification_refs", [a.path for a in t.specification_refs]),
            ("expected_outputs", [e.path for e in t.expected_outputs]),
        ):
            for tgt, reason in validate_targets(vals, repo_root, field):
                errors.append(f"{t.id}.{field}: {tgt}: {reason}")
    source_paths = [
        a.path for a in (contract.authority_sources or []) if a.path
    ]
    for tgt, reason in validate_targets(
        source_paths, repo_root, "authority.sources",
    ):
        errors.append(f"authority.sources: {tgt}: {reason}")
    for req in contract.requirements:
        req_paths = [p for p in (req.specification_refs or []) if p]
        for tgt, reason in validate_targets(
            req_paths, repo_root, "requirement.specification_refs",
        ):
            errors.append(
                f"requirement {req.id}.specification_refs: {tgt}: {reason}"
            )
    return errors



def validate_repository_binding(contract: Contract, repo_root) -> list:
    """Enforce a declared repository block (spec 02, 05, 06). Absent = no bind."""
    from .identity import repository_binding
    from .repository import porcelain, read_repo_identity, repo_head
    from .safety import is_control_artifact, is_interpreter_residue

    decl = repository_binding(contract)
    if not decl:
        return []
    errors = []
    if decl.get("identity"):
        have = read_repo_identity(repo_root)
        if have != decl["identity"]:
            errors.append(
                f"repository.identity declared {decl['identity']!r} "
                f"but worktree is {have!r}"
            )
    if decl.get("revision"):
        head = repo_head(repo_root)
        if head != decl["revision"]:
            errors.append(
                f"repository.revision declared {decl['revision'][:12]} "
                f"but HEAD is {head[:12] or '(empty)'}"
            )
    dirty = decl.get("dirty_state")
    if dirty in (None, ""):
        pass
    elif dirty in ("clean", False) or dirty == {"expected": "clean"}:
        dirt = sorted(
            p for p in porcelain(repo_root)
            if not is_control_artifact(p) and not is_interpreter_residue(p)
        )
        if dirt:
            errors.append(
                f"repository.dirty_state=clean but dirty paths {dirt}"
            )
    else:
        errors.append(f"unknown repository.dirty_state {dirty!r}")
    return errors
