# 20 — Architecture Decision Record Index

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

Canonical process and list: [../decisions/README.md](../decisions/README.md).

## Accepted at freeze v0.1

| ADR | Title |
|---|---|
| [0001](../decisions/ADR-0001-independence.md) | Git-Up! is independent of Red/Cognition |
| [0002](../decisions/ADR-0002-two-planes.md) | Contract plane and execution plane |
| [0003](../decisions/ADR-0003-contract-identity.md) | SHA256 canonical contract identity |
| [0004](../decisions/ADR-0004-lock-first.md) | Exclusive lease acquired before reconstruction |
| [0005](../decisions/ADR-0005-pass-authorization.md) | PASS only via VALIDATING + predicate |
| [0006](../decisions/ADR-0006-adapters-not-core.md) | Stages 1–4 are adapters |
| [0007](../decisions/ADR-0007-dry-run.md) | Dry-run is first-class and mute |
| [0008](../decisions/ADR-0008-implementation-posture.md) | Spec first; Rust intent; no crate cut yet |
| [0009](../decisions/ADR-0009-prior-art-reference.md) | Prior-art Python lives under reference/ only |
| [0010](../decisions/ADR-0010-implementation-freeze.md) | Implementation Freeze v0.2 |
| [0011](../decisions/ADR-0011-exact-allowlist.md) | Exact allowlist match |
| [0012](../decisions/ADR-0012-conformance-v0.3.md) | Conformance completion v0.3 |
| [0013](../decisions/ADR-0013-until-paused-and-residue.md) | run --until-paused + residue |
| [0014](../decisions/ADR-0014-verify-predicate.md) | verify predicate breakdown |
| [0015](../decisions/ADR-0015-adapter-emit.md) | Plan adapter + contract emit |
| [0016](../decisions/ADR-0016-fenced-plan.md) | Fenced plans only; no prose parse |
| [0017](../decisions/ADR-0017-plan-source-identity.md) | Bind emitted contracts to plan hash |
| [0018](../decisions/ADR-0018-pipeline-and-lineage.md) | Explicit lineage, emit --check, pipeline tool |
| [0019](../decisions/ADR-0019-contract-diff.md) | contract diff compares identity |
| [0020](../decisions/ADR-0020-self-plan-and-strict-validate.md) | Self-plan + validate --strict |
| [0021](../decisions/ADR-0021-host-1.0.md) | Host Implementation 1.0 |
| [0022](../decisions/ADR-0022-host-1.0.1.md) | Host 1.0.1 conformance patch |
| [0023](../decisions/ADR-0023-host-1.0.2.md) | Host 1.0.2 observation + cycles |
| [0024](../decisions/ADR-0024-host-1.0.3.md) | Host 1.0.3 repository + evidence binding |
| [0025](../decisions/ADR-0025-host-1.0.4.md) | Host 1.0.4 referential integrity + directory emit |
| [0026](../decisions/ADR-0026-host-1.0.5.md) | Host 1.0.5 authority.sources + stricter validate |
| [0027](../decisions/ADR-0027-host-1.0.6.md) | Host 1.0.6 privilege denial + digest/command checks |
| [0028](../decisions/ADR-0028-host-1.0.7.md) | Host 1.0.7 confinement + BLOCKED runtime + argv |
| [0029](../decisions/ADR-0029-host-1.0.8.md) | Host 1.0.8 isolated Git observation |

## Rules

1. Every semantic change to a FROZEN spec requires a new ADR and a freeze bump.
2. ADRs are append-only. Supersession is recorded, not silent rewrite.
3. An ADR cannot weaken a charter invariant (spec 01 §8) without a major version.
