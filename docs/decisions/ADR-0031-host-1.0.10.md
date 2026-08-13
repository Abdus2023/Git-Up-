# ADR-0031 — Host 1.0.10 flag-style path arguments

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.10 (Specification v0.1 unchanged)

## Context

Spec 10 §2 / 16 §3: command arguments MUST NOT be absolute and MUST NOT
contain a `..` path component. The host split on `/` and tested list
membership. `--file=../secret` tokenizes as `--file=../secret`, whose
`/`-parts are `--file=..` and `secret` — `..` is not an element, so the
argument was allowed. `--file=/etc/passwd` similarly bypassed the
leading-`/` check.

The execution contract's `required_evidence` list omitted `command_id`,
`observed_delta`, and `target_hashes`, which spec 10 §5 requires to be
recorded. The records already contained those fields; the projection
did not name them.

An unknown checkpoint `schema_version` was loaded as v1 and could
present forged PASS rows.

## Decision

Compatible host patch **1.0.10**:

1. Argument safety inspects the value side of `flag=value` (and `\\`
   as a separator). `--file=../x` and `--file=/abs` are denied. Bare
   relative `--file=src/out.txt` remains allowed.
2. Execution-contract `required_evidence` names `command_id`,
   `observed_delta`, and `target_hashes` (spec 05 §6 / 10 §5).
3. A checkpoint whose `schema_version` is present and not
   `git-up.state.v1` is treated as empty (reconstruct from evidence).

## Consequences

- Semver **1.0.10**. Specification v0.1 is not bumped.
- Flag-style path smuggling cannot reach `subprocess`.
- Self-contract identity is unchanged.
