# ADR-0012 — Conformance completion v0.3

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.3

## Context

v0.2 discharged the spec 18 invariant IDs but left several MUST-level CLI and evidence details underspecified in code: command-specific report shapes, `reconstruct --write`, truncation indication, and writing reports inside `.git-up/` without a lease.

## Decision

Raise the host implementation to v0.3:

1. Each spec 17 command emits its declared payload (inspect / plan / reconstruct / contract validate / verify / audit).
2. Evidence records mark stdout/stderr truncation.
3. `--report` under `.git-up/` is refused in dry-run and, when allowed, written before lease release.
4. `reconstruct --write` is recover.
5. Ship a repo-root self-contract so `git-up classify` works in this repository.

## Consequences

- CLI tests become part of the release gate.
- Running `git-up run` against the self-contract executes the unit suite as a validator. Tests themselves MUST NOT `execute=True` on that contract (recursion).
