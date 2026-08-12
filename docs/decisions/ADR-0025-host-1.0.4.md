# ADR-0025 — Host 1.0.4 referential integrity and directory emit

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.4 (Specification v0.1 unchanged)

## Context

Spec 15 requires `requirement → specification → task`. A task could name a
requirement that the contract does not declare and still classify READY. Tool,
command, criterion, and requirement ids could collide; `tool_map()` then
silently kept the last tool. Coverage could name a task that does not exist.
`emit --from` only accepted a file, not a directory of explicit plan files.

## Decision

Compatible host patch **1.0.4**:

1. Load-time `ContractError` on duplicate or empty ids for tasks, tools,
   requirements, per-task validation commands, and per-task criteria.
2. Coverage `task_id` must name a declared task. Requirement / coverage /
   tool entries must be objects.
3. A `requirement_ref` that is not in `contract.requirements` is
   `TRACEABILITY` (classification) and a closure gap (no PASS).
4. `contract emit --from DIR` accepts a directory only when **exactly one**
   `*.json` / `*.md` file is a `git-up.plan.v0.1` plan. Zero or more than one
   → refuse to choose (same posture as multiple fences).
5. `contract emit --check` also runs repository binding.

## Consequences

- Semver **1.0.4**. Specification v0.1 is not bumped.
- `emit --from examples/plans/` fails closed (two example plans).
- Existing self-contract and fixtures already have unique ids and resolved refs.
