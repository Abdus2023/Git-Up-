# ADR-0017 — Bind emitted contracts to the plan identity

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.8

## Context

Spec 12 requires `provenance.source_identity` on the contract. The v0.6 adapter left it empty, and `load_contract` dropped any `provenance` object. Two different plans could emit contracts that looked unbound to their producer.

## Decision

1. `emit_contract` sets `provenance.source_identity = SHA256(canonical(plan))` and `producer = git-up.adapter.plan`.
2. `Contract` persists `provenance` through load.
3. Contract-document identity includes producer + plan hash (plus existing semantic fields).
4. Wrapping markdown prose is not part of the plan hash — only the declared plan object is.

## Consequences

- Same plan JSON and the same plan inside a fence share `source_identity`.
- Changing a declared task field changes the plan hash and therefore the contract identity.
- Hand-written contracts without provenance keep empty producer/hash.
