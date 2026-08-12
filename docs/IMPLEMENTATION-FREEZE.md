# Git-Up! Implementation Freeze v0.2

**Declared:** 2026-08-12  
**Status:** IN FORCE  
**Depends on:** Specification Freeze v0.1  
**ADR:** [ADR-0010](decisions/ADR-0010-implementation-freeze.md)

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

`python3 -m unittest discover -s tests -p 'test_*.py'` — spec 18 IDs I-PASS-1…5, I-LOCK-1/2, I-DRY-1, I-EVID-1/2, I-REC-1/2, I-SCOPE-1, I-SAFE-1, I-ID-1/2, I-HEAD-1, I-AUTH-1, I-COV-1, I-LEDGER-1.

## 6. Out of scope for v0.2

- Adapters (Stages 1–4)
- Network service / multi-repo
- Signed evidence / rebase policy
- Editing implementation targets (agents do that)
- crates.io dependencies
