# ADR-0024 — Host 1.0.3 repository and evidence binding

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.3 (Specification v0.1 unchanged)

## Context

Spec 02 requires the controller to validate a contract against repository
identity. Spec 05 declares an optional `repository { identity, revision,
dirty_state }` block. Spec 06 §6 requires authorizing evidence `head` to equal
the current HEAD (and the same for repository / source identity). Host 1.0.2
bound PASS only through `contract_id`, ignored a declared `repository` block,
and crashed (exit 3) on malformed list items instead of `ContractError`.

## Decision

Compatible host patch **1.0.3**:

1. Authorizing evidence must match the current provenance context:
   `head`, `repository_identity`, `source_identity`, `validator == "git-up"`.
   A matching `contract_id` with a forged `head` field is inert.
2. If the contract (or plan) **declares** `repository.identity` /
   `repository.revision` / `repository.dirty_state`, enforce it. Absent means
   no bind. `dirty_state` of `clean` (or `false`, or `{expected: clean}`)
   requires no product dirt. Any other non-empty `dirty_state` is unknown →
   refuse. The host never writes a declared identity into `repo.identity`.
3. `source_identity` includes the repository block only when at least one
   binding field is non-empty (existing contracts keep their hash).
4. The plan adapter passes a declared `repository` through and does not invent
   one. `expected_outputs` entries must be objects.
5. Unknown dependency refs are reported as `not a declared task`.
6. Malformed list items in a contract are `ContractError` (exit 2), not a
   traceback.

## Consequences

- Semver **1.0.3**. Specification v0.1 is not bumped.
- A contract pinned to another worktree or commit fail-closes before execute.
- Dry-run `verify` without `repo.identity` still cannot cite mutating evidence
  as bound (empty identity ≠ recorded identity).
