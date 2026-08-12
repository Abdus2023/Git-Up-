# Conformance audit — Specification v0.1 × host 1.0.2

**Status:** derived (not authority)  
**Date:** 2026-08-12

Format: **Phase → Invariant → Implementation → Test → Evidence → Gap**

This is the audit the methodology called for. It does not authorize PASS.

## Components A–M

| Phase | Invariant | Implementation | Test | Evidence | Gap |
|---|---|---|---|---|---|
| 1 State model | Explicit VALIDATING; no READY→PASS | `git_up/model.py` ALLOWED_TRANSITIONS | I-PASS-1 | self-contract after `run` | none |
| 2 Classification | Fail-closed; never writes PASS | `git_up/classify.py` | I-AUTH-1, I-COV-1, I-PASS-5 | `git-up classify` | none |
| 3 Dependencies | Only PASS is auto-satisfiable | `classify_task` | I-PASS-5 | pipeline example | none |
| 4 Authority | Hierarchy; missing doc blocks | `authority_missing` | I-AUTH-1 | — | none |
| 5 Contract identity | SHA256 canonical | `git_up/identity.py` | I-ID-1, I-ID-2 | `contract_id` on evidence | none |
| 6 Canonicalization | List order non-semantic | `canonical.py` + identity sort | I-ID-1 | — | none |
| 7 Provenance | validator=`git-up`; HEAD bound | `provenance_context` | I-HEAD-1, I-PASS-4 | evidence records | none |
| 8 Evidence | Hash chain; trust prefix | `git_up/evidence.py` | I-EVID-1, I-EVID-2 | `.git-up/evidence.jsonl` | none |
| 9 Validators | No shell; exact allowlist | `git_up/safety.py` | I-SAFE-1 | — | none |
| 10 Execution | Declared commands only | `git_up/execute.py` | I-REC-2, I-TIMEOUT | — | none |
| 11 Result integrity | Target hashes + expected outputs | `task_may_pass` | I-PASS-2, I-SCOPE-1 | — | none |
| 12 PASS authorization | Predicate; no shortcuts | `authorize.py` + VALIDATING | I-PASS-1…5 | `git-up verify` | none |
| 13 Recovery | Evidence > checkpoint | `checkpoint.py` + reconstruct | I-PASS-3, I-REC-1 | `git-up recover` | none |
| 14 Crash consistency | Atomic replace; fsync order | `StateStore.save`, `EvidenceLog.append` | I-REC-1 | — | mid-fsync FS lie out of scope |
| 15 Determinism | Same inputs → same ids | identity + queue sort | I-ID-1, determinism suite | — | none |
| 16 Traceability | CLOSED required for PASS | `closure_gaps` | I-COV-1, I-LEDGER-1 | `git-up trace` | none |
| 17–23 Hardening | Folded into F/I/M/16 | residue, truncation, exact allowlist | I-SAFE-1, truncation, pycache | — | none |
| 24–25 Coverage | Ledger derived | `requirement_statuses` | I-LEDGER-1 | `git-up trace` | none |
| 26 Global authority | CLI cannot widen tools | `effective_allowlist` | I-SAFE-1 | — | none |
| 27 State machine | Forbidden transitions | `StateStore.transition` | I-PASS-1 | — | none |
| 28 Concurrency | Lock **first** | `Controller.run` | I-LOCK-1, I-LOCK-2 | phase_log | none vs spec; prior art still wrong |
| 29 External consistency | HEAD mismatch fail-closes PASS | identity includes HEAD | I-HEAD-1 | — | no rebase policy (fail closed) |

## Charter

| ID | Status |
|---|---|
| CH-1…CH-7 | discharged (see [invariant-register](invariant-register.md)) |
| S1, C1, C2, R1–R3, T1–T3 | discharged |

## Remaining non-gaps (explicit non-scope)

- Rust native crates (toolchain unavailable)
- Stages 1–4 adapters
- Signed evidence / rebase policy
- Multi-repo / network service

## How to re-run the audit

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 ./git-up verify --dry-run
python3 ./git-up audit
```
