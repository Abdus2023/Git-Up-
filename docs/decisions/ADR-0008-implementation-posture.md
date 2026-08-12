# ADR-0008 — Specification first; Rust intent; no crate cut yet

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Specification v0.1

## Context

A suggested layout (`git-up-core`, `git-up-contract`, `git-up-engine`, …) is attractive and premature. Implementing before the freeze would either port the Python controller or proliferate empty crates.

## Decision

v0.1 freezes architecture and specification only. No product implementation is authorized. Intended later language is Rust. Crate decomposition is **not** frozen. Do not add a workspace of empty crates in this freeze.

## Consequences

- No `Cargo.toml` in v0.1.
- No Python package as the product.
- A future implementation freeze will choose crates against A–M, not against 29 phases.
