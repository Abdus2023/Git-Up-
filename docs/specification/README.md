# Git-Up! Specification v0.1

**Status:** FROZEN  
**Date:** 2026-08-12  
**Architecture:** [../ARCHITECTURE.md](../ARCHITECTURE.md)

These twenty documents are the first Git-Up! freeze. They define the independent project. They do not implement it.

| # | Document | Status |
|---|---|---|
| 01 | [Project Charter](01-project-charter.md) | FROZEN |
| 02 | [Scope / Non-Scope](02-scope.md) | FROZEN |
| 03 | [Terminology](03-terminology.md) | FROZEN |
| 04 | [Epistemic Model](04-epistemic-model.md) | FROZEN |
| 05 | [Contract Model](05-contract-model.md) | FROZEN |
| 06 | [Repository Model](06-repository-model.md) | FROZEN |
| 07 | [Task Model](07-task-model.md) | FROZEN |
| 08 | [State Machine](08-state-machine.md) | FROZEN |
| 09 | [Authority Model](09-authority-model.md) | FROZEN |
| 10 | [Execution Model](10-execution-model.md) | FROZEN |
| 11 | [Evidence Model](11-evidence-model.md) | FROZEN |
| 12 | [Provenance Model](12-provenance-model.md) | FROZEN |
| 13 | [Concurrency Model](13-concurrency-model.md) | FROZEN |
| 14 | [Recovery Model](14-recovery-model.md) | FROZEN |
| 15 | [Traceability Model](15-traceability-model.md) | FROZEN |
| 16 | [Security Model](16-security-model.md) | FROZEN |
| 17 | [CLI Contract](17-cli-contract.md) | FROZEN |
| 18 | [Test Strategy](18-test-strategy.md) | FROZEN |
| 19 | [Phase Mapping 1–29](19-phase-mapping.md) | FROZEN |
| 20 | [ADR Index](20-adr-index.md) | FROZEN |

## Reading order

Charter → Scope → Terminology → Epistemic model → Contract / Repository / Task → State machine → Authority → Execution / Evidence / Provenance → Concurrency / Recovery → Traceability / Security → CLI / Tests → Phase map / ADRs.

## Change control

Edits to a FROZEN document require a new ADR and a bump of the freeze identifier (v0.1 → v0.1.1 for errata, v0.2 for semantic change). Silent drift is a specification defect.
