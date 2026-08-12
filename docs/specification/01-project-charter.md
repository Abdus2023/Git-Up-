# 01 — Project Charter

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

## 1. Name

**Git-Up!** (product)  
**`git-up`** (CLI)  
Repository: `Git-Up-`

## 2. One-sentence thesis

Git-Up! is a contract-driven Git implementation and verification controller that converts an explicit implementation contract into controlled repository execution, observation, evidence, and authoritative completion.

## 3. Mission

Give any implementation source — a human plan, an RFC, an issue, a design document, or an AI coding agent — a single, fail-closed controller that:

1. accepts only an explicit contract,
2. classifies what is authorized to run,
3. executes only under an exclusive lease,
4. observes what actually changed,
5. records tamper-evident evidence,
6. authorizes `PASS` only when an independently verifiable predicate holds.

## 4. The fundamental principle

**Git-Up! does not decide what should be built. It verifies that an explicitly declared implementation contract was executed correctly.**

No claim becomes stronger merely because it moved downstream.

## 5. Why it exists independently

The methodology was proven as a Stage-5 controller inside another ecosystem. That ecosystem is a *possible upstream*. It is not Git-Up!'s identity, vocabulary, layout, or runtime.

Git-Up! therefore:

- owns its own specification, tests, release history, and terminology;
- treats Stages 1–4 (extraction, reconstruction, requirements, contract production) as adapters;
- begins at `DECLARED CONTRACT → CONTROLLER`.

## 6. Users

| User | Relationship |
|---|---|
| Human implementer | Declares a contract; Git-Up! verifies the work |
| AI coding agent | Executes inside the contract; cannot self-certify |
| Reviewer / auditor | Reads evidence, trace, and status; never trusts a report as authority |
| CI system | Runs `git-up` as a gate |
| Upstream planner | Emits a Git-Up! contract via an adapter |

## 7. Success for v0.1

v0.1 succeeds if, and only if, a competent implementer can build Git-Up! from these documents **without consulting Red/Cognition sources**, and the resulting system honors every MUST invariant in specs 04–16.

v0.1 does **not** require working product code.

## 8. Non-negotiable invariants (charter-level)

1. Contract, execution, and evidence are distinct objects.
2. `PASS` requires a valid predecessor state and an independently verifiable authorization predicate.
3. A successful command is never sufficient for `PASS`.
4. Exclusive lease for all non-dry-run authoritative operations; lock is acquired first.
5. Dry-run mutates nothing: no lock, no execution, no evidence, no checkpoint.
6. Reports and checkpoints describe or cache; they never authorize.
7. Fail closed: unknown, insufficient, or conflicting inputs yield `BLOCKED` or `FAIL`, never guessed `READY` or `PASS`.

## 9. Stewardship

Changes to this charter require ADR + freeze bump. See [20 — ADR Index](20-adr-index.md).
