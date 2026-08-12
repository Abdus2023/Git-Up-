# ADR-0001 — Git-Up! is independent of Red/Cognition

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Specification v0.1

## Context

The controller methodology was developed inside Red/Cognition. That repository has RFCs, a Python `impl_controller`, and a planner-specific manifest. Reusing those names and paths would couple Git-Up! to a single upstream and hide assumptions.

## Decision

Git-Up! is a separate product with its own specification, terminology, tests, and release history. It MUST NOT require Red/Cognition RFCs, files, or runtime. Red/Cognition MAY later ship an adapter that emits Git-Up! contracts.

## Consequences

- New vocabulary (`git-up`, `.git-up/`, `contract`, validator identity `"git-up"`).
- Prior-art code is not the implementation.
- Adapters are optional and out of v0.1 core.
