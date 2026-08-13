# ADR-0015 — Plan adapter and `contract emit`

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.6

## Context

Stages 1–4 are adapters (ADR-0006). v0.5 had no adapter, so every contract had to be written by hand. A first adapter must exist without becoming a second controller or guessing missing semantics.

## Decision

1. Add `git_up.adapter` to emit `git-up.contract.v0.1` from `git-up.plan.v0.1`.
2. Add `git-up contract emit --from <plan> [--out <contract>]`. This extends the existing `contract` command; it is not a new top-level verb.
3. The adapter never invents authority, commands, or criteria.
4. Adapter code is not on the PASS authorization path.

## Consequences

- Humans and other producers can emit contracts without touching core.
- Incomplete plans become BLOCKED tasks, not guessed READY tasks.
