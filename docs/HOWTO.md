# How to use Git-Up!

Git-Up! does not implement your feature. It verifies that a **declared contract** was executed correctly.

```
write a contract
        ↓
git-up contract validate
git-up plan --dry-run
        ↓
an agent or human edits the worktree
        ↓
git-up run
        ↓
git-up evidence
git-up trace
```

## 1. Declare a contract

Hand-write JSON, or emit from a plan (adapter; does not invent fields):

```bash
python3 ./git-up contract emit --from examples/plans/example.json --out /tmp/emitted.json
python3 ./git-up contract emit --from examples/plans/example.md --out /tmp/emitted.json --check
python3 ./git-up contract emit --from examples/plans/example.json --out /tmp/v2.json --parent /tmp/emitted.json
python3 ./git-up --contract /tmp/emitted.json classify
python3 tools/pipeline.py --plan examples/plans/example.json --out /tmp/c.json
python3 ./git-up contract diff /tmp/emitted.json /tmp/v2.json
```

See `examples/contracts/example.json` and spec 05. Minimum for `READY`:

- authority source file that exists in the repo
- requirement ref + specification ref
- at least one validation command and acceptance criterion
- `allowed_tools` (bare names)
- `policy.failure_mode = fail_closed`
- `policy.concurrency = exclusive`

## 2. Inspect without mutating

```bash
python3 ./git-up --contract path/to/contract.json inspect
python3 ./git-up --contract path/to/contract.json contract validate
python3 ./git-up --contract path/to/contract.json plan
python3 ./git-up --contract path/to/contract.json run --dry-run
```

Dry-run guarantees: no lock, no execution, no evidence, no checkpoint, no `repo.identity`.

## 3. Implement, then verify

The agent may change only `files_allowed_to_change` from the emitted execution contract.

```bash
python3 ./git-up --contract path/to/contract.json run
python3 ./git-up --contract path/to/contract.json run --until-paused
python3 ./git-up --contract path/to/contract.json verify --dry-run
python3 ./git-up --contract path/to/contract.json status
python3 ./git-up --contract path/to/contract.json recover
```

`PASS` is not “the command exited 0.” It is the authorization predicate (spec 11).

## 4. This repository

`git-up.contract.json` at the root is a **self-contract**: its validator is the spec 18 unit suite. `git-up classify` should report that task `READY` (or `PASS` after a successful `run`).

Do not invoke `git-up run` on the self-contract from inside those unit tests.

After a successful `git-up run` here, `git-up status` reports `T-SPEC18 = PASS` and `git-up evidence` shows a chain-verified record. That is Git-Up! authorizing its own suite — not a unit test declaring itself green.

## 5. Exit codes

| Code | Meaning |
|---|---|
| 0 | Controller process succeeded (includes PAUSED / clean dry-run) |
| 1 | Validation / authorization FAIL |
| 2 | Contract or usage error |
| 3 | Internal error |
| 4 | Lease unavailable |
