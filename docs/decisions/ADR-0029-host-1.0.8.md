# ADR-0029 — Host 1.0.8 isolated Git observation

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.8 (Specification v0.1 unchanged)

## Context

Spec 06 binds Git-Up! to **one worktree**. HEAD and porcelain are
authorization inputs (contract_id, scope guard, dirty_state). Spec 16 §9
says environment variables cannot widen authority.

The host invoked `git` with the process environment. Ambient `GIT_DIR` /
`GIT_WORK_TREE` / `GIT_COMMON_DIR` retarget `rev-parse` and `status` at
another repository. A user `alias.status` can hide untracked paths from
porcelain. Scope and HEAD binding would then describe the wrong tree.

Spec 06 §2.2: empty HEAD on a mutating run is already FAIL. Dry-run MAY
report empty HEAD as a classification blocker. It did not.

## Decision

Compatible host patch **1.0.8**:

1. All controller git invocations (and declared validators) use
   `controller_env()`: strip ambient `GIT_*`, set
   `GIT_CONFIG_NOSYSTEM` / `GIT_CONFIG_GLOBAL=/dev/null` /
   `GIT_CONFIG_SYSTEM=/dev/null`, `GIT_TERMINAL_PROMPT=0`,
   `GIT_OPTIONAL_LOCKS=0`. Git is always `git -C <repo-root>`.
   Repo-local `.git/config` remains. Linked worktrees keep working
   because `GIT_DIR` is not forced to `<root>/.git`.
2. Dry-run classification treats empty HEAD as `ENVIRONMENT` (spec 06
   §2.2). Mutating runs still FAIL closed before classify.

## Consequences

- Semver **1.0.8**. Specification v0.1 is not bumped.
- `GIT_DIR` in the operator shell cannot steal HEAD or porcelain.
- A `~/.gitconfig` status alias cannot hide untracked product writes.
- An unborn repository is BLOCKED on dry-run, not READY.
- Self-contract identity is unchanged.
