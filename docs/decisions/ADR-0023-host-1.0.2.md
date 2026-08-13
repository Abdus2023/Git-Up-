# ADR-0023 — Host 1.0.2 observation and graph conformance

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.2 (Specification v0.1 unchanged)

## Context

Host 1.0.1 still had three fail-closed holes in observation and classification:

1. `prohibited_scope` was identity-bearing and confined as a path, but a write
   under an allowed target that also matched a prohibited path was treated as
   in-scope (spec 07, 10, 16).
2. `git status --porcelain` was sliced as `line[3:]`. A rename
   `R  old -> new` became one fake path, so `new` could escape the scope guard.
   Untracked directories were reported as `dir/` instead of their files.
3. Spec 07 §4: cycles in the dependency graph never yield READY and must be
   reported as a blocking chain. Members were BLOCKED only by “dep not PASS”,
   with no cycle record.
4. Spec 10 §5: `observed_delta` is newly dirty product paths, minus `.git-up/`
   artifacts. The host recorded only paths that failed the scope check, so
   in-target writes were invisible.
5. Spec 11 §5.9: a structural PASS record that still carries a scope /
   prohibited delta must not authorize.

## Decision

Compatible host patch **1.0.2**:

1. Scope violations = (paths not under `implementation_targets`) ∪ (paths
   under `prohibited_scope`). Prohibited wins. Residue and `.git-up/` stay
   ignored.
2. Observe via `git status --porcelain=v1 -z --untracked-files=all`. Parse
   rename/copy as `XY PATH\\0ORIG_PATH\\0`. Both names are observed.
3. Strongly connected dependency components of size > 1 (and self-loops) are
   `DEPENDENCY` with `dependency cycle: A → B → A`.
4. `observed_delta` is the product delta. Authorization separately rejects
   any current-`contract_id` structural PASS whose delta still violates scope.

## Consequences

- Semver **1.0.2**. Specification v0.1 is not bumped.
- `git mv` of a target to a non-target is INTEGRATION FAIL.
- A write to `src/secret` is FAIL even if `src` is an allowed target.
- Cycle members never become READY.
