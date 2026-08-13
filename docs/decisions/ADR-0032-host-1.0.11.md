# ADR-0032 — Host 1.0.11 directory target observation

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.11 (Specification v0.1 unchanged)

## Context

Spec 06 §5 records target state as absent / file sha256 / symlink.
`sha256_file` on a directory raises `IsADirectoryError`, which the host
stored as `None` — the same value as an absent path. Spec 11 §5.7 binds
PASS to that map. Deleting a directory target (including the self-contract
`git_up/` package) left the map unchanged and could still authorize PASS.

Spec 05 names `policy.determinism` as required. A contract with
`determinism: false` loaded and classified.

## Decision

Compatible host patch **1.0.11**:

1. A directory target is observed as `dir:` plus SHA256 of the canonical
   child list `(name, observed-state)`. Interpreter residue and
   `.git-up/` entries are omitted (ADR-0013). Absent remains `None`.
   Files and symlinks are unchanged.
2. Declared `policy.determinism` that is not true is `ContractError`.
   Absent still defaults (existing contracts keep their hash).

## Consequences

- Semver **1.0.11**. Specification v0.1 is not bumped.
- Changing a file under a directory target invalidates PASS.
- `__pycache__` under a directory target does not.
- Self-contract document identity is unchanged.
