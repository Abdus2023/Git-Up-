# 11 — Evidence Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

Evidence is the only acceptable proof of validation. It is not the contract and not the execution.

## 1. Record

```
EvidenceRecord {
    evidence_id
    task_id
    command
    command_id
    stdout, stderr
    exit_status                  // int or null
    result                       // PASS | FAIL | BLOCKED | NOT_APPLICABLE
    failure_class                // optional
    expected_exit
    timestamp
    artifacts[]                  // { path, sha256, bytes }
    notes
    contract_id
    repository_identity
    head
    source_identity              // contract document hash
    validator                    // "git-up"
    target_hashes
    observed_delta[]
    prev_hash
    record_hash
}
```

Unknown `result` values are invalid. The record MUST be rejected at append time.

## 2. Log

Append-only JSONL at `.git-up/evidence.jsonl`.

- `prev_hash` of the first record is `""`.
- `record_hash = SHA256(canonical(record without record_hash))`.
- Append is durable: write, flush, fsync (best-effort if the FS rejects fsync; still flush).
- A checkpoint MAY reference an evidence_id only after a successful append.

## 3. Trust

`verified_records()` is the trusted prefix:

- parseable UTF-8 JSON objects,
- `prev_hash` matches previous `record_hash`,
- `record_hash` matches recomputation,
- `evidence_id` unique.

Any break (tamper, missing line, malformed JSON, wrong hash, duplicate id) **stops the trusted stream**. The broken record and all later records are untrusted. Fail closed.

Integrity report: `{ total, trusted, intact, broken_at }`.

## 4. Structural PASS (necessary, not sufficient)

A record is a **structural PASS** only if:

- `result == PASS`,
- `exit_status` is an integer,
- `exit_status == expected_exit`,
- `command` is non-empty.

Structural PASS is **necessary** for authorization and **never sufficient**.

## 5. Authorization predicate (component J)

A task MAY enter `PASS` only if **all** hold:

1. Predecessor state is `VALIDATING`.
2. The evidence log's trusted prefix is used exclusively.
3. Every declared validation command (legacy mode) or every acceptance criterion (strict mode) has a structural PASS record with:
   - `task_id` matching,
   - `contract_id` equal to the **current** computed id,
   - matching `command_id`,
   - `validator == "git-up"`.
4. Authority documents currently exist and are readable in-repo.
5. Every PASS-required dependency is in the authoritative PASS set (fixpoint).
6. `closure_gaps(...)` is empty (spec 15).
7. If the task has implementation targets: at least one authorizing PASS record's `target_hashes` equals the **current** observed target hash map.
8. If the task has `expected_outputs`: each exists with the declared digest now.
9. No authorizing PASS record is accompanied by an unremediated scope violation for that command.

The authoritative PASS set is the least fixpoint of this predicate over the task graph.

## 6. Forbidden shortcuts

The following MUST NOT imply PASS:

- exit status 0
- presence of any evidence row
- checkpoint `validated_pass`
- dry-run classification
- agent self-report
- “the tests looked green” in notes

## 7. Evidence vs. interpretation

Interpretation (failure class, report narrative, ledger) is derived. If interpretation disagrees with the record fields, the record wins; the interpretation is repaired, not the other way around.
