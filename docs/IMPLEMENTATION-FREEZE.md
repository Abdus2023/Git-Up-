# Git-Up! Implementation Freeze v0.3

**Declared:** 2026-08-12  
**Status:** IN FORCE (supersedes v0.2 host surface)  
**Depends on:** Specification Freeze v0.1  
**ADR:** [ADR-0010](decisions/ADR-0010-implementation-freeze.md), [ADR-0012](decisions/ADR-0012-conformance-v0.3.md)

This freeze **authorizes implementation** of Git-Up! against specs 05–18.

## 1. Crate cut (target native layout)

Mapped to components A–M. Not 29 phase crates.

| Crate (future Rust) | Components | v0.2 module |
|---|---|---|
| `git-up-core` | path safety, command safety, canonical hash, git identity (B) | `git_up.canonical`, `git_up.safety`, `git_up.repository` |
| `git-up-contract` | A, C, D, F | `git_up.model`, `git_up.contract`, `git_up.identity` |
| `git-up-evidence` | I, J, M | `git_up.evidence`, `git_up.authorize` |
| `git-up-engine` | E, G, H, K, L + orchestrator | `git_up.classify`, `git_up.queue`, `git_up.lock`, `git_up.checkpoint`, `git_up.controller` |
| `git-up-cli` | spec 17 | `git_up.cli` |

Empty Rust crates are **not** added (ADR-0008). The module map is the port contract.

## 2. Host implementation (v0.2)

A Rust toolchain cannot be fetched in this environment (`static.rust-lang.org` / rustup TLS fail). v0.2 therefore ships a **conforming host implementation** in Python 3.11 **stdlib only**.

This is not a rename of `reference/red-cognition-controller/`. Independent names, `.git-up/` control plane, lock-**first** critical section, explicit `VALIDATING`, validator identity `"git-up"`.

Rust remains the intended native language for a later freeze when a toolchain exists.

## 3. Authorized surface

CLI names from spec 17, implemented by the `git-up` driver:

`inspect`, `reconstruct`, `contract validate`, `plan`, `classify`, `ready`, `run`, `verify`, `evidence`, `status`, `recover`, `audit`, `trace`

## 4. Invariants that MUST hold in this freeze

Every ID in spec 18 §3 is a release gate. See `tests/` suites.

Especially:

- **C1/C2** — lock acquired before reconstruction
- **S1** — PASS only from `VALIDATING` + predicate
- **Dry-run mute** — no lock, evidence, checkpoint, or identity create
- **No claim amplification** — exit 0 / checkpoint / unbound evidence ≠ PASS

## 5. Discharge

`python3 -m unittest discover -s tests -p 'test_*.py'` — spec 18 IDs plus v0.3 CLI/truncation/report-lease tests.

## 6. v0.3 additions

- Command-specific payloads for inspect, plan, reconstruct, contract validate, verify, audit
- `reconstruct --write` ≡ recover
- Evidence `stdout_truncated` / `stderr_truncated`
- `--report` inside `.git-up/` refused in dry-run; mutating writes occur before lease release
- Root `git-up.contract.json` self-contract (validator = spec 18 suite)
- [HOWTO](HOWTO.md)

## 7. Out of scope for v0.3

- Adapters (Stages 1–4)
- Network service / multi-repo
- Signed evidence / rebase policy
- Editing implementation targets (agents do that)
- crates.io dependencies
