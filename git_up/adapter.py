"""Adapter plane: emit a Git-Up! contract from a declared plan.

Adapters are not core. They MUST NOT invent authority, validators, or
acceptance criteria. Missing fields pass through empty; classification
then fail-closes (ADR-0006, ADR-0015).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import CONTRACT_SCHEMA
from .canonical import sha256_json
from .errors import ContractError

PLAN_SCHEMA = "git-up.plan.v0.1"

# Explicit fences only. Prose is never parsed as a plan (ADR-0016).
_FENCE_GITUP = re.compile(
    r"```git-up-plan[^\n]*\n(.*?)```",
    re.DOTALL,
)
_FENCE_JSON = re.compile(
    r"```json[^\n]*\n(.*?)```",
    re.DOTALL,
)


def _parse_plan_object(raw) -> dict:
    if not isinstance(raw, dict):
        raise ContractError("plan must be a JSON object")
    if raw.get("schema_version") != PLAN_SCHEMA:
        raise ContractError(
            f"unknown plan schema_version {raw.get('schema_version')!r}; "
            f"expected {PLAN_SCHEMA!r}"
        )
    return raw


def parse_plan_text(text: str, *, source: str = "<text>") -> dict:
    """Load a plan from raw text: whole JSON, or one explicit fence.

    Fail closed if:
      * more than one ```git-up-plan fence exists
      * no fence and the file is not a plan JSON object
      * a json fence exists but is not a git-up.plan.v0.1 object
    Never extract tasks from headings or prose.
    """
    text = text or ""
    gitup_blocks = _FENCE_GITUP.findall(text)
    if len(gitup_blocks) > 1:
        raise ContractError(
            f"{source}: multiple ```git-up-plan fences; refuse to choose"
        )
    if len(gitup_blocks) == 1:
        try:
            raw = json.loads(gitup_blocks[0])
        except json.JSONDecodeError as e:
            raise ContractError(f"{source}: git-up-plan fence is not JSON: {e}") from e
        return _parse_plan_object(raw)

    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError:
            raw = None
        if isinstance(raw, dict) and raw.get("schema_version") == PLAN_SCHEMA:
            return _parse_plan_object(raw)
        if isinstance(raw, dict):
            raise ContractError(
                f"{source}: JSON is not a {PLAN_SCHEMA} plan"
            )

    json_blocks = _FENCE_JSON.findall(text)
    plan_blocks = []
    for block in json_blocks:
        try:
            raw = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict) and raw.get("schema_version") == PLAN_SCHEMA:
            plan_blocks.append(raw)
    if len(plan_blocks) > 1:
        raise ContractError(
            f"{source}: multiple ```json plan objects; refuse to choose"
        )
    if len(plan_blocks) == 1:
        return _parse_plan_object(plan_blocks[0])

    raise ContractError(
        f"{source}: no {PLAN_SCHEMA} plan found "
        "(need a JSON plan file or a single ```git-up-plan fence)"
    )


def load_plan(path) -> dict:
    if str(path) == "-":
        return parse_plan_text(sys.stdin.read(), source="<stdin>")
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ContractError(f"cannot read plan {p}: {e}") from e
    return parse_plan_text(text, source=str(p))


def _auth(item) -> dict:
    if isinstance(item, str):
        return {"path": item, "anchor": "", "requirement_id": ""}
    if not isinstance(item, dict):
        return {"path": "", "anchor": "", "requirement_id": ""}
    return {
        "path": str(item.get("path") or ""),
        "anchor": str(item.get("anchor") or ""),
        "requirement_id": str(item.get("requirement_id") or ""),
    }


