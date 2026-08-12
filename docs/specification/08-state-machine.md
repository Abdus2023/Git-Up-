# 08 — State Machine

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

## 1. Stored task states

```
DISCOVERED | READY | IN_PROGRESS | VALIDATING | PASS | FAIL | BLOCKED | REJECTED | DEFERRED
```

## 2. Report-only states

| Name | Meaning |
|---|---|
| `PAUSED` | Frontier: no READY task. Not stored on a task. |
| `ADVISORY` | Label on dry-run classifications. Not a task state. |

## 3. Allowed transitions

```
DISCOVERED  → READY | BLOCKED | REJECTED | DEFERRED
READY       → IN_PROGRESS | BLOCKED | REJECTED | DEFERRED
IN_PROGRESS → VALIDATING | FAIL | BLOCKED
VALIDATING  → PASS | FAIL
FAIL        → READY | BLOCKED | IN_PROGRESS | DISCOVERED
BLOCKED     → READY | BLOCKED | REJECTED | DEFERRED
PASS        → ∅          # terminal
REJECTED    → ∅          # terminal
DEFERRED    → ∅          # terminal
```

`READY → BLOCKED` occurs when reclassification under the lock finds a gate no longer holds.

`IN_PROGRESS → BLOCKED` occurs if a safety/scope/authority failure is detected before validation completes.

Crash while `IN_PROGRESS` is recovered as: reconstruct; if predicate holds → may become `PASS` via `VALIDATING`; otherwise demote to `DISCOVERED`/`BLOCKED`/`FAIL`. Never leave a crashed `IN_PROGRESS` as implicit PASS. See spec 14.

## 4. Forbidden transitions (MUST reject)

```
DISCOVERED      → PASS
READY           → PASS
IN_PROGRESS     → PASS          # must pass through VALIDATING
BLOCKED         → PASS
FAIL            → PASS          # must re-enter IN_PROGRESS/VALIDATING
CHECKPOINT_FLAG → PASS
EVIDENCE_EXISTS → PASS
EXIT_0          → PASS
ADVISORY        → PASS
```

**Invariant S1.** Every terminal `PASS` transition MUST have predecessor `VALIDATING` and a true authorization predicate (spec 11 §4).

## 5. Sticky vs. reclassified

| Class | States | Rule |
|---|---|---|
| Terminal | `PASS`, `REJECTED`, `DEFERRED` | Not recomputed by the classifier. `PASS` is still **re-checked** by reconstruction: a checkpoint `PASS` without current predicate is demoted to `DISCOVERED`. `REJECTED`/`DEFERRED` remain until the contract flips the corresponding flag. |
| Reclassifiable | `DISCOVERED`, `READY`, `IN_PROGRESS`, `VALIDATING`, `FAIL`, `BLOCKED` | Recomputed every locked cycle from contract + evidence + repo identity. |

The classifier never writes `PASS`. Reconstruction + authorization does.

## 6. Lifecycle (normative narrative)

```
DISCOVERED
    │  prerequisites satisfied under lock
    ▼
  READY
    │  acquire already held; select queue head
    ▼
IN_PROGRESS
    │  execute declared validators / observe
    ▼
VALIDATING
    │
    ├─ predicate holds  →  PASS
    └─ predicate fails  →  FAIL
```

`PAUSED` is reported when the ready queue is empty after classification.

## 7. Blocker precedence (primary class)

When multiple blockers apply, the primary class is the first match:

1. `SPECIFICATION_CONFLICT`
2. `INCOMPLETE_SPECIFICATION`
3. `DEPENDENCY`
4. `TOOLCHAIN`
5. `INSUFFICIENT_TASK_DEFINITION`
6. `TRACEABILITY`
7. `ARCHITECTURE`
8. `PROVISIONING`
9. `AUTHORIZATION`
10. `ENVIRONMENT`
11. `INFRASTRUCTURE`

All classes are retained in `reasons[]`. Fail closed: report all.

## 8. Determinism

Given identical contract, identical verified evidence prefix, identical repository identity and HEAD, identical tool PATH facts: classification, ready queue, and `contract_id` MUST be identical. List order in inputs MUST NOT matter after canonicalization.

## 9. Implementation note (non-normative)

Historical prior art omitted `VALIDATING` as an explicit stored state and allowed `IN_PROGRESS → PASS`. Git-Up! tightens this: `PASS` is unreachable except from `VALIDATING`.
