# 04 — Epistemic Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

This document freezes *what Git-Up! is allowed to know* and *how strongly it may claim it*.

## 1. The four questions

```
WHAT IS SUPPOSED TO HAPPEN     →  contract plane (declared)
WHAT GIT-UP! MAY DO            →  current contract_id + policy
WHAT ACTUALLY HAPPENED         →  execution-plane observation
WHAT CAN BE PROVEN             →  chained evidence
```

A fifth question — *what should we build?* — is **out of epistemic scope**. Adapters and humans answer it. Git-Up! MUST NOT.

## 2. Strength of claims

Claims are totally ordered by strength. A weaker artifact MUST NOT be used to justify a stronger claim.

```
source / declared contract
        >
    current contract_id
        >
    execution observation
        >
    evidence record
        >
    evidence interpretation
        >
    derived report / ledger / checkpoint
```

Consequences:

- A beautiful report cannot create a `PASS`.
- A checkpoint flag `validated_pass: true` cannot create a `PASS`.
- A green exit status cannot create a `PASS`.
- An evidence record that is not bound to the **current** `contract_id` cannot create a `PASS`.
- A requirement ledger is always derived.

## 3. The non-amplification rule

**No claim becomes stronger merely because it moved downstream.**

If the contract is incomplete, execution cannot complete it.  
If the observation is missing, evidence cannot invent it.  
If the evidence is unbound, a report cannot rebind it.

## 4. Fail closed

When any of the following hold, Git-Up! MUST refuse the stronger claim:

| Condition | Required response |
|---|---|
| Missing required contract field | `BLOCKED` / contract invalid; never guess |
| Conflicting specifications declared | `BLOCKED` (`SPECIFICATION_CONFLICT`) |
| Authority document missing, unreadable, or escaping the repo | `BLOCKED` (`INSUFFICIENT_TASK_DEFINITION`) |
| Tool claimed available but not on PATH | `BLOCKED` (`TOOLCHAIN`) |
| Dependency not authoritatively PASS | `BLOCKED` (`DEPENDENCY`) |
| Evidence chain broken | ignore the break and everything after; never trust the tail |
| Checkpoint corrupt | discard checkpoint; reconstruct from evidence |
| Lock unavailable | `FAIL` / `PAUSED`; do not proceed unlocked |
| Unknown result / unknown state | refuse; do not coerce |

## 5. Reconstruction over memory

Authoritative state is **reconstructed** every locked cycle from:

1. the current contract document (and its identity),
2. the current repository identity and HEAD,
3. the verified prefix of the evidence log.

The checkpoint is a hint for resume bookkeeping (attempts, in-progress markers) and MUST be reconciled against reconstruction. Any checkpoint `PASS` not in the reconstructed set is demoted.

## 6. Dry-run epistemology

Dry-run answers: *if we locked and ran now, what would we attempt?*  
It MUST be labeled `advisory`. It MUST NOT write evidence or checkpoints. It MUST NOT be cited later as authorization.

## 7. Agent belief

An agent's assertion that it succeeded is **not an observation**. It MAY appear in notes. It MUST NOT enter the authorization predicate.

## 8. Time

Timestamps are observational metadata. They do not authorize. Temporal validity means: the evidence was produced under the `contract_id` / HEAD / repository identity it names. Replay across those identities is invalid regardless of timestamp.
