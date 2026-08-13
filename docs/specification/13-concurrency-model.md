# 13 — Concurrency Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

This document freezes the Phase-28 invariant for Git-Up! independently of prior-art code. Historical controllers computed authoritative PASS and loaded checkpoints **before** acquiring the lease. That is a known defect. Git-Up! forbids it.

## 1. Exclusive lease

v0.1 concurrency policy is **exclusive**. One controller instance mutates a worktree's `.git-up/` control plane at a time.

Lease file: `.git-up/controller.lock`

Primitive (POSIX): `fcntl.flock(LOCK_EX | LOCK_NB)` on an `O_RDWR|O_CREAT` fd.  
Fallback (no fcntl): `O_EXCL` create of the lock file.

Second acquirer: fail closed immediately (`LockAcquisitionError` → run result `FAIL`, frontier `PAUSED`). No spin in v0.1 default. Blocking acquire is not the default.

Release: unlock, close, best-effort unlink.

## 2. Critical section (MUST)

For every non-dry-run command that classifies authoritatively, executes, writes evidence, or writes a checkpoint:

```
ACQUIRE LOCK
      ↓
build provenance context
      ↓
reconstruct authoritative PASS
      ↓
load + reconcile checkpoint
      ↓
inspect HEAD / dirty state
      ↓
classify
      ↓
(optional) execute + observe
      ↓
append evidence
      ↓
authorize / reclassify
      ↓
atomic checkpoint
      ↓
RELEASE
```

**Invariant C1.** No authoritative decision input may be sampled outside the lease.

**Invariant C2.** The lock is acquired **first**, before reconstruction.

Forbidden (the historical window):

```
Controller A                         Controller B
compute auth_pass(A)
                                     compute auth_pass(B)
load checkpoint(A)
                                     load checkpoint(B)
                                     acquire lock
                                     mutate, evidence, checkpoint, release
acquire lock
use stale auth_pass(A)
```

## 3. What the lease covers

Covered:

- `.git-up/repo.identity` creation
- `.git-up/state.json` read/write
- `.git-up/evidence.jsonl` append
- authoritative classification
- validation process spawn
- HEAD / porcelain sampling used for authorization

Not covered (and MUST NOT be treated as authoritative):

- dry-run reads
- human edits to the worktree by an agent (those are observations, checked by scope guard)

## 4. Dry-run

```
NO LOCK
NO EXECUTION
NO MUTATION
NO EVIDENCE
NO CHECKPOINT
NO IDENTITY-FILE CREATE
```

Dry-run MAY read the contract, worktree, and evidence log. It MUST label outputs advisory. Two dry-runs may race; that is acceptable because they do not write.

## 5. Recover

`git-up recover` is a mutating command: it MUST take the lease, reconstruct, demote unsupported checkpoint claims, write a fresh checkpoint, execute nothing, duplicate no evidence, then release. Idempotent.

## 6. Crash while holding the lease

- Advisory `flock` dies with the process → lease released by the kernel.
- `O_EXCL` fallback MAY leave a stale lock file. v0.1: do not break the lock automatically. Operator removes it. A future freeze may add a documented break-glass with recorded evidence.

## 7. Multi-worktree

Different worktrees have different `.git-up/` directories and different `repository_id`s. They MAY run concurrently. Evidence is not portable between them.

## 8. Threads / async

v0.1 specifies process-level exclusion only. Internal threads MUST NOT perform a second unlocked authoritative reconstruction.
