# ADR-0018 — Explicit lineage, emit --check, dry-run pipeline tool

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.9

## Context

Spec 12 allows `parent_contracts`. Inferring a parent from the worktree would invent lineage. Operators also need a confinement check at emit time and a mute recipe that chains emit → validate → classify without becoming a second controller.

## Decision

1. `git-up contract emit --parent PREV.json` records `source_identity(PREV)` in `parent_contracts`. No parent is inferred.
2. `git-up contract emit --check` confinement-checks the emitted contract against `--repo-root`. It does not execute.
3. `tools/pipeline.py` is Git-Up! tooling: dry-run only, no lease, no evidence, no PASS authorization.

## Consequences

- Lineage is opt-in and auditable.
- `tools/` is no longer empty; it is still not core.
