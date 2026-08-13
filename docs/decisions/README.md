# Architecture Decision Records

Format: short Markdown, one decision per file.

```
# ADR-NNNN — Title
Status: accepted | superseded | withdrawn
Date: YYYY-MM-DD
Freeze: Git-Up! Specification vX.Y
```

Context → Decision → Consequences → Notes (optional).

## Index

| ADR | Status | Title |
|---|---|---|
| [0001](ADR-0001-independence.md) | accepted | Independence from Red/Cognition |
| [0002](ADR-0002-two-planes.md) | accepted | Two planes |
| [0003](ADR-0003-contract-identity.md) | accepted | Contract identity |
| [0004](ADR-0004-lock-first.md) | accepted | Lock-first critical section |
| [0005](ADR-0005-pass-authorization.md) | accepted | PASS authorization |
| [0006](ADR-0006-adapters-not-core.md) | accepted | Adapters are not core |
| [0007](ADR-0007-dry-run.md) | accepted | Dry-run mute guarantee |
| [0008](ADR-0008-implementation-posture.md) | accepted | Spec first; no crate proliferation |
| [0009](ADR-0009-prior-art-reference.md) | accepted | Prior art under reference/ |
| [0010](ADR-0010-implementation-freeze.md) | accepted | Implementation Freeze v0.2 |
| [0011](ADR-0011-exact-allowlist.md) | accepted | Exact allowlist match |
| [0012](ADR-0012-conformance-v0.3.md) | accepted | Conformance completion v0.3 |
| [0013](ADR-0013-until-paused-and-residue.md) | accepted | run --until-paused + residue |
| [0014](ADR-0014-verify-predicate.md) | accepted | verify predicate breakdown |
| [0015](ADR-0015-adapter-emit.md) | accepted | Plan adapter + contract emit |
| [0016](ADR-0016-fenced-plan.md) | accepted | Fenced plans only; no prose parse |
| [0017](ADR-0017-plan-source-identity.md) | accepted | Bind emitted contracts to plan hash |
| [0018](ADR-0018-pipeline-and-lineage.md) | accepted | Explicit lineage, emit --check, pipeline tool |
| [0019](ADR-0019-contract-diff.md) | accepted | contract diff compares identity |
| [0020](ADR-0020-self-plan-and-strict-validate.md) | accepted | Self-plan + validate --strict |
| [0021](ADR-0021-host-1.0.md) | accepted | Host Implementation 1.0 |
| [0022](ADR-0022-host-1.0.1.md) | accepted | Host 1.0.1 conformance patch |
| [0023](ADR-0023-host-1.0.2.md) | accepted | Host 1.0.2 observation + cycles |
| [0024](ADR-0024-host-1.0.3.md) | accepted | Host 1.0.3 repository + evidence binding |
| [0025](ADR-0025-host-1.0.4.md) | accepted | Host 1.0.4 referential integrity + directory emit |
| [0026](ADR-0026-host-1.0.5.md) | accepted | Host 1.0.5 authority.sources + stricter validate |
| [0027](ADR-0027-host-1.0.6.md) | accepted | Host 1.0.6 privilege denial + digest/command checks |
| [0028](ADR-0028-host-1.0.7.md) | accepted | Host 1.0.7 confinement + BLOCKED runtime + argv |
| [0029](ADR-0029-host-1.0.8.md) | accepted | Host 1.0.8 isolated Git observation |
| [0030](ADR-0030-host-1.0.9.md) | accepted | Host 1.0.9 evidence uniqueness + unknown state |
| [0031](ADR-0031-host-1.0.10.md) | accepted | Host 1.0.10 flag-style path arguments |
| [0032](ADR-0032-host-1.0.11.md) | accepted | Host 1.0.11 directory target observation |
