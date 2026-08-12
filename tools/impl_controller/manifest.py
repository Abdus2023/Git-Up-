"""Manifest loader: implementation plan -> Task objects.

The manifest is a JSON document (stdlib-safe; PyYAML is not required).
Schema validation is strict and fail-closed:
  * unknown fields are rejected (never silently normalized);
  * malformed sub-objects (validation commands, blockers, deps, criteria) are
    rejected;
  * type errors surface as ManifestError;
  * dependency cycles are detected and reported with the blocking chain;
  * target-path confinement is validated via Manifest.validate_paths().
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .model import (
    Task, Tool, AuthorityRef, DependencyRef, DeclaredBlocker,
    ValidationCommand, AcceptanceCriterion, ExpectedOutput, ToolRegistry,
    Requirement, CoverageEntry,
)
from .safety import validate_targets

MANIFEST_SCHEMA_VERSION = "1.0"

KNOWN_TOPLEVEL = {
    "schema_version", "project", "generated", "provenance", "note",
    "tool_registry", "tasks", "requirements",
}

KNOWN_TASK_FIELDS = {
    "task_id", "title", "description", "priority", "plan_order", "scope",
    "source_authority", "requirement_refs", "specification_refs",
    "implementation_targets", "dependency_refs", "required_tools",
    "validation_commands", "acceptance_criteria", "evidence_refs",
    "spec_conflicts", "spec_gaps", "declared_blockers", "allowed_tools",
    "prohibited_scope", "expected_outputs", "provenance", "rejected", "deferred",
}


class ManifestError(ValueError):
    """Raised when the manifest is structurally invalid."""


@dataclass
class Manifest:
    schema_version: str
    project: str
    tasks: list                   # list[Task]
    tool_registry: ToolRegistry
    generated: str = ""
    provenance: str = ""
    source_path: Optional[str] = None
    requirements: list = field(default_factory=list)   # list[Requirement]

    def validate_paths(self, repo_root) -> None:
        """Validate implementation-target path confinement. Raises on escape."""
        root = Path(repo_root)
        for t in self.tasks:
            violations = validate_targets(t.implementation_targets, root,
                                           "implementation_targets")
            if violations:
                details = "; ".join(f"{p}: {r}" for p, r in violations)
                raise ManifestError(
                    f"task '{t.task_id}' unsafe implementation_targets: {details}")


# ---------------------------------------------------------------------------
# parsing helpers
# ---------------------------------------------------------------------------

def _need(d: dict, key: str, ctx: str):
    if key not in d:
        raise ManifestError(f"{ctx}: missing required field '{key}'")
    return d[key]


def _as_list(d: dict, key: str, ctx: str) -> list:
    if key not in d:
        return []
    val = d[key]
    if not isinstance(val, list):
        raise ManifestError(f"{ctx}: field '{key}' must be a list")
    return val


def _parse_authority(items: list, ctx: str) -> list:
    out = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise ManifestError(f"{ctx}[{i}]: authority ref must be an object")
        out.append(AuthorityRef(
            doc=_need(it, "doc", f"{ctx}[{i}]"),
            anchor=it.get("anchor", ""),
            requirement_id=it.get("requirement_id", ""),
        ))
    return out


def _int_or_raise(v, ctx: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ManifestError(f"{ctx}: must be an integer, got {v!r}")
    return v


def _parse_task(raw: dict, idx: int) -> Task:
    ctx = f"task[{idx}]"
    if not isinstance(raw, dict):
        raise ManifestError(f"{ctx}: task must be an object")
    unknown = set(raw.keys()) - KNOWN_TASK_FIELDS
    if unknown:
        raise ManifestError(f"{ctx} ({raw.get('task_id', '?')}): "
                            f"unknown field(s): {sorted(unknown)}")

    tid = str(_need(raw, "task_id", ctx))
    ctx = f"task[{tid}]"

    deps = []
    for i, d in enumerate(_as_list(raw, "dependency_refs", ctx)):
        if not isinstance(d, dict) or not d.get("ref"):
            raise ManifestError(f"{ctx}.dependency_refs[{i}]: missing 'ref'")
        deps.append(DependencyRef(ref=str(d["ref"]),
                                  required_state=str(d.get("required_state", "PASS"))))

    vcs = []
    for i, v in enumerate(_as_list(raw, "validation_commands", ctx)):
        if not isinstance(v, dict):
            raise ManifestError(f"{ctx}.validation_commands[{i}]: must be an object")
        if not v.get("id"):
            raise ManifestError(f"{ctx}.validation_commands[{i}]: missing 'id'")
        if not str(v.get("command", "")).strip():
            raise ManifestError(f"{ctx}.validation_commands[{i}]: missing 'command'")
        vcs.append(ValidationCommand(id=str(v["id"]), command=str(v["command"]),
                                     expected_exit=_int_or_raise(
                                         v.get("expected_exit", 0),
                                         f"{ctx}.validation_commands[{i}].expected_exit"),
                                     purpose=str(v.get("purpose", ""))))

    acs = []
    for i, a in enumerate(_as_list(raw, "acceptance_criteria", ctx)):
        if not isinstance(a, dict) or not a.get("id") or not a.get("criterion"):
            raise ManifestError(f"{ctx}.acceptance_criteria[{i}]: "
                                "must have 'id' and 'criterion'")
        acs.append(AcceptanceCriterion(id=str(a["id"]), criterion=str(a["criterion"]),
                                       validator=str(a.get("validator", ""))))

    blockers = []
    for i, b in enumerate(_as_list(raw, "declared_blockers", ctx)):
        if not isinstance(b, dict) or not b.get("category"):
            raise ManifestError(f"{ctx}.declared_blockers[{i}]: missing 'category'")
        blockers.append(DeclaredBlocker(category=str(b["category"]),
                                        satisfied=bool(b.get("satisfied", False)),
                                        evidence=str(b.get("evidence", "")),
                                        detail=str(b.get("detail", ""))))

    exps = []
    for i, o in enumerate(_as_list(raw, "expected_outputs", ctx)):
        if not isinstance(o, dict) or not o.get("path") or not o.get("sha256"):
            raise ManifestError(f"{ctx}.expected_outputs[{i}]: need 'path' and 'sha256'")
        exps.append(ExpectedOutput(path=str(o["path"]), sha256=str(o["sha256"])))

    ev = [str(x) for x in _as_list(raw, "evidence_refs", ctx)]
    if len(ev) != len(set(ev)):
        raise ManifestError(f"{ctx}.evidence_refs: duplicate references")

    return Task(
        task_id=tid,
        title=str(_need(raw, "title", ctx)),
        description=str(_need(raw, "description", ctx)),
        priority=_int_or_raise(raw.get("priority", 100), f"{ctx}.priority"),
        plan_order=_int_or_raise(raw.get("plan_order", idx), f"{ctx}.plan_order"),
        scope=str(raw.get("scope", "")),
        source_authority=_parse_authority(_as_list(raw, "source_authority", ctx),
                                          f"{ctx}.source_authority"),
        requirement_refs=[str(x) for x in _as_list(raw, "requirement_refs", ctx)],
        specification_refs=_parse_authority(_as_list(raw, "specification_refs", ctx),
                                            f"{ctx}.specification_refs"),
        implementation_targets=[str(x) for x in _as_list(raw, "implementation_targets", ctx)],
        dependency_refs=deps,
        required_tools=[str(x) for x in _as_list(raw, "required_tools", ctx)],
        validation_commands=vcs,
        acceptance_criteria=acs,
        evidence_refs=ev,
        spec_conflicts=[str(x) for x in _as_list(raw, "spec_conflicts", ctx)],
        spec_gaps=[str(x) for x in _as_list(raw, "spec_gaps", ctx)],
        declared_blockers=blockers,
        allowed_tools=[str(x) for x in _as_list(raw, "allowed_tools", ctx)],
        prohibited_scope=[str(x) for x in _as_list(raw, "prohibited_scope", ctx)],
        expected_outputs=exps,
        provenance=str(raw.get("provenance", "")),
        rejected=bool(raw.get("rejected", False)),
        deferred=bool(raw.get("deferred", False)),
    )


def _parse_requirements(items: list) -> list:
    """Parse optional top-level requirements with explicit coverage declarations."""
    out = []
    for i, r in enumerate(items):
        if not isinstance(r, dict) or not r.get("id"):
            raise ManifestError(f"requirements[{i}]: must have 'id'")
        cov = []
        for j, c in enumerate(r.get("coverage", [])):
            if not isinstance(c, dict) or not c.get("task_id"):
                raise ManifestError(f"requirements[{i}].coverage[{j}]: must have 'task_id'")
            cov.append(CoverageEntry(task_id=str(c["task_id"]),
                                     obligations=[str(o) for o in c.get("obligations", [])]))
        out.append(Requirement(id=str(r["id"]),
                               specification_refs=[str(s) for s in r.get("specification_refs", [])],
                               coverage=cov))
    return out


def _parse_tool_registry(raw: dict) -> ToolRegistry:
    reg = ToolRegistry()
    for tid, spec in (raw or {}).items():
        if not isinstance(spec, dict):
            raise ManifestError(f"tool_registry['{tid}']: must be an object")
        reg.register(Tool(id=str(tid),
                          available=bool(spec.get("available", False)),
                          evidence=str(spec.get("evidence", "")),
                          detail=str(spec.get("detail", "")),
                          binary=str(spec.get("binary", "")),
                          version=str(spec.get("version", ""))))
    return reg


def _detect_cycles(tasks: list) -> None:
    by_id = {t.task_id: [d.ref for d in t.dependency_refs] for t in tasks}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in by_id}

    def dfs(node, stack):
        color[node] = GRAY
        stack.append(node)
        for nxt in by_id.get(node, []):
            if nxt not in by_id:
                continue  # unknown deps are caught elsewhere
            if color[nxt] == GRAY:
                cyc = stack[stack.index(nxt):] + [nxt]
                raise ManifestError(f"dependency cycle detected: {' -> '.join(cyc)}")
            if color[nxt] == WHITE:
                dfs(nxt, stack)
        stack.pop()
        color[node] = BLACK

    for tid in by_id:
        if color[tid] == WHITE:
            dfs(tid, [])


def load_manifest(path) -> Manifest:
    p = Path(path)
    if not p.is_file():
        raise ManifestError(f"manifest not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ManifestError(f"manifest JSON parse error in {p}: {e}") from e
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be an object")

    unknown_top = set(raw.keys()) - KNOWN_TOPLEVEL
    if unknown_top:
        raise ManifestError(f"unknown top-level field(s): {sorted(unknown_top)}")

    schema_version = str(raw.get("schema_version", ""))
    if not schema_version:
        raise ManifestError("manifest missing 'schema_version'")
    if not schema_version.split(".")[0].isdigit():
        raise ManifestError(f"invalid schema_version: {schema_version!r}")

    task_list = _as_list(raw, "tasks", "manifest")
    tasks = [_parse_task(t, i) for i, t in enumerate(task_list)]
    if not tasks:
        raise ManifestError("manifest has no tasks")

    ids = [t.task_id for t in tasks]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ManifestError(f"duplicate task_id(s): {dupes}")

    known = set(ids)
    for t in tasks:
        for dep in t.dependency_refs:
            if dep.ref not in known:
                raise ManifestError(
                    f"task '{t.task_id}': dependency_refs -> unknown task '{dep.ref}'")

    _detect_cycles(tasks)
    tool_registry = _parse_tool_registry(raw.get("tool_registry", {}))

    return Manifest(
        schema_version=schema_version,
        project=str(raw.get("project", "")),
        tasks=tasks,
        tool_registry=tool_registry,
        generated=str(raw.get("generated", "")),
        provenance=str(raw.get("provenance", "")),
        source_path=str(p),
        requirements=_parse_requirements(raw.get("requirements", [])),
    )
