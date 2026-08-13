# ADR-0014 — `verify` emits a predicate breakdown

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.5

## Context

Spec 17 says `verify` re-evaluates the authorization predicate. v0.4 only relabeled a recover/classify report. Operators could not see *why* a task was not PASS without reading source.

## Decision

`git-up verify` emits a derived `predicate[]` from `authorize.predicate_report`. Each entry is an explanation. It **never** authorizes PASS (spec 09). Default `verify` remains mutating (reconcile checkpoint) unless `--dry-run`.

Also record the Stage 5 conformance audit at `docs/traceability/conformance.md`.

## Consequences

- Verify is inspectable.
- The audit document is derived, not frozen specification.
