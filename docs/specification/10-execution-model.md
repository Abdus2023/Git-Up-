# 10 — Execution Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

## 1. What “execute” means in v0.1

`git-up run` (without `--dry-run`) under the lease:

1. classifies,
2. takes the head READY task,
3. transitions `READY → IN_PROGRESS`,
4. runs each declared **validation command** that does not already have PASS evidence for the current `contract_id`,
5. observes after each command,
6. transitions `IN_PROGRESS → VALIDATING`,
7. evaluates the authorization predicate,
8. records evidence (already appended per command),
9. checkpoints,
10. authorizes `PASS` or `FAIL`.

Git-Up! does not implement product features and does not apply arbitrary patches.

## 2. Command rules

Commands are executed with `shell = false`.

A command is runnable only if safety validation succeeds (spec 16):

- non-empty string, no NUL, no shell metacharacters (`; & | > < \` $ \\` and control chars),
- bare executable (no `/`, no `\`, no leading `.`),
- executable is not a shell interpreter (`sh`, `bash`, `dash`, `zsh`, `ksh`, `csh`, `tcsh`, `ash`, `busybox`, `fish`),
- executable is in the effective allowlist,
- no absolute path arguments,
- no `..` path arguments,
- empty allowlist ⇒ nothing authorized.

Unsafe command → evidence `BLOCKED`, not executed.

## 3. Environment

- `cwd` = repository root.
- Timeout: contract `policy.timeout_seconds` or implementation default (spec: default 600s). Timeout → `FAIL`.
- Missing binary → `BLOCKED` (`TOOLCHAIN` / tool not found).
- stdout/stderr captured and truncated for storage (v0.1: last 4000 units each); truncation MUST be indicated if applied. Truncation does not by itself invalidate a structurally valid PASS, but expected-output / target-hash checks still apply.

## 4. Idempotency

A validation command whose `command_id` already has chain-verified PASS evidence for `(task_id, current contract_id)` MUST NOT be re-executed or re-recorded.

## 5. Observation (component H)

After each command, record at least:

- argv / command string
- exit status (or null on timeout / spawn failure)
- stdout / stderr (truncated as specified)
- `observed_delta`: porcelain paths newly dirty, minus `.git-up/` artifacts
- `target_hashes`: spec 06 map
- timestamp (observational)
- `contract_id`, repository identity, HEAD, source identity, validator identity
- `command_id`

Compare `observed_delta` to `implementation_targets`. Any path outside targets and outside `.git-up/` is a **scope violation** → result `FAIL`, class `INTEGRATION`. A successful exit cannot override this.

## 6. Expected outputs

If `expected_outputs` is non-empty, authorization requires each path to exist with the declared sha256 **at validation time**. Exit 0 is never enough.

## 7. Dry-run

`--dry-run` MUST:

- acquire no lease,
- execute no command,
- write no evidence, checkpoint, identity file, or lock,
- still produce classification, dependency analysis, planned execution contract, and *expected* evidence shape,
- label output `mode: dry-run` / advisory.

## 8. Plan / classify / ready

These commands are dry-run-class by default (no mutation). They MUST NOT be used as authorization.

## 9. Determinism of execution planning

The sequence of commands considered for a task is the set of validation commands whose `command_id` is not yet PASS-bound. Set membership is order-independent for identity; execution order is the contract's declared command list order (stable). Identity ignores that order; execution honors it.
