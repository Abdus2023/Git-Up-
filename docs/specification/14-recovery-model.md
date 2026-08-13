# 14 — Recovery Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

## 1. Thesis

On restart Git-Up! NEVER assumes prior runtime state is still valid. It reconstructs from contract + verified evidence + repository identity, then reconciles the checkpoint downward.

## 2. Checkpoint

Path: `.git-up/state.json`

```
{
    schema_version: "git-up.state.v1",
    last_checkpoint: iso8601,
    repo_head: string,
    tasks: [ TaskRuntimeState ]
}

TaskRuntimeState {
    task_id
    state
    validated_pass          // cache only
    in_progress
    last_classification
    evidence_refs[]
    attempts
    updated_at
}
```

### Atomic write

Write `state.json.tmp` → flush → fsync → `rename`/`replace`. A crash mid-write leaves the previous file intact.

### Corrupt checkpoint

JSON parse failure → treat as empty store. Do not trust a half-file. Reconstruct from evidence.

## 3. Reconstruction

Under the lease:

1. Load contract; fail closed on invalid.
2. Build provenance context (may create `repo.identity` only on mutating recover/run).
3. Compute authoritative PASS set from the evidence predicate (spec 11 §5), **ignoring** `validated_pass` flags.
4. Load checkpoint if parseable.
5. Demote every checkpoint `PASS` / `validated_pass` not in the reconstructed set → `DISCOVERED`, clear `in_progress`.
6. If checkpoint HEAD ≠ current HEAD: record drift; do not treat old HEAD-bound evidence as authorizing (spec 06 §6).
7. Reclassify.
8. Persist a new checkpoint.
9. Execute nothing. Append nothing.

Safe to call repeatedly. `git-up recover` is this procedure.

## 4. Crash during IN_PROGRESS

Possible worlds:

| World | Recovery |
|---|---|
| Evidence for all commands appended and predicate holds | Reconstruct → PASS (via VALIDATING bookkeeping); no re-exec |
| Partial evidence | Missing commands remain; task not PASS; may become READY again |
| Evidence append interrupted (broken tail) | Trusted prefix only; tail untrusted |
| Checkpoint not yet replaced | Old checkpoint + new evidence; reconstruction prefers evidence |
| Checkpoint replaced, evidence not flushed | Should be impossible if evidence is fsynced before checkpoint references it. If it happens, dangling evidence_id is ignored |

**Invariant R1.** Evidence is authoritative over checkpoint.  
**Invariant R2.** Checkpoint MUST NOT be written with a new evidence_id until that record is durable.  
**Invariant R3.** Recovery never duplicates evidence.

## 5. Illegal recovery shortcuts

Recovery MUST NOT:

- promote to PASS because `in_progress` was true,
- promote to PASS because `attempts > 0`,
- copy evidence from another worktree,
- repair a broken hash chain by rewriting history,
- execute validators (that is `run`, not `recover`).

## 6. Idempotency of run

Re-running after a completed PASS for the current `contract_id` MUST NOT re-execute those commands (spec 10 §4) and MUST remain PASS under reconstruction.
