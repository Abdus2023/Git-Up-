# ADR-0019 — `contract diff` compares identity, not success

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.10

## Context

Lineage (`--parent`) records that B followed A. Operators still need to see *what* changed. A diff that treated “more PASS” as better would invert the authority hierarchy.

## Decision

Add `git-up contract diff A.json B.json` (or `--a` / `--b`). It reports document identity, plan identity, added/removed/changed tasks. It is advisory. `result: PASS` means the diff was computed, not that either contract is authorized.

## Consequences

- Diff is a `contract` subcommand, not a new top-level verb.
- No field is interpreted as “improvement.”
