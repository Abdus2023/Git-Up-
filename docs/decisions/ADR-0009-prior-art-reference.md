# ADR-0009 — Prior-art Python lives under reference/ only

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Specification v0.1

## Context

The Red/Cognition `tools/` tree was copied into this repository for audit. Leaving it at `tools/` would make it look like Git-Up! product code and contradict ADR-0001.

## Decision

The snapshot lives at `reference/red-cognition-controller/`. It is not built, packaged, or invoked as Git-Up!. `tools/` is reserved for future Git-Up! tooling after an implementation freeze.

## Consequences

- Audit can still read the historical controller (including the Phase-28 lock window).
- CI for Git-Up! MUST NOT treat that suite as product tests.
