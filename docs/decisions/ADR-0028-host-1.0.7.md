# ADR-0028 — Host 1.0.7 confinement completeness and BLOCKED runtime

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.7 (Specification v0.1 unchanged)

## Context

ADR-0026 said contract-level `authority.sources` paths are confined.
ADR-0027 said that gate was restored. `validate_confinement` still only
walked per-task paths. A source such as `docs/../docs/SPEC.md` resolved
in-repo and classified READY, violating spec 06 §4 / 16 §4 (`..` is
never a legal contract path). Requirement `specification_refs` were
likewise unchecked.

Spec 08 allows `IN_PROGRESS → BLOCKED` when a safety or toolchain
failure is detected before VALIDATING. The host recorded those as
`finish_fail` (task state FAIL) even when the evidence `result` was
`BLOCKED`. Spec 10 still requires scope violations and non-matching
exits to be FAIL — that split was not implemented.

Spec 05 names validation commands as `argv-or-string`. A JSON list was
stringified (`"['python3', '-c', 'pass']"`) and could not execute.

## Decision

Compatible host patch **1.0.7**:

1. `validate_confinement` also checks `authority.sources` and
   requirement `specification_refs`. Escape / `..` / `.git` is a
   contract error (same posture as task-level authority paths).
2. Evidence `result == BLOCKED` (unsafe command, missing binary)
   transitions `IN_PROGRESS → BLOCKED`. Scope and exit mismatches stay
   `FAIL`. `VALIDATING → BLOCKED` remains illegal.
3. A missing binary records `failure_class: TOOLCHAIN` (spec 10 §3).
4. `command` may be a string or a list of string tokens. Lists are
   canonicalized with `shlex.join` at load/emit so identity matches the
   equivalent string form. Other types are `ContractError`.

## Consequences

- Semver **1.0.7**. Specification v0.1 is not bumped.
- `contract validate` and `emit --check` fail closed on `..` in
  contract-level sources.
- A denied shell/sudo-class or missing tool no longer checkpoints FAIL.
- Existing string commands and the self-contract hash are unchanged.
