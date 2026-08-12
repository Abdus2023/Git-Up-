# 17 — CLI Contract

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

Names and semantics are frozen. Implementation is not authorized by this freeze.

## 1. Binary

```
git-up <command> [options]
```

Unknown commands exit non-zero and emit a machine-readable error object.

## 2. Global options

| Option | Meaning |
|---|---|
| `--contract <path>` | Contract document (required for most commands) |
| `--repo-root <path>` | Default: git toplevel |
| `--state <path>` | Default: `.git-up/state.json` |
| `--evidence <path>` | Default: `.git-up/evidence.jsonl` |
| `--report <path>` | Also write JSON report |
| `--quiet` | Suppress stdout report |
| `--dry-run` | Advisory mode (default for inspect/classify/plan/ready) |

## 3. Commands

| Command | Default mode | Lease? | Writes? | Purpose |
|---|---|---|---|---|
| `inspect` | dry-run | no | no | Show contract + repo identity + integrity |
| `reconstruct` | dry-run unless `--write` | only with `--write` | checkpoint if `--write` | Show reconstructed PASS set |
| `contract validate` | dry-run | no | no | Structural + confinement checks |
| `plan` | dry-run | no | no | Classification + contracts + expected evidence |
| `classify` | dry-run | no | no | Per-task states and blockers |
| `ready` | dry-run | no | no | Print ready queue |
| `run` | mutating unless `--dry-run` | yes if mutating | evidence + checkpoint | Full lifecycle |
| `verify` | mutating unless `--dry-run` | yes if mutating | no exec; may refresh derived report | Re-evaluate predicate |
| `evidence` | read | no | no | Show trusted prefix / integrity |
| `status` | read | no | no | Frontier, graph counts, drift notes |
| `recover` | mutating | yes | checkpoint | Spec 14 procedure |
| `audit` | read | no | no | Integrity + forbidden-transition checks on artifacts |
| `trace` | read | no | no | Spec 15 handoff + ledger |

`--write` on `reconstruct` is equivalent to `recover` without extra flags.

## 4. `git-up run` (central)

Mutating:

```
ACQUIRE LOCK
LOAD contract
VERIFY AUTHORITY / confinement
RECONSTRUCT authoritative PASS
RECONCILE checkpoint
CLASSIFY
SELECT ready head
BUILD execution contract
EXECUTE validators (unless none / already bound)
OBSERVE
VALIDATE predicate
RECORD evidence (already appended per command)
RECONCILE / reclassify
AUTHORIZE result
CHECKPOINT
RELEASE
```

`--dry-run`: same analysis through BUILD CONTRACT; stop; no lock; no exec; no writes.

## 5. Exit codes

| Code | Meaning |
|---|---|
| 0 | Controller succeeded as a process. Includes `PAUSED` (nothing READY) and dry-run. |
| 1 | Validation / authorization FAIL (predicate false, scope violation, etc.) |
| 2 | Contract / usage error |
| 3 | Internal controller error |
| 4 | Lease unavailable |

`PASS` as a **task** state is not the same as process exit 0. A run that correctly reports `PAUSED` exits 0.

## 6. Report envelope

Every command that prints a report uses:

```
{
    schema_version: "git-up.report.v1",
    controller: "git-up",
    controller_version: semver,
    mode: "dry-run" | "plan" | "execute" | "recover" | "verify",
    result: "PASS" | "FAIL",
    frontier: "READY" | "PAUSED",
    errors: [],
    drift_notes: [],
    ...
}
```

`result` here is **run result**, not a task PASS. A dry-run that classifies cleanly may say `result: PASS` meaning “the controller run had no errors.” It MUST still set `mode: dry-run` and MUST NOT be archived as task authorization.

## 7. Stability

Command names in §3 are frozen. Adding commands requires an ADR. Removing or renaming a v0.1 command requires a major freeze bump.
