# 02 — Scope / Non-Scope

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

## 1. In scope for the Git-Up! core

The controller, given a declared implementation contract and a Git worktree:

- validate the contract structurally and against repository identity;
- reconstruct authoritative state from evidence + contract (never from checkpoint alone);
- classify tasks fail-closed;
- emit execution contracts only for `READY` tasks;
- acquire an exclusive lease for every non-dry-run operation;
- execute only declared validation / permitted execution commands;
- observe worktree deltas and target hashes;
- append tamper-evident evidence;
- authorize `PASS` / `FAIL` / `BLOCKED` by predicate;
- persist crash-safe checkpoints that are always subordinate to evidence;
- recover idempotently;
- report status, traceability, and audit views as **derived** artifacts.

## 2. In scope as adapters (not core)

Anything that *produces* a Git-Up! contract from some other artifact:

- RFC / specification extractors
- issue / PR / design-doc adapters
- AI-plan adapters
- Red/Cognition plan adapters
- repository reconstruction and requirement mining

Adapters MAY live in this repository later. They are not required for v0.1 freeze and MUST NOT leak their vocabulary into the core models.

## 3. Explicitly out of scope

Git-Up! is **not**:

| Non-scope | Why |
|---|---|
| A product feature implementer | Agents and humans implement; Git-Up! verifies |
| A Git replacement | Git remains the VCS |
| A build system | It may *invoke* declared tools; it does not own builds |
| A planner / architect | It does not decide what should be built |
| A cognition / specification ecosystem | That is a possible upstream |
| A general workflow engine | Only implementation contracts over a Git worktree |
| A secret store, policy engine, or IAM system | It consumes declared authority; it does not issue identity |
| A multi-repo orchestrator (v0.1) | One worktree, one lease |
| A network service (v0.1) | Local CLI / library |

## 4. v0.1 documentation scope vs. later implementation scope

| Now (this freeze) | Later (authorized by a future freeze) |
|---|---|
| Identity, models, invariants, CLI names, tests | Rust implementation, crate cut, adapters |
| Conceptual contract schema | Byte-stable serialization RFC |
| `.git-up/` names | On-disk versioning scheme beyond v1 |

## 5. Coupling ban

The following MUST NOT appear as required inputs to Git-Up! core:

- Red/Cognition RFC numbers or document paths
- Rebol / Red toolchain assumptions
- `implementation-plan.json` as the only manifest shape
- `.impl_controller/` paths
- any planner-specific task id scheme

Prior-art paths may be cited in `reference/` and in ADRs as historical notes only.

## 6. Failure-mode scope

When Git-Up! cannot decide safely, it MUST:

- refuse execution,
- classify `BLOCKED` or return `FAIL`,
- record why,
- never invent missing authority, validators, or hashes.
