# Git-Up! documentation

This tree is the **Specification Freeze v0.1**.

Nothing in this tree authorizes product implementation. It freezes identity, scope, models, invariants, and the ADR process so later implementation cannot smuggle in Red/Cognition assumptions.

## Start here

1. [ARCHITECTURE.md](ARCHITECTURE.md) — freeze v0.1 synthesis
2. [specification/README.md](specification/README.md) — numbered Specification v0.1
3. [decisions/README.md](decisions/README.md) — Architecture Decision Records
4. [traceability/README.md](traceability/README.md) — spec ↔ phase ↔ invariant map

## Named entry points

These are indexes into the numbered specification. The numbered documents are canonical.

| Named doc | Canonical spec |
|---|---|
| [SPECIFICATION.md](SPECIFICATION.md) | 01–20 |
| [CONTRACT.md](CONTRACT.md) | 05 |
| [STATE-MACHINE.md](STATE-MACHINE.md) | 08 |
| [EVIDENCE.md](EVIDENCE.md) | 11 |
| [TRACEABILITY.md](TRACEABILITY.md) | 15 |
| [SECURITY.md](SECURITY.md) | 16 |

## What is frozen

- Project thesis and non-scope
- Two-plane architecture (contract / execution → verification)
- Three-way distinction (contract / execution / evidence)
- Authority hierarchy
- State machine and illegal transitions
- Contract identity
- Lock-first concurrency for all non-dry-run operations
- Dry-run non-mutation guarantee
- PASS authorization predicate
- Recovery and crash-consistency obligations
- CLI surface (names and semantics, not implementation)
- Test strategy keyed to invariants
- Mapping of methodological phases 1–29 onto v0.1 components A–M

## What is not frozen

- Crate decomposition
- Wire formats beyond the conceptual schema
- Storage layout beyond the `.git-up/` names
- Implementation language bindings
- Adapter implementations for any particular upstream planner
