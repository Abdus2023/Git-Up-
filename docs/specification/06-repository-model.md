# 06 — Repository Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

Git-Up! treats Git as the worktree and identity substrate, not as a thing to wrap or replace.

## 1. One control domain

v0.1 operates on **one Git worktree** and **one lease**. Multi-repo orchestration is out of scope.

Default root: `git rev-parse --show-toplevel`, overridable.

## 2. Repository identity

```
RepositoryIdentity {
    repository_id     // stable per-worktree id
    remote_identity   // optional; informational in v0.1
    branch            // optional
    HEAD              // object name; empty if not a git repo → fail closed for mutating ops
    worktree          // resolved absolute path
    dirty_state       // porcelain summary
}
```

### 2.1 `repository_id`

A stable UUID stored at `.git-up/repo.identity`.

- Created on first locked operation if absent.
- Two checkouts MUST receive different identities so evidence cannot be copied across worktrees.
- If the identity file cannot be created during a mutating operation, the operation FAIL-closes.
- Dry-run MUST NOT create the identity file.

### 2.2 HEAD

Read via `git rev-parse HEAD`. Empty HEAD on a mutating run is `FAIL` (no silent “not a git repo” success). Dry-run MAY report empty HEAD as a classification blocker.

### 2.3 Dirty state

Observed via `git status --porcelain` (or equivalent). Used for:

- scope guard (delta confinement),
- optional contract expectation (`repository.dirty_state`),
- reports.

Dirty state is observational. It does not by itself authorize or forbid `PASS` unless the contract declared an expectation or the delta escapes targets.

## 3. Control directory

```
.git-up/
    repo.identity
    state.json            # checkpoint
    state.json.tmp        # crash-safe replace
    evidence.jsonl        # append-only log
    controller.lock       # exclusive lease
```

These paths are Git-Up! artifacts. Scope guards MUST exclude them from “escaped write” detection. They SHOULD be gitignored.

Writes inside `.git/` are prohibited as implementation targets.

## 4. Path confinement

Every contract path (authority source, specification, target, prohibited, expected output) MUST:

- be repository-relative,
- contain no `..` component,
- contain no `~` component,
- not be absolute,
- resolve (including symlink targets) inside the repository root.

Escape → contract invalid or `BLOCKED`, fail closed. Existence is not required for targets that the task is meant to create.

## 5. Observed target state

For each implementation target:

| Condition | Recorded value |
|---|---|
| Absent | `null` |
| Regular file | `sha256` hex |
| Symlink | `link:` + sha256 of resolved content, or `link:broken` |

PASS binds to this map, not to exit status. A file replaced by a symlink is a different state.

## 6. HEAD drift

If a checkpoint records a HEAD that differs from the current HEAD, the controller MUST:

- note drift,
- invalidate sticky non-terminal runtime markers,
- recompute `contract_id` (HEAD is an identity input),
- refuse to treat prior evidence as authorizing unless its recorded HEAD matches the current identity rules in spec 12.

v0.1 default: evidence binds to the HEAD at observation time; authorization requires the evidence `head` to equal the current HEAD **or** a future freeze must define rebase/amend policy. v0.1 does **not** define rebase policy — HEAD mismatch fail-closes PASS.

## 7. Git-Up! is not Git

Git-Up! MUST NOT:

- rewrite published history,
- force-push,
- modify `.git/` as an implementation target,
- treat a commit message as evidence.

It MAY invoke `git` as a declared validation tool if allowlisted.
