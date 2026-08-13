# ADR-0022 — Host 1.0.1 conformance patch

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.1 (Specification v0.1 unchanged)

## Context

Host 1.0.0 implemented Specification v0.1. Review found several fail-closed
misses that did not require a new spec freeze:

1. Spec 10 §2 / 16 §3 reject `&`. The host character set omitted it.
2. Spec 09 §5 requires CLI `--allow-tool` to be recorded and to refine, never
   widen. An empty intersection silently fell back to the full contract set.
3. Spec 14's crash world "evidence complete → reconstruct PASS via VALIDATING"
   left `IN_PROGRESS` in the checkpoint forever. Classification was correct
   (evidence is authority) but the cache was not reconciled.
4. Spec 08 §5: `REJECTED` / `DEFERRED` are contract-terminal. Reconstruction
   applied PASS before those flags.
5. Spec 05 §3: commands with an empty effective tool set should not be READY.
6. Spec 11 §4: skip / attestation treated `result == PASS` as enough; structural
   PASS is the necessary form.
7. Relative `--contract` was cwd-relative while `--state` / `--evidence` resolve
   under the repo root.

## Decision

Compatible host patch **1.0.1**:

1. Reject `; & | > < \` $ \\` and ASCII controls.
2. `cli_allow is None` → contract tool set. A provided list intersects. Empty
   intersection is empty (deny all). Record `cli_allow_tool` and
   `effective_allowlist` on the execution contract. Do not put them in
   `contract_id`.
3. After demoting unbacked PASS, persist reconstructed PASS only by walking
   `→ READY → IN_PROGRESS → VALIDATING → PASS`. Clear crashed
   `IN_PROGRESS`/`VALIDATING` that is not authoritative.
4. Contract `rejected` / `deferred` outrank reconstructed PASS. `task_may_pass`
   is false for those tasks.
5. Non-empty `validation_commands` with empty `allowed_tools ∪ required_tools`
   is `INSUFFICIENT_TASK_DEFINITION`.
6. Idempotent skip and criterion attestation require structural PASS.
7. Relative `--contract` resolves under `--repo-root` / git toplevel.
8. `inspect` and `contract validate` report `document_identity`
   (`source_identity` of the loaded contract). Advisory; not authorization.

## Consequences

- Semver **1.0.1**. Specification v0.1 is not bumped.
- `--allow-tool typo` now denies execution instead of ignoring the flag.
- Operators can match `document_identity` without a mutating run.
- A native Rust 1.0 remains a separate artifact (toolchain still unavailable).
