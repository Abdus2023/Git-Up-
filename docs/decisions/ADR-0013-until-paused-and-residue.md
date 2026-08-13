# ADR-0013 — `run --until-paused` and interpreter residue

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.4

## Context

Spec 10 says a single `run` considers only the head of the READY queue. Multi-task contracts therefore need repeated invocations. Operators and agents want one command that drains the queue without dropping the lease between tasks.

Separately, running declared validators (especially `python3 -m unittest`) writes `__pycache__` / `*.pyc`. Treating those as scope violations would make self-verification impossible without lying about implementation targets.

## Decision

1. Add `git-up run --until-paused`: under **one** exclusive lease, execute the READY head, reclassify, repeat until the queue is empty or a task FAILs. Default `run` remains one task.
2. Interpreter residue (`__pycache__/`, `*.pyc`, `*.pyo`) is a controller-class artifact: it is not a scope violation and is omitted from `observed_delta`.
3. Publish a derived JSON Schema at `docs/contract.schema.json`. It describes the v0.1 contract document; it is **not** authority (spec 09).

## Consequences

- Self-contract `git-up run` can authorize T-SPEC18.
- New flag, not a new command name (spec 17 §7).
