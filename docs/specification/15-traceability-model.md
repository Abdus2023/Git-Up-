# 15 — Traceability Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

## 1. Required chain

```
requirement → specification → task → contract_id → validation → evidence → status
```

A break anywhere is a closure gap. PASS requires `closure = CLOSED`.

## 2. Per-task handoff (derived report)

Each task reports:

- `task_id`, `status`
- `contract_id`
- `closure`: `CLOSED` | `OPEN`
- `closure_gaps[]`
- `criterion_attestations[]` (strict mode; else empty)
- `requirement_refs[]`
- `specification_refs[]`
- `source_authority[]`
- `implementation_targets[]`
- `validation_commands[]`
- `evidence_refs[]`
- `blocker_class`, `blocker_reasons[]`

This view is derived. It cannot authorize.

## 3. Closure gaps (normative list)

Emit a gap if:

- no requirement refs,
- no specification refs,
- no validation commands,
- no acceptance criteria,
- (legacy) a command has no PASS evidence bound to current `contract_id`,
- (strict) a criterion has `NO_CRITERION_ATTESTATION`,
- any bound evidence has `validator != "git-up"`.

## 4. Requirement ledger (derived)

```
Requirement { id, specification_refs[], coverage[] { task_id, obligations[] } }

status:
    NO_COVERAGE   — no covering tasks declared
    BLOCKED       — none of the covering tasks are PASS
    PARTIAL       — some, not all, covering tasks are PASS
    SATISFIED     — all covering tasks are PASS
```

**Invariant T1.** Task PASS does not imply requirement SATISFIED unless every declared covering task is PASS.

**Invariant T2.** The ledger never authorizes task PASS.

**Invariant T3.** The ledger is recomputed each run from the authoritative PASS set; it is never read back as input.

## 5. Coverage identity

`coverage_identity = SHA256(canonical(sorted requirement coverage graph))`.  
Detects change. Not an authorization input.

## 6. `git-up trace`

Emits the per-task handoff and the ledger. Read-only if `--dry-run` / default inspect; under lease if asked to persist a report file inside `.git-up/` (v0.1: writing reports outside `.git-up/` is allowed without treating them as authority; writing inside `.git-up/` requires the lease).

## 7. Adapter traceability

Adapters SHOULD record `provenance.source_identity` and `producer`. Git-Up! treats those as informational. It traces **its** chain, not the adapter's internal reasoning.
