# Changelog

Derived history. Not authority.

## 1.0.7 — 2026-08-12

- `authority.sources` and requirement `specification_refs` are confined (spec 06 §4)
- `IN_PROGRESS → BLOCKED` for unsafe/missing-tool evidence; scope/exit stay FAIL
- Missing binary records `failure_class: TOOLCHAIN`
- Validation `command` accepts an argv list (canonicalized with shlex.join)

## 1.0.6 — 2026-08-12

- `sudo` / `su` / `doas` / `pkexec` denied even if allowlisted (spec 16 §8)
- Empty validation commands and non-sha256 `expected_outputs` are ContractError
- `git-up evidence` annotates `bound_to_current_context` (advisory)

## 1.0.5 — 2026-08-12

- Contract-level `authority.sources` are confined and must exist (spec 09)
- `--strict` also fails on TRACEABILITY / spec conflict / spec gap
- Authority refs that are not a string or object are ContractError

## 1.0.4 — 2026-08-12

- Duplicate/empty tool, requirement, command, and criterion ids fail closed
- Coverage must name a declared task; dangling requirement_refs are TRACEABILITY
- `contract emit --from DIR` requires exactly one plan among `*.json`/`*.md`
- `contract emit --check` also enforces a declared repository bind

## 1.0.3 — 2026-08-12

- Authorizing evidence must match current HEAD / repo identity / source / validator
- Declared `repository.identity` / `revision` / `dirty_state=clean` are enforced
- Unknown dependency refs and malformed list items fail closed (ContractError)
- Plan adapter passes through an explicit `repository` block; does not invent one

## 1.0.2 — 2026-08-12

- `prohibited_scope` is enforced even under an allowed target
- Porcelain uses `-z` / `-uall`; rename/copy observes both paths
- Dependency cycles (and self-loops) are BLOCKED with an explicit chain
- `observed_delta` records in-target product writes
- Spec 11 §5.9: a PASS record with a scope delta cannot authorize

## 1.0.1 — 2026-08-12

- Spec 10/16: reject `&` with the other shell metacharacters
- Spec 09: `--allow-tool` is recorded; empty intersection denies (no fallback)
- Spec 14: recover writes reconstructed PASS only via VALIDATING
- Spec 08: REJECTED/DEFERRED outrank reconstructed PASS
- Spec 05: empty tool set + commands is INSUFFICIENT_TASK_DEFINITION
- Structural PASS required for skip and criterion attestation
- Relative `--contract` resolves under the repo root
- `inspect` / `contract validate` report `document_identity`

## 1.0.0 — 2026-08-12

- Host Implementation 1.0 of Specification v0.1 (ADR-0021)
- Committed `git-up.contract.json` must match `emit(docs/plans/self.md)`

## 0.11.0 — 2026-08-12

- Self-plan `docs/plans/self.md` is the source of `git-up.contract.json`
- `contract validate --strict` fails on INSUFFICIENT_TASK_DEFINITION

## 0.10.0 — 2026-08-12

- `git-up contract diff A B` — identity comparison (ADR-0019)

## 0.9.0 — 2026-08-12

- `contract emit --parent` explicit lineage
- `contract emit --check` confinement without execute
- `tools/pipeline.py` mute emit → validate → classify

## 0.8.0 — 2026-08-12

- Emitted contracts bind `provenance.source_identity` to the plan hash

## 0.7.0 — 2026-08-12

- Fenced `git-up-plan` blocks; prose is never parsed

## 0.6.0 — 2026-08-12

- Plan adapter and `contract emit`

## 0.5.0 — 2026-08-12

- `verify` predicate breakdown
- Conformance audit table

## 0.4.0 — 2026-08-12

- `run --until-paused`
- Interpreter residue ignored by scope guard

## 0.3.0 — 2026-08-12

- Command-specific CLI payloads
- Evidence truncation flags
- Self-contract

## 0.2.0 — 2026-08-12

- Host controller (lock-first, VALIDATING, authorization predicate)

## 0.1.0 — 2026-08-12

- Specification Freeze (docs 01–20)
