# ADR-0016 — Fenced plans only; never parse prose

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Implementation Freeze v0.7

## Context

Issues, design docs, and agent transcripts are natural adapter inputs. Parsing their prose for tasks would invent a plan — the adapter would become a planner.

## Decision

`contract emit` accepts:

1. A whole-file `git-up.plan.v0.1` JSON document, or
2. Exactly one fenced block: ` ```git-up-plan ` containing that JSON, or
3. Exactly one ` ```json ` fence whose object is a `git-up.plan.v0.1` plan, or
4. stdin (`--from -`) under the same rules.

Multiple matching fences, or markdown with no fence, **fail closed**. Headings, lists, and chat text are never sources of tasks.

## Consequences

A GitHub issue or design doc can carry a plan without Git-Up! reading the issue. The human (or another system) must declare the plan explicitly.
