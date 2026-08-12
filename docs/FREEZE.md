# Git-Up! Specification Freeze v0.1

**Declared:** 2026-08-12  
**Status:** IN FORCE

This freeze is the first Git-Up! baseline. Implementation of crates, CLI, or runtime behavior is **not** authorized until a later freeze says so.

## Frozen set

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [specification/01](specification/01-project-charter.md) … [20](specification/20-adr-index.md)
- [decisions/ADR-0001](decisions/ADR-0001-independence.md) … [ADR-0009](decisions/ADR-0009-prior-art-reference.md)
- [traceability/](traceability/README.md)

## Architectural baseline (A–M)

Contract, repository identity, task, dependency, classification, contract identity, execution, observation, evidence, PASS authorization, checkpoint/recovery, concurrency, traceability.

## Deliberate tightenings versus prior art

1. Stages 1–4 are adapters, not core.
2. Explicit `VALIDATING` state; `IN_PROGRESS → PASS` is illegal.
3. Lock is acquired **before** reconstruction (Phase 28 corrected).
4. Dry-run creates no identity file and takes no lease.
5. Independent terminology and `.git-up/` control directory.

## Next step (completed by Implementation Freeze v0.2)

See [HOST-1.0.md](HOST-1.0.md). The host implementation is **1.0.9** (Specification v0.1).
