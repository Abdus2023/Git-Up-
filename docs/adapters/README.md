# Adapter protocol

**Status:** Implementation Freeze v0.6  
**ADR:** [ADR-0015](../decisions/ADR-0015-adapter-emit.md)

Adapters produce Git-Up! contracts. They are **not** the controller.

```
Any Source  →  Adapter  →  Implementation Contract  →  Git-Up! core
```

Emitted contracts bind `provenance.source_identity` to the **plan object**, not the wrapping document (ADR-0017).

## Rules

1. An adapter MAY fill `policy` with `fail_closed` / `exclusive` (core constants).
2. An adapter MUST NOT invent authority documents, requirement ids, validators, or acceptance criteria.
3. Missing definition fields stay empty. Classification then BLOCKS. That is success for the adapter.
4. Adapter output is a contract document, not PASS.
5. `provenance.producer` names the adapter. It is informational (spec 12 §8).

## Plan schema

`git-up.plan.v0.1` — see `examples/plans/example.json`.

A design note or issue may carry **exactly one** fenced plan. Prose is ignored (ADR-0016):

````markdown
```git-up-plan
{ "schema_version": "git-up.plan.v0.1", "tasks": [ ... ] }
```
````

```bash
python3 ./git-up contract emit --from examples/plans/example.json --out /tmp/c.json
python3 ./git-up contract emit --from examples/plans/example.md --out /tmp/c.json
python3 ./git-up contract emit --from - --out /tmp/c.json < examples/plans/example.json
# directory: exactly one *.json / *.md plan; 0 or >1 fails closed
python3 ./git-up --contract /tmp/c.json classify
```

## Non-adapters

Red/Cognition RFCs, GitHub issues, and AI chat logs are future adapters. They are not in v0.6 core.
