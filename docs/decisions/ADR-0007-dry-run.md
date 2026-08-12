# ADR-0007 — Dry-run is first-class and mute

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Specification v0.1

## Context

Operators and agents need to inspect classification and planned contracts without taking a lease or leaving residue. A dry-run that creates identity files or lock files becomes a mutation.

## Decision

`--dry-run` (and default inspect/classify/plan/ready) guarantees:

```
NO LOCK · NO EXECUTION · NO MUTATION · NO EVIDENCE · NO CHECKPOINT · NO IDENTITY CREATE
```

Outputs are labeled advisory and cannot authorize PASS.

## Consequences

- `repo.identity` is created only under a mutating lease.
- Tests I-DRY-1 are mandatory.
- Dry-run `result: PASS` means “controller run had no errors,” not task PASS.
