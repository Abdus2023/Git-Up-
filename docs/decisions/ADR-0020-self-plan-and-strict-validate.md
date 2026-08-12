# ADR-0020 — Self-plan is the source of the self-contract; validate --strict

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.11

## Context

`git-up.contract.json` was hand-written. The adapter loop existed but the product contract did not go through it. `contract validate` only checked schema + confinement, so an insufficient definition still exited 0.

## Decision

1. `docs/plans/self.md` is the declared self-plan. `git-up.contract.json` is **emitted** from it (adapter output, with plan `source_identity`).
2. `git-up contract validate --strict` fail-closes if any task is `INSUFFICIENT_TASK_DEFINITION` (or confinement fails). It still does not execute and does not authorize PASS.

## Consequences

- Regenerating the self-contract is `git-up contract emit --from docs/plans/self.md --out git-up.contract.json`.
- Hand-editing the emitted contract without updating the plan is a provenance drift, visible via `contract diff`.
