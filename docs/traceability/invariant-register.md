# Invariant register

Charter invariants (spec 01 §8) plus operational MUST IDs from spec 18.

| ID | Statement | Spec | Test ID |
|---|---|---|---|
| CH-1 | Contract, execution, evidence are distinct | 04, 05, 10, 11 | I-PASS-2 |
| CH-2 | PASS needs predecessor + predicate | 08, 11 | I-PASS-1 |
| CH-3 | Successful command insufficient | 11 §4–6 | I-PASS-2 |
| CH-4 | Exclusive lease; lock first | 13 | I-LOCK-1, I-LOCK-2 |
| CH-5 | Dry-run mutates nothing | 10 §7, 13 §4 | I-DRY-1 |
| CH-6 | Reports/checkpoints do not authorize | 09, 14 | I-PASS-3 |
| CH-7 | Fail closed | 04 §4 | I-AUTH-1, I-SAFE-1 |
| S1 | PASS only from VALIDATING | 08 §4 | I-PASS-1 |
| C1 | No authoritative sample outside lease | 13 §2 | I-LOCK-1 |
| C2 | Lock acquired first | 13 §2 | I-LOCK-1 |
| R1 | Evidence > checkpoint | 14 | I-PASS-3, I-REC-1 |
| R2 | Checkpoint after durable evidence | 14 | I-REC-2 |
| R3 | Recovery does not duplicate evidence | 14 | I-REC-2 |
| T1 | Task PASS ⇏ requirement SATISFIED | 15 | I-LEDGER-1 |
| T2 | Ledger never authorizes task PASS | 15 | I-LEDGER-1 |
| T3 | Ledger is recomputed, never read as input | 15 | I-LEDGER-1 |
| I-TIMEOUT | Timeout is FAIL, not PASS | 10 | `tests/execution/test_timeout.py` |
| I-SYMLINK | Symlink escape fail-closed | 16 | `tests/security/test_symlink.py` |
| I-SAFE-2 | `&` and the spec 16 metacharacter set | 10, 16 | `test_shell_metacharacters_rejected` |
| I-ALLOW-1 | CLI allow-tool refine-only; empty ∩ denies | 09 §5 | `test_empty_cli_allow_intersect_denies` |
| I-REC-3 | Reconstruct PASS only via VALIDATING | 14 | `test_reconstructed_pass_via_validating` |
| I-SCOPE-2 | prohibited_scope wins over targets | 07, 10, 16 | `test_prohibited_scope_inside_target_is_violation` |
| I-SCOPE-3 | Rename/copy both paths observed | 06, 10 | `test_parse_porcelain_rename_includes_both_paths` |
| I-DEP-1 | Dependency cycles never READY | 07 §4 | `test_dependency_cycle_is_blocked` |
