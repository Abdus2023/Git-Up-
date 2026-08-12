# ADR-0010 — Implementation Freeze v0.2

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.2
- Supersedes (in part): ADR-0008 (the “no implementation” clause only)

## Context

Specification Freeze v0.1 forbade product code until a later freeze chose a crate cut and authorized implementation. That later freeze is now. A Rust toolchain cannot be obtained here (rustup / static.rust-lang.org TLS is blocked). Waiting would leave the invariants untested.

## Decision

1. Authorize implementation against specs 05–18.
2. Freeze the A–M crate cut listed in `docs/IMPLEMENTATION-FREEZE.md`.
3. Ship v0.2 as a Python 3 stdlib host implementation with that module map, so spec 18 obligations can be discharged now.
4. Do not copy `reference/red-cognition-controller/`.
5. Keep Rust as the intended native implementation for a future freeze.

## Consequences

- ADR-0008’s “no product code” clause is superseded; its “no empty crates” and “not a Python port of prior art” clauses stand.
- `git-up` is the product CLI.
- Tests live under `tests/` per spec 18 suites, not under the prior-art unittest tree.
