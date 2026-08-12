# Git-Up!

**Git-Up! is an evidence-driven implementation controller that turns declared implementation contracts into deterministic, auditable, verified repository changes.**

It does not decide what should be built. It verifies that an explicitly declared implementation contract was executed correctly.

```
Any Source
   │
   ├── RFC
   ├── specification
   ├── issue
   ├── design document
   ├── AI-generated plan
   └── human implementation plan
          │
          ▼
   Git-Up! Contract
          │
          ▼
   Git-Up! Controller
          │
          ▼
   Git repository
```

## Status

**Specification Freeze v0.1** is in force.

Do not implement crates, CLI commands, or runtime behavior until a later freeze authorizes it. The canonical documents live under [`docs/`](docs/README.md).

| Document | Role |
|---|---|
| [Architecture Freeze v0.1](docs/ARCHITECTURE.md) | Two planes, lifecycle, independence |
| [Specification v0.1](docs/specification/README.md) | Charter through ADR index (01–20) |
| [ADR index](docs/decisions/README.md) | Binding design decisions |
| [Prior-art note](reference/red-cognition-controller/README.md) | Extracted principles only |

## Core identity

Git-Up! sits **above Git**. Git is the version-control system. Git-Up! is the implementation-control system.

```
Contract     = WHAT MAY BE DONE
Execution    = WHAT WAS DONE
Evidence     = WHAT CAN BE PROVEN
```

These three are never merged. A successful command is never sufficient for `PASS`. A report can describe authority; it cannot become authority.

```
source > contract > execution observation > evidence interpretation > report
```

## Lifecycle

```
AUTHORITATIVE INPUTS
        ↓
RECONSTRUCTION          ← adapters (not core)
        ↓
REQUIREMENTS
        ↓
IMPLEMENTATION CONTRACT
        ↓
GIT-UP!
        ↓
LOCK                    ← first for every non-dry-run operation
        ↓
CLASSIFY
        ↓
EXECUTE
        ↓
OBSERVE
        ↓
VERIFY
        ↓
EVIDENCE
        ↓
RECONCILE
        ↓
PASS / FAIL / BLOCKED
```

Stages 1–4 (input, reconstruction, requirements, contract production) are **adapters**. Git-Up! core begins at a declared contract.

## Independence

Git-Up! does **not** depend on Red/Cognition RFCs, terminology, repository layout, or runtime. Red/Cognition may later become one possible upstream contract producer. The Python controller under `reference/red-cognition-controller/` is prior art for audit, not product code.

## Planned CLI (not implemented in v0.1)

```
git-up inspect
git-up reconstruct
git-up contract validate
git-up plan
git-up classify
git-up ready
git-up run
git-up verify
git-up evidence
git-up status
git-up recover
git-up audit
git-up trace
```

`git-up run --dry-run` is a first-class mode with a hard guarantee:

```
NO LOCK · NO EXECUTION · NO MUTATION · NO EVIDENCE · NO CHECKPOINT
```

## License

MIT. See [LICENSE](LICENSE).
