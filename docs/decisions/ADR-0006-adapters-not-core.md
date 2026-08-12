# ADR-0006 — Stages 1–4 are adapters

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Specification v0.1

## Context

The historical lifecycle included extraction, repository reconstruction, requirements, and contract production inside the same project as the controller. That couples Git-Up! to one planning culture and delays reuse by agents, CI, and humans who already have a plan.

## Decision

Git-Up! core begins at a declared contract. Stages 1–4 live behind adapters. Any source may produce a contract. Core validates; it does not mine requirements.

## Consequences

- Smaller core.
- No RFC-0075 (or any other ecosystem) validator in core.
- Adapters are future work, not v0.1 deliverables.
