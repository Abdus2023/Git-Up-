# ADR-0005 — PASS only via VALIDATING + predicate

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Specification v0.1

## Context

Historical code treated `IN_PROGRESS → PASS` as legal if evidence existed, and forbade READY→PASS. That is still too weak: crash mid-progress plus a checkpoint flag can look like success. Exit 0 is a perennial false equivalent.

## Decision

`PASS` is reachable only from `VALIDATING`, and only when the full authorization predicate (spec 11 §5) holds. Exit status, checkpoint flags, evidence presence, and agent belief are never sufficient.

## Consequences

- Explicit `VALIDATING` state (tighter than prior art).
- Reconstruction is the only way a task joins the authoritative PASS set.
- Classifier never writes PASS.
