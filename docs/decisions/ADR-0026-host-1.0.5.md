# ADR-0026 — Host 1.0.5 contract-level sources and stricter validate

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.5 (Specification v0.1 unchanged)

## Context

Spec 09 names `authority.sources` as a source, alongside task
`source_authority` and `specification_refs`. Host 1.0.4 ignored the
contract-level list. A missing named source must BLOCK
(`INSUFFICIENT_TASK_DEFINITION`); the host must not fetch or invent one.

`contract validate --strict` only failed on `INSUFFICIENT_TASK_DEFINITION`.
After 1.0.4, a dangling `requirement_ref` is `TRACEABILITY` and still exited 0
under `--strict`.

Garbage authority entries (`42` instead of a path or object) crashed load.

## Decision

Compatible host patch **1.0.5**:

1. Parse `authority.sources` (or `authority_sources`). Confine the paths.
   Missing/unreadable sources BLOCK every non-terminal task and fail
   `task_may_pass`.
2. `source_identity` includes that list only when it is non-empty (existing
   contracts keep their hash).
3. The plan adapter passes a declared `authority.sources` through and does
   not invent one.
4. Authority refs that are neither a string nor an object are `ContractError`.
5. `--strict` fail-closes on contract-shape blockers:
   `INSUFFICIENT_TASK_DEFINITION`, `TRACEABILITY`, `SPECIFICATION_CONFLICT`,
   `INCOMPLETE_SPECIFICATION`. Not `DEPENDENCY` or `TOOLCHAIN`.

## Consequences

- Semver **1.0.5**. Specification v0.1 is not bumped.
- A contract that names a missing charter document cannot classify READY.
- `--strict` now catches dangling requirement refs.
