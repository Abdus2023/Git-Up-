# Git-Up!

**Git-Up! is an evidence-driven implementation controller that turns declared implementation contracts into deterministic, auditable, verified repository changes.**

It does not decide what should be built. It verifies that an explicitly declared implementation contract was executed correctly.

```
Any Source → Git-Up! Contract → Git-Up! Controller → Git repository
```

## Status

| Freeze | Role |
|---|---|
| [Specification v0.1](docs/specification/README.md) | Identity, models, invariants |
| [Implementation v0.11](docs/IMPLEMENTATION-FREEZE.md) | Controller + adapters + pipeline + diff |
| [Conformance audit](docs/traceability/conformance.md) | Phase → impl → test → gap |
| [HOWTO](docs/HOWTO.md) | Operator / agent workflow |

```
Contract     = WHAT MAY BE DONE
Execution    = WHAT WAS DONE
Evidence     = WHAT CAN BE PROVEN
```

A successful command is never sufficient for `PASS`.

## Quick start

```bash
python3 ./git-up classify
python3 ./git-up plan
python3 ./git-up run --dry-run
python3 ./git-up contract emit --from examples/plans/example.json --out /tmp/c.json
python3 -m unittest discover -s tests -p 'test_*.py'
```

The default `--contract` is the repo-root [self-contract](git-up.contract.json).

`git-up run --dry-run` is mute:

```
NO LOCK · NO EXECUTION · NO MUTATION · NO EVIDENCE · NO CHECKPOINT
```

Mutating commands acquire the exclusive lease **first**, then reconstruct, classify, execute, observe, record, and checkpoint.

## Layout

```
git-up              CLI driver
git_up/             host implementation (A–M module map)
tests/              spec 18 invariant suites
docs/               frozen specification + ADRs
examples/           sample contracts and plans
tools/              mute pipeline (not the controller)
reference/          prior-art audit material only
```

The intended native crate cut is documented in the implementation freeze. The host implementation is Python 3 stdlib because a Rust toolchain cannot be fetched in this environment. It is **not** a port of `reference/red-cognition-controller/`.

## CLI

```
git-up inspect | reconstruct | contract validate | contract emit | contract diff | plan | classify | ready
git-up run [--dry-run] [--until-paused] | verify | evidence | status | recover | audit | trace
```

## License

MIT. See [LICENSE](LICENSE).
