# ADR-0004 — Exclusive lease acquired before reconstruction

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Specification v0.1

## Context

Prior-art `tools/impl_controller/controller.py` did:

```
load manifest → provenance → auth_pass → load checkpoint
→ inspect HEAD → ACQUIRE LOCK → classify → execute → …
```

Two processes could compute `auth_pass` on the same unlocked snapshot; the later acquirer could classify from a stale set after the earlier writer mutated evidence and checkpoint. The lock primitive (`flock` / `O_EXCL`) was sound; the **critical-section boundary** was not.

The Phase-28 statement “exclusive flock for ALL non-dry-run operations” is stronger than “lock before execute.”

## Decision

For every non-dry-run authoritative operation, Git-Up! acquires the exclusive lease **first**, then reconstructs, classifies, executes, observes, records, and checkpoints under that lease. Dry-run takes no lock and writes nothing.

## Consequences

- CLI `run` narrative that listed lock after “build contract” is superseded by this ADR.
- Tests MUST prove reconstruction happens after acquire (spec 18 I-LOCK-1).
- Second mutating instance fails closed (exit 4).
