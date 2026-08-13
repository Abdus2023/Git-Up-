# 18 — Test Strategy

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

Tests exist to protect invariants, not to mirror prior-art filenames.

## 1. Principle

Every MUST in specs 04–17 maps to at least one test obligation below. A future implementation freeze is incomplete until the obligation is discharged.

Do not treat a green self-test of the Python prior-art package as Git-Up! evidence.

## 2. Suites

| Suite | Protects |
|---|---|
| `tests/contract/` | Schema, identity stability, canonicalization, insufficient definition |
| `tests/execution/` | Command safety, allowlist, timeout, idempotent skip |
| `tests/evidence/` | Chain integrity, structural PASS, truncation flags |
| `tests/recovery/` | Atomic checkpoint, corrupt store, crash worlds, no dup evidence |
| `tests/concurrency/` | Lock-first, second instance fail-closed, no pre-lock auth_pass |
| `tests/determinism/` | Same inputs → same ids, queue, classification |
| `tests/state/` | Allowed/forbidden transitions, VALIDATING gate |
| `tests/authority/` | Missing docs, escape paths, ledger non-authority |
| `tests/traceability/` | Closure gaps, strict vs legacy coverage |
| `tests/security/` | Shell metacharacters, symlink escape, `.git` targets, dry-run non-mutation |

## 3. Invariant tests (normative obligations)

| ID | Invariant | Attack / case |
|---|---|---|
| I-PASS-1 | No READY→PASS | Attempt direct promotion |
| I-PASS-2 | No exit0→PASS | Command succeeds, target hash wrong |
| I-PASS-3 | No checkpoint→PASS | Forge `validated_pass` |
| I-PASS-4 | No unbound evidence→PASS | Evidence for old `contract_id` |
| I-PASS-5 | Fixpoint deps | A depends on B; B not PASS |
| I-LOCK-1 | Lock first | Instrumentation: reconstruction after acquire only |
| I-LOCK-2 | Second writer | Two mutating runs; one FAIL code 4 |
| I-DRY-1 | Dry-run mute | No lock file, no evidence, no state, no identity create |
| I-EVID-1 | Broken chain | Flip a byte mid-log; tail untrusted |
| I-EVID-2 | Dup id | Second same evidence_id breaks trust |
| I-REC-1 | Corrupt checkpoint | Truncated JSON; reconstruct continues |
| I-REC-2 | No re-exec | PASS commands not run again |
| I-SCOPE-1 | Outside target | Validator writes other path → FAIL |
| I-SAFE-1 | `bash -c` | BLOCKED even if allowlisted |
| I-ID-1 | List reorder | Requirements permuted; `contract_id` stable |
| I-ID-2 | Content change | Command string change; id changes; old PASS inert |
| I-HEAD-1 | HEAD drift | Amend HEAD; old evidence cannot PASS |
| I-AUTH-1 | Missing spec file | BLOCKED insufficient |
| I-COV-1 | Strict gap | Criterion without validator |
| I-LEDGER-1 | Ledger ≠ authority | SATISFIED ledger cannot PASS an uncovered task |

## 4. Concurrency test specifically for C1

The historical defect is pre-lock reconstruction. Tests MUST demonstrate (by API hooks or ordering probes) that `auth_pass`, checkpoint load, and HEAD sample used for authorization occur **after** successful `acquire`.

## 5. Determinism

No wall-clock in `contract_id`. Timestamps may appear in evidence and reports but not in identity payloads. Tests fail if two runs in the same repo with frozen inputs disagree on ids or queues.

## 6. No pytest requirement (implementation note)

A future Rust test harness (`cargo test`) is expected. The strategy is harness-agnostic.

## 7. Evidence of testing

CI SHOULD run the suites. CI green is a derived report. It does not authorize a Git-Up! task PASS unless a contract names those tests as validators and the predicate holds.
