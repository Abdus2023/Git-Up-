# 16 — Security Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

Git-Up! is fail-closed. Ambiguity is never permission.

## 1. Threats in scope (v0.1)

| Threat | Mitigation |
|---|---|
| Command injection via validation strings | No shell; metacharacter reject; no shell interpreters |
| Path escape / symlink escape | Confinement on every contract path; `.git` writes banned |
| Scope creep (writes outside targets) | Porcelain delta check → FAIL INTEGRATION |
| Evidence tampering / truncation | Hash chain; trust prefix only |
| Checkpoint forgery of PASS | Reconstruction ignores checkpoint for PASS |
| Replay across repos / commits / tasks | `contract_id` binding |
| Concurrent controllers | Exclusive non-blocking lease; lock-first |
| Allowlist bypass | Empty allowlist denies all; CLI cannot add undeclared tools |
| Agent self-certification | Belief is not observation |
| Dry-run presented as proof | Mode label required; no artifacts |

## 2. Threats out of scope (v0.1)

- Compromised operator account
- Kernel-level flock bypass / hostile filesystem that lies about fsync
- Supply-chain compromise of allowlisted binaries
- Multi-tenant remote service abuse
- Cryptographic anonymity / signed evidence by a third-party notary (may be a later freeze)

## 3. Command safety (normative)

See spec 10 §2. Additional rules:

- Reject characters: `; & | > \` $ < \\` and ASCII controls including TAB/CR/LF and DEL.
- Executable MUST be a bare name on the allowlist.
- Shell interpreters are denied even if allowlisted.
- Absolute arguments and `..` components denied.

## 4. Path safety (normative)

`validate_targets` / authority paths:

- no absolute, no `..`, no `~`, no `.git` component,
- resolved path (and symlink target) must stay in-repo,
- existence not required for create-targets.

## 5. Integrity safety

- Evidence: chained sha256, unique ids, durable append before checkpoint reference.
- Checkpoint: atomic replace; corrupt → empty.
- Identity: per-worktree UUID; not copied in evidence reuse.

## 6. Confidentiality

v0.1 does not encrypt the evidence log. Treat `.git-up/` as sensitive if commands printed secrets. Spec does not authorize redaction that would break hashes; avoid putting secrets in validators.

## 7. Availability

Non-blocking lock: a holder prevents other mutating runs. Dry-run remains available. Stale `O_EXCL` lock requires operator intervention (spec 13 §6).

## 8. Privilege

Git-Up! MUST NOT require root. It MUST NOT invoke `sudo`. It MUST NOT modify `.git/` as a target.

## 9. Supply of policy

Security policy lives in the contract (`allowed_tools`, targets, prohibited scope) plus these invariants. Environment variables cannot widen authority.
