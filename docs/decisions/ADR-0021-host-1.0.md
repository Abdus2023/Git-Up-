# ADR-0021 — Host Implementation 1.0

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0

## Context

Specification v0.1 is frozen. The host (Python 3 stdlib) now covers the authorized surface: controller, CLI, adapters, lineage, diff, self-plan dogfood. Rust remains the intended native language (ADR-0008) but cannot be built here. Continuing to mint 0.x freezes without a host baseline blurs “done.”

## Decision

1. Declare **Host 1.0.0** as the conforming implementation of Specification v0.1.
2. Require the committed `git-up.contract.json` to have the same document identity as `emit(docs/plans/self.md)`.
3. Leave Rust crates, additional adapters, and signed evidence to later freezes. Host 1.0 does not authorize those.

## Consequences

- Semver **1.0.0** is the host. Breaking the frozen spec requires a new specification freeze, not a quiet 1.0.1.
- Compatible host fixes may be 1.0.x. New host features need a new ADR.
- A native Rust 1.0 would be a **different** artifact, versioned separately.
