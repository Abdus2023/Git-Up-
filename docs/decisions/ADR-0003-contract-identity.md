# ADR-0003 — SHA256 canonical contract identity

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Specification v0.1

## Context

Evidence must not replay across tasks, repositories, commits, or revised contracts. User-supplied ids are forgeable.

## Decision

`contract_id = SHA256(canonical(authoritative_payload))` computed by the controller. Unordered lists are sorted. Command *content* is semantic; command *declaration order* is not. HEAD, repository identity, and source identity are in the payload.

## Consequences

- Any semantic edit invalidates prior PASS evidence.
- Identity is deterministic (spec 18 I-ID-*).
- User-supplied `contract_id` fields are ignored for authorization.
