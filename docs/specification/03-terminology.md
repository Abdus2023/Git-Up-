# 03 — Terminology

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

Words in this document are normative. Do not import Red/Cognition names as required vocabulary.

## 1. Product terms

| Term | Meaning |
|---|---|
| **Git-Up!** | The product: a contract-driven implementation and verification controller. |
| **`git-up`** | The CLI. |
| **Controller** | The component that classifies, locks, executes, observes, records, and authorizes. |
| **Adapter** | A non-core producer of a Git-Up! contract from some upstream artifact. |
| **Agent** | An external implementer (human or model) that may change the worktree inside a contract. |

## 2. Plane terms

| Term | Meaning |
|---|---|
| **Contract plane** | What Git-Up! is authorized to do. |
| **Execution plane** | What actually happened in the worktree / processes. |
| **Verification** | The comparison of observation against contract that may yield `VALIDATED`. |

## 3. Object terms

| Term | Meaning |
|---|---|
| **Implementation contract** (or **contract**) | The central declared object. See spec 05. |
| **`contract_id`** | `SHA256(canonical(authoritative_contract))`. Identity boundary. |
| **Task** | A unit of authorized work inside a contract. |
| **Acceptance criterion** | A stated condition of success. |
| **Validator** | A declared command that attests one or more criteria. |
| **Implementation target** | A worktree path the contract permits to change. |
| **Prohibited scope** | A worktree path the contract forbids to change. |
| **Expected output** | A path that must exist with a declared digest after success. |

## 4. Epistemic terms

| Term | Meaning |
|---|---|
| **Authoritative** | May justify a controller decision. Only sources and the current contract are authoritative. |
| **Derived** | Computed view (report, ledger, graph). Never authorizes `PASS`. |
| **Advisory** | Dry-run or unlocked classification. Must be labeled. MUST NOT be checkpointed as authority. |
| **Observation** | Measured execution-plane fact (exit status, hashes, porcelain delta). |
| **Evidence** | A chained, structured record of an observation bound to a `contract_id`. |
| **Authorization predicate** | The closed list of conditions that alone may yield `PASS`. |

## 5. State terms

| Term | Meaning |
|---|---|
| **DISCOVERED** | Task is known; prerequisites not yet shown. |
| **READY** | All classification gates pass; not yet leased for execution. |
| **IN_PROGRESS** | Lease held; execution or observation underway. |
| **VALIDATING** | Execution finished; predicate being evaluated. |
| **PASS** | Terminal success; predicate held. |
| **FAIL** | Validation did not hold; reclassifiable. |
| **BLOCKED** | Cannot proceed; all reasons reported. |
| **PAUSED** | Frontier: nothing READY. Report-level, not a stored task state. |
| **REJECTED** | Explicitly refused. Terminal. |
| **DEFERRED** | Explicitly parked. Terminal. |

## 6. Concurrency and recovery terms

| Term | Meaning |
|---|---|
| **Lease** | Exclusive controller lock over the worktree's `.git-up/` control plane. |
| **Checkpoint** | Crash-safe cache of runtime state. Subordinate to evidence. |
| **Evidence log** | Append-only, hash-chained record file. |
| **Reconstruction** | Recompute authoritative PASS set from contract + evidence + repository identity. |
| **Drift** | Detected mismatch (HEAD, contract hash, checkpoint claim vs. evidence). |
| **Fail closed** | Ambiguity becomes refusal, never permission. |

## 7. Forbidden equivalences

The following MUST NOT be treated as synonyms:

| Forbidden pair | Why |
|---|---|
| exit 0 ≡ PASS | Observation ≠ authorization |
| evidence exists ≡ PASS | Record may be FAIL, stale, or unbound |
| checkpoint PASS ≡ PASS | Cache is not authority |
| task PASS ≡ requirement satisfied | Coverage is derived and many-to-many |
| dry-run classification ≡ authoritative classification | No lease, advisory only |
| report ≡ contract | Reports describe; contracts authorize |

## 8. Spelling

Use **Git-Up!** in prose, **`git-up`** in commands, **`.git-up/`** for the control directory. Do not use `impl_controller`, `implementation-plan`, or `RFC-0075` as required names.
