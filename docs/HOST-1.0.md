# Git-Up! Host Implementation 1.0

**Declared:** 2026-08-12  
**Status:** IN FORCE  
**Implements:** [Specification Freeze v0.1](specification/README.md)  
**ADR:** [ADR-0021](decisions/ADR-0021-host-1.0.md) … [ADR-0027](decisions/ADR-0027-host-1.0.6.md)

This is version **1.0.6** of the **host** implementation (Python 3.11 stdlib). It is not a Rust native port and not a Red/Cognition runtime. 1.0.x patches are compatible conformance fixes of 1.0.0 (Specification v0.1 unchanged).

## What 1.0 is

A contract-driven controller that:

- classifies fail-closed
- acquires an exclusive lease **before** reconstruction
- executes only declared validators
- authorizes `PASS` only from `VALIDATING` + the predicate
- treats dry-run as mute
- accepts plans only when explicitly declared (JSON or one fence)
- binds emitted contracts to the plan hash
- records parents only when `--parent` is passed

The product self-contract is **emitted** from [`docs/plans/self.md`](plans/self.md). A test requires `emit(self.md)` and the committed `git-up.contract.json` to share document identity.

## What 1.0 is not

| Non-scope | Status |
|---|---|
| Rust crates (`git-up-core`, …) | Future freeze; toolchain was unavailable |
| Stages 1–4 as cognition / RFC mining | Adapters only; prose is not parsed |
| Red/Cognition RFCs or `.impl_controller` | Prior art under `reference/` |
| Multi-repo, network service, signed evidence | Out of scope |
| Rebase / amend policy | HEAD mismatch fail-closes PASS |

## Release gate

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 ./git-up contract emit --from docs/plans/self.md --out /tmp/self.json
python3 ./git-up contract diff git-up.contract.json /tmp/self.json
python3 ./git-up contract validate --strict
```

`contract diff` of the committed file vs a fresh emit must report `identical: true`.

## 1.0.x patches

- 1.0.1 — [ADR-0022](decisions/ADR-0022-host-1.0.1.md)
- 1.0.2 — [ADR-0023](decisions/ADR-0023-host-1.0.2.md): `prohibited_scope`, porcelain rename/`-z`, dependency cycles, honest `observed_delta`
- 1.0.3 — [ADR-0024](decisions/ADR-0024-host-1.0.3.md): evidence context bind; declared `repository` block
- 1.0.4 — [ADR-0025](decisions/ADR-0025-host-1.0.4.md): unique ids, dangling refs, directory emit
- 1.0.5 — [ADR-0026](decisions/ADR-0026-host-1.0.5.md): `authority.sources`; `--strict` contract-shape blockers
- 1.0.6 — [ADR-0027](decisions/ADR-0027-host-1.0.6.md): deny sudo-class executables; sha256/empty-command load checks

No new CLI verbs. No spec bump.
