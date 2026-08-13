# ADR-0011 — Allowlist match is exact, not prefix

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.2

## Context

A historical controller treated an executable as allowlisted if `exe.startswith(allowed_entry)`. That authorizes `python3-evil` when `python3` is allowed.

## Decision

Git-Up! allowlist membership is **exact** token equality on the bare executable name.

## Consequences

Safer default. Documented as an independent tightening, not inherited behavior.
