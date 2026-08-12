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
