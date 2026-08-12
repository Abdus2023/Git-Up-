# ADR-0030 — Host 1.0.9 evidence-id uniqueness and unknown-state refuse

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.9 (Specification v0.1 unchanged)

## Context

Spec 11 §3: the trusted prefix requires a unique `evidence_id`.
`verified_records` skipped the uniqueness check when the id was empty
(`if eid and eid in seen_ids`). A hand-written chain of empty-id PASS
rows was trusted. Spec 11 §1 requires `evidence_id` on every record.

Spec 11 §1 / spec 04: unknown `result` values are invalid. Append already
raised. A hand-edited JSONL row with `result: GREEN` and a matching hash
was still trusted.

`append` would write a second row with the same id (the tail then became
untrusted). Fail-closed is not to write the break.

Spec 04: unknown state — refuse; do not coerce. `StateStore.load` kept
`state: GREEN`. Recover then called `record_reconstructed_pass`, which
cannot transition GREEN → READY and raised `TransitionError`. A forged
unknown state could crash recovery instead of being discarded.

## Decision

Compatible host patch **1.0.9**:

1. Empty `evidence_id` stops the trusted prefix.
2. A `result` outside `{PASS, FAIL, BLOCKED, NOT_APPLICABLE}` stops the
   trusted prefix.
3. `append` refuses a duplicate `evidence_id` (`EvidenceError`); the log
   is not extended.
4. Checkpoint rows whose `state` is not a `TaskState` value are ignored
   on load (same posture as a corrupt store: reconstruct from evidence).

## Consequences

- Semver **1.0.9**. Specification v0.1 is not bumped.
- Empty-id or `GREEN` evidence cannot authorize PASS.
- Recovering a GREEN checkpoint with valid evidence walks VALIDATING
  instead of crashing.
- Self-contract identity is unchanged.
