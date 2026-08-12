# 09 — Authority Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

## 1. Hierarchy (normative)

```
source / declared contract
    > current contract_id
        > execution observation
            > evidence
                > interpretation
                    > report / ledger / checkpoint
```

Nothing lower may justify a decision reserved to something higher.

## 2. What is a source

A **source** is a repository-relative document named by the contract (`authority.sources`, task `source_authority`, `specification_refs`).

A source is usable only if:

- the path is confined (spec 06),
- it names a readable regular file inside the worktree,
- it is not a directory, dangling link, or escape.

Missing source → `INSUFFICIENT_TASK_DEFINITION`. Git-Up! does not fetch, generate, or substitute sources.

## 3. What the contract authorizes

The current computed `contract_id` is the **identity boundary** of authorization. Evidence bound to any other id is inert for PASS.

Changing a semantic field changes `contract_id` and thereby invalidates prior PASS evidence for that task.

## 4. What the controller is authorized to do

Under a READY execution contract, v0.1 authorizes Git-Up! to:

- run declared validation commands with allowlisted bare tools,
- observe the worktree,
- append evidence,
- write checkpoint and lock files under `.git-up/`.

v0.1 does **not** authorize Git-Up! to edit implementation targets. That is the agent's role. If a validation command writes outside targets, the observation is `FAIL` / `INTEGRATION` (scope violation), not PASS.

## 5. Global authority (component, historical phase 26)

There is no second, implicit authority. In particular:

- environment variables do not add tools to the allowlist;
- CLI `--allow-tool` MAY union with the task allowlist for process invocation, but MUST itself be recorded in the execution context; it MUST NOT silently widen `contract_id` without being part of identity (v0.1: extra allow-tools that are not in the contract are permitted only as a subset refinement — they MUST NOT introduce tools absent from the contract);
- operator belief, PR comments, and agent chat are not sources unless materialized as contract sources.

## 6. Derived views that must never authorize

| View | Role |
|---|---|
| Requirement ledger | Coverage status; task PASS ⇏ requirement SATISFIED unless all covering tasks PASS |
| Coverage identity hash | Detects coverage-graph change; does not authorize |
| Controller JSON report | Describes a run |
| Checkpoint `validated_pass` | Cache to be reconciled |
| Ready queue | Scheduling, not proof |

## 7. Authority problems are blockers, not warnings

If any named authority document is missing, unreadable, or escapes the repository, classification is `BLOCKED`. Execution MUST NOT proceed “best effort.”
