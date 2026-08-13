# ADR-0002 — Contract plane and execution plane

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Specification v0.1

## Context

If execution artifacts (logs, exit codes, worktree dirt) are allowed to rewrite what was authorized, the controller becomes a diary of whatever happened.

## Decision

Git-Up! has two planes. The contract plane answers what is authorized. The execution plane answers what happened. Verification compares them. Execution artifacts MUST NOT become contract authority.

## Consequences

- Three objects remain distinct: contract, execution, evidence.
- Reports and checkpoints are derived.
- Scope violations fail even when the command exits 0.
