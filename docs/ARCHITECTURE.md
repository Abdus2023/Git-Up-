# Git-Up! — Architecture Freeze v0.1

**Status:** FROZEN  
**Date:** 2026-08-12  
**Supersedes:** none  
**Normative companions:** [Specification v0.1](specification/README.md), [ADR index](decisions/README.md)

This document freezes the independent architecture of Git-Up!. It is not a port of the Red/Cognition controller. Principles extracted from that prior art are restated here in Git-Up! terms; hidden assumptions are not imported.

---

## Thesis

**Git-Up! is a contract-driven Git implementation and verification controller. It converts an explicit implementation contract into controlled repository execution, observation, evidence, and authoritative completion.**

The key word is **contract**.

Git-Up! does not need to understand the entire upstream intellectual process. It needs a trustworthy boundary between:

```
WHAT IS SUPPOSED TO HAPPEN
        ↓
WHAT GIT-UP! IS AUTHORIZED TO DO
        ↓
WHAT ACTUALLY HAPPENED
        ↓
WHAT CAN BE PROVEN
```

**Git-Up! does not decide what should be built. It verifies that an explicitly declared implementation contract was executed correctly.**

---

## Independence

```
Red/Cognition
    │
    └── cognitive / specification / governance ecosystem

Git-Up!
    │
    └── independent implementation + verification controller
```

Git-Up! SHALL NOT depend on Red/Cognition RFCs, terminology, repository structure, or runtime. Red/Cognition MAY later become one adapter that produces Git-Up! contracts. Any other producer (human plan, issue, design doc, coding agent) is equally valid.

Stages 1–4 of the historical methodology (input, reconstruction, requirements, contract production) are **adapters**, not Git-Up! core.

Git-Up! core begins at:

```
DECLARED CONTRACT
        ↓
CONTROLLER
```

---

## Two planes

```
                    GIT-UP!
                        │
           ┌────────────┴────────────┐
           │                         │
           ▼                         ▼
    CONTRACT PLANE             EXECUTION PLANE
           │                         │
    specification              repository
    requirements               worktree
    tasks                      commands
    dependencies               tools
    acceptance                 processes
    validators                 observations
    authority                  evidence
           │                         │
           └────────────┬────────────┘
                        ▼
                   VERIFICATION
```

| Plane | Question it answers |
|---|---|
| Contract | What is Git-Up! authorized to execute? |
| Execution | What actually happened? |
| Verification | Does the observation satisfy the contract? |

Execution artifacts MUST NOT silently become contract authority.

---

## Three objects that must never merge

| Object | Meaning |
|---|---|
| Contract | WHAT MAY BE DONE |
| Execution | WHAT WAS DONE |
| Evidence | WHAT CAN BE PROVEN |

Example:

```
Contract:  cargo test --workspace
Execution: exit = 0
Evidence:  stdout + stderr + exit status + repository HEAD
           + contract_id + target state + timestamp + provenance
```

Only after verification: `VALIDATED = TRUE`.  
Only after the complete contract is satisfied: `PASS = TRUE`.

A successful command alone is never sufficient.

---

## Authority hierarchy

```
                    AUTHORITY
                        ▲
                        │
               ┌────────┴────────┐
               │ Authoritative   │
               │ contract/source │
               └────────┬────────┘
                        │
                  execution
                        │
                        ▼
                   observation
                        │
                        ▼
                     evidence
                        │
                        ▼
                  derived reports
```

```
source
  > contract
    > execution observation
      > evidence interpretation
        > report
```

A report can **describe** authority. It cannot **become** authority.  
A checkpoint can **cache** a previously authorized result. It cannot **authorize** one.  
A requirement ledger is a **derived** view. Task `PASS` does not imply requirement satisfaction unless every declared covering task is `PASS`, and the ledger never authorizes task `PASS`.

---

## Git-Up! is not a Git wrapper

| Git knows | Git-Up! additionally knows |
|---|---|
| commit, branch, merge, diff, worktree, repository | contract, task, authority, dependency, acceptance criterion, validator, execution, observation, evidence, provenance, verification, PASS |

Git-Up! uses Git as the worktree and identity substrate. It does not replace Git.

Minimum repository identity:

```
RepositoryIdentity {
    repository_id     // stable per-worktree identity
    remote_identity   // optional
    branch            // optional
    HEAD
    worktree
    dirty_state
}
```

A contract MUST name the repository state it was created against. A mutation of that identity MUST be detected, never silently ignored.

---

## State machine (normative sketch)

Full rules: [08 — State Machine](specification/08-state-machine.md).

```
                 ┌───────────┐
                 │ DISCOVERED│
                 └─────┬─────┘
                       │
                prerequisites
                   satisfied
                       │
                       ▼
                 ┌───────────┐
                 │   READY   │
                 └─────┬─────┘
                       │
                    acquire
                     lease
                       │
                       ▼
               ┌──────────────┐
               │ IN_PROGRESS  │
               └──────┬───────┘
                      │
             ┌────────┴────────┐
             ▼                 ▼
        observation        execution
             │                 │
             └────────┬────────┘
                      ▼
                  VALIDATE
                      │
            ┌─────────┴─────────┐
            ▼                   ▼
         SUCCESS             FAILURE
            │                   │
            ▼                   ▼
        EVIDENCE              FAIL
            │
            ▼
       RECONCILIATION
            │
       ┌────┴────┐
       ▼         ▼
      PASS     BLOCKED
```

`PAUSED` is the execution frontier that cannot currently progress. It is a report state, not a stored task state.

Allowed transitions (normative):

```
DISCOVERED  → READY | BLOCKED | REJECTED | DEFERRED
READY       → IN_PROGRESS | BLOCKED | REJECTED | DEFERRED
IN_PROGRESS → VALIDATING | PAUSED | FAIL | BLOCKED
VALIDATING  → PASS | FAIL
FAIL        → READY | BLOCKED | IN_PROGRESS
BLOCKED     → READY | BLOCKED | REJECTED | DEFERRED
PASS, REJECTED, DEFERRED are terminal (sticky unless an authoritative
prerequisite change forces reclassification of non-PASS terminals
per the recovery rules).
```

Illegal (MUST reject):

```
DISCOVERED → PASS
READY      → PASS
CHECKPOINT → PASS
EVIDENCE_EXISTS → PASS
EXIT_0     → PASS
```

**Every terminal PASS transition MUST have a valid predecessor state and an independently verifiable authorization predicate.**

---

## Contract identity

```
contract_id = SHA256(canonical(authoritative_contract))
```

The payload MUST bind at least:

- validator identity
- repository identity
- HEAD
- contract-source identity (hash of the declared contract document)
- task identity
- requirements, specifications
- dependency state
- tools (id + declared version)
- validation commands (content, not declaration order)
- acceptance criteria
- implementation targets and prohibited scope
- expected outputs
- policy fields that affect authorization

Declaration order of independent lists MUST NOT affect identity. Content MUST.

Evidence records MUST carry `contract_id` so they cannot be replayed across tasks, repositories, commits, or contract revisions.

---

## Critical section (Phase 28, stronger than historical code)

For every **non-dry-run** operation that may classify authoritatively, execute, write evidence, or write a checkpoint:

```
ACQUIRE LOCK
      ↓
reconstruct / classify
      ↓
execute
      ↓
observe
      ↓
evidence
      ↓
checkpoint
      ↓
RELEASE
```

The exclusive lease covers **all** of those steps. Computing an authoritative PASS set, loading a checkpoint, or inspecting HEAD **outside** the lease is a specification violation.

Dry-run is the complementary guarantee:

```
NO LOCK
NO EXECUTION
NO MUTATION
NO EVIDENCE
NO CHECKPOINT
```

Dry-run MAY reconstruct and classify from a snapshot and MUST label the result advisory.

See [13 — Concurrency Model](specification/13-concurrency-model.md) and [ADR-0004](decisions/ADR-0004-lock-first.md).

---

## PASS authorization predicate

A task MAY be `PASS` only if **all** of the following hold:

1. Predecessor state is `VALIDATING` (never `READY`, never `DISCOVERED`).
2. Chain-verified, structurally valid PASS evidence exists for every declared validation command (or, in strict coverage mode, every acceptance criterion is attested).
3. Every such evidence record is bound to the task's **current** `contract_id`.
4. Authority documents exist and are readable inside the repository.
5. Every PASS-required dependency is itself authoritatively PASS (fixpoint).
6. Traceability closure has no gaps.
7. Observed target hashes still match the hashes recorded in the authorizing evidence.
8. Declared expected outputs exist with their declared hashes.
9. Observed worktree delta is confined to declared implementation targets (plus Git-Up! artifacts).
10. The evidence log hash chain is intact through the authorizing records.

A successful command alone is never sufficient.

---

## Agent integration

```
         IMPLEMENTATION AGENT
             /          \
            /            \
      Codex              Claude Code
            \            /
             \          /
           IMPLEMENTATION
                 │
                 ▼
              Git-Up!
                 │
      ┌──────────┴──────────┐
      ▼                     ▼
   Contract             Evidence
      │                     │
      └──────────┬──────────┘
                 ▼
           Verification
```

The agent may implement. Git-Up! verifies.  
The agent MUST NOT be able to declare itself successful merely because it believes it succeeded.

---

## CLI surface (names frozen; implementation not)

```
git-up inspect | reconstruct | contract validate | plan | classify | ready
git-up run | verify | evidence | status | recover | audit | trace
```

`git-up run` conceptually performs:

```
ACQUIRE LOCK          ← first, unless --dry-run
  ↓
LOAD
  ↓
VERIFY AUTHORITY
  ↓
RECONSTRUCT STATE
  ↓
CLASSIFY
  ↓
SELECT READY TASK
  ↓
BUILD CONTRACT
  ↓
EXECUTE               ← skipped in --dry-run
  ↓
OBSERVE
  ↓
VALIDATE
  ↓
RECORD EVIDENCE
  ↓
RECONCILE
  ↓
AUTHORIZE RESULT
  ↓
RELEASE
```

---

## v0.1 architectural baseline (A–M)

Do not create one module per methodological phase. Map phases onto these components:

| ID | Component |
|---|---|
| A | Contract model |
| B | Repository identity |
| C | Task model |
| D | Dependency model |
| E | Classification |
| F | Contract identity |
| G | Execution |
| H | Observation |
| I | Evidence |
| J | PASS authorization |
| K | Checkpoint / recovery |
| L | Concurrency |
| M | Traceability |

Phase mapping: [19 — Phase Mapping](specification/19-phase-mapping.md).

---

## Implementation posture

- **Language (intent, not yet authorized):** Rust workspace, std + carefully chosen crates. Not a Python port.
- **Crate cut:** not frozen. Suggested later: `git-up-core`, `git-up-contract`, `git-up-engine`, `git-up-evidence`, `git-up-cli`.
- **Runtime directory:** `.git-up/` (`repo.identity`, `state.json`, `evidence.jsonl`, `controller.lock`).
- **Prior art:** `reference/red-cognition-controller/` is audit material only.

No product code is authorized by this freeze.