def _task(raw: dict, index: int) -> dict:
    if not isinstance(raw, dict) or not raw.get("id"):
        raise ContractError(f"plan task[{index}] missing id")
    cmds = []
    for v in raw.get("commands") or raw.get("validation_commands") or []:
        if not isinstance(v, dict):
            continue
        cmds.append({
            "id": str(v.get("id") or ""),
            "command": str(v.get("command") or ""),
            "expected_exit": int(v.get("expected_exit", 0)),
            "purpose": str(v.get("purpose") or ""),
        })
    crits = []
    for c in raw.get("criteria") or raw.get("acceptance_criteria") or []:
        if not isinstance(c, dict):
            continue
        crits.append({
            "id": str(c.get("id") or ""),
            "statement": str(c.get("statement") or c.get("criterion") or ""),
            "validator": str(c.get("validator") or ""),
        })
    deps = []
    for d in raw.get("depends_on") or raw.get("dependencies") or []:
        if isinstance(d, str):
            deps.append({"ref": d, "required_state": "PASS"})
        elif isinstance(d, dict):
            deps.append({
                "ref": str(d.get("ref") or d.get("id") or ""),
                "required_state": str(d.get("required_state") or "PASS"),
            })
    authority = raw.get("authority") or raw.get("source_authority") or []
    if isinstance(authority, dict):
        authority = [authority]
    spec = raw.get("specification") or raw.get("specification_refs") or []
    if isinstance(spec, dict):
        spec = [spec]
    return {
        "id": str(raw["id"]),
        "title": str(raw.get("title") or ""),
        "description": str(raw.get("description") or ""),
        "scope": str(raw.get("scope") or ""),
        "priority": int(raw.get("priority", 100)),
        "order": int(raw.get("order", index)),
        "source_authority": [_auth(a) for a in authority],
        "requirement_refs": [str(x) for x in (raw.get("requirement_refs") or [])],
        "specification_refs": [_auth(a) for a in spec],
        "implementation_targets": [str(x) for x in (raw.get("targets") or raw.get("implementation_targets") or [])],
        "prohibited_scope": [str(x) for x in (raw.get("prohibited_scope") or [])],
        "dependencies": deps,
        "required_tools": [str(x) for x in (raw.get("required_tools") or [])],
        "allowed_tools": [str(x) for x in (raw.get("allowed_tools") or [])],
        "validation_commands": cmds,
        "acceptance_criteria": crits,
        "expected_outputs": list(raw.get("expected_outputs") or []),
        "declared_blockers": list(raw.get("declared_blockers") or []),
        "spec_conflicts": list(raw.get("spec_conflicts") or []),
        "spec_gaps": list(raw.get("spec_gaps") or []),
        "rejected": bool(raw.get("rejected", False)),
        "deferred": bool(raw.get("deferred", False)),
    }


def emit_contract(plan: dict, parent_ids=None) -> dict:
    """Translate a plan into a contract document. Does not guess."""
    if not isinstance(plan, dict):
        raise ContractError("plan must be a JSON object")
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise ContractError(
            f"unknown plan schema_version {plan.get('schema_version')!r}; "
            f"expected {PLAN_SCHEMA!r}"
        )
    tasks_raw = plan.get("tasks") or []
    if not tasks_raw:
        raise ContractError("plan has no tasks")
    tasks = [_task(t, i) for i, t in enumerate(tasks_raw)]
    tools = []
    for t in plan.get("tools") or []:
        if isinstance(t, dict) and t.get("id"):
            tools.append({
                "id": str(t["id"]),
                "available": bool(t.get("available", False)),
                "binary": str(t.get("binary") or t["id"]),
                "version": str(t.get("version") or ""),
                "evidence": str(t.get("evidence") or ""),
                "detail": str(t.get("detail") or ""),
            })
    reqs = []
    for r in plan.get("requirements") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        spec = r.get("specification_refs") or []
        if r.get("specification"):
            spec = list(spec) + [str(r["specification"])]
        cov = r.get("coverage") or []
        reqs.append({
            "id": str(r["id"]),
            "specification_refs": [str(x) for x in spec],
            "coverage": cov,
        })
    timeout = int((plan.get("policy") or {}).get("timeout_seconds") or 600)
    return {
        "schema_version": CONTRACT_SCHEMA,
        "policy": {
            "determinism": True,
            "timeout_seconds": timeout,
            "concurrency": "exclusive",
            "failure_mode": "fail_closed",
        },
        "tools": tools,
        "requirements": reqs,
        "tasks": tasks,
        "provenance": {
            "producer": "git-up.adapter.plan",
            "source_identity": sha256_json(plan),
            "parent_contracts": list(parent_ids or []),
        },
    }


def emit_contract_file(plan_path, out_path=None, parent_path=None) -> dict:
    from .contract import load_contract
    from .identity import source_identity

    plan = load_plan(plan_path)
    parents = []
    if parent_path:
        parents = [source_identity(load_contract(parent_path))]
    doc = emit_contract(plan, parent_ids=parents)
    if out_path:
        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc
