# 19 — Phase Mapping 1–29

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

The 29 methodological phases are a **history of a controller methodology**. They are not a crate plan and not a Red/Cognition dependency. This document maps them onto Git-Up! components A–M so implementers do not recreate 29 modules.

## 1. Components (v0.1 baseline)

| ID | Component | Spec |
|---|---|---|
| A | Contract model | 05 |
| B | Repository identity | 06 |
| C | Task model | 07 |
| D | Dependency model | 07 §4 |
| E | Classification | 07 §8, 08 |
| F | Contract identity | 05 §4, 12 |
| G | Execution | 10 |
| H | Observation | 10 §5 |
| I | Evidence | 11 |
| J | PASS authorization | 11 §5, 08 |
| K | Checkpoint / recovery | 14 |
| L | Concurrency | 13 |
| M | Traceability | 15 |

## 2. Stages 1–4 are adapters

| Stage | Historical name | Git-Up! home |
|---|---|---|
| 1 | Input / extraction | Adapter |
| 2 | Repository reconstruction | Adapter + B (identity only in core) |
| 3 | Requirement & traceability mining | Adapter; M consumes declared refs |
| 4 | Implementation contract production | Adapter output = A |

Core begins at the declared contract.

## 3. Stage 5 phases → components

| Phase | Historical name | Component | Git-Up! notes |
|---|---|---|---|
| 1 | State model | C, E, 08 | Adds explicit `VALIDATING` |
| 2 | Classification | E | Fail-closed; never writes PASS |
| 3 | Dependencies | D | Only PASS is auto-satisfiable |
| 4 | Authority | 09 | Hierarchy frozen |
| 5 | Contract identity | F | SHA256 canonical |
| 6 | Canonicalization | F | Order-independent lists |
| 7 | Provenance | 12 | Validator `git-up` |
| 8 | Evidence | I | Hash-chained JSONL |
| 9 | Validators | G, 16 | Allowlist, no shell |
| 10 | Execution | G | Validation commands only in v0.1 |
| 11 | Result integrity | H, J | Target hashes + expected outputs |
| 12 | PASS authorization | J | Predicate; no shortcuts |
| 13 | Recovery | K | Evidence > checkpoint |
| 14 | Crash consistency | K | Atomic replace, fsync order |
| 15 | Determinism | F, E, 18 | Same inputs → same ids |
| 16 | Traceability closure | M | CLOSED required for PASS |
| 17–23 | Semantic / provenance hardening | F, I, M, 16 | Folded; no extra modules |
| 24–25 | Semantic closure / coverage | M §4–5 | Ledger is derived |
| 26 | Global authority | 09 §5 | No implicit widen |
| 27 | State machine | 08 | Forbidden transitions |
| 28 | Concurrency | L | **Lock first** (stronger than historical code) |
| 29 | External consistency | B §6, J, 18 I-HEAD-1 | HEAD mismatch fail-closes PASS |

## 4. Phase 28 discrepancy (recorded)

Prior-art `controller.py` sampled `auth_pass`, loaded the checkpoint, and inspected HEAD **before** `FileLock.acquire()`. Git-Up! Specification v0.1 treats that as non-conformant. See [ADR-0004](../decisions/ADR-0004-lock-first.md).

## 5. Phase 29 posture

v0.1 external consistency is:

- evidence bound to `(repository_id, HEAD, source_identity, contract_id)`,
- HEAD drift prevents reuse of old evidence,
- worktree delta confined to targets,
- no defined rebase/cherry-pick rewrite policy (fail closed instead).

A later freeze may add signed remotes or rebase policy. Not now.

## 6. Do not implement “Phase N” packages

Forbidden: `git-up-phase-28` as a crate. Required: implement A–M so that the phase obligations in §3 hold.
