# ADR-0027 — Host 1.0.6 privilege denial and load-time command/digest checks

- Status: accepted
- Date: 2026-08-12
- Freeze: Git-Up! Host 1.0.6 (Specification v0.1 unchanged)

## Context

Spec 16 §8: Git-Up! MUST NOT invoke `sudo` and MUST NOT require root. Shell
interpreters were denied even if allowlisted; `sudo` was not. An allowlisted
`sudo python3` would have run.

A validation command with an empty string was accepted at load and only
BLOCKED at execute. An `expected_outputs` entry with a short or empty digest
was accepted and could never PASS.

`git-up evidence` dumped the trusted prefix with no indication of whether a
record is bound to the current provenance context (spec 06 §6). That is
advisory, not authorization.

## Decision

Compatible host patch **1.0.6**:

1. Privilege-escalation frontends `sudo`, `su`, `doas`, `pkexec` are denied
   even if allowlisted. Same posture as the shell-interpreter set. Spec names
   `sudo`; the others are the same root-escalation class under
   “MUST NOT require root.”
2. A declared validation command with an empty `command` is `ContractError`.
3. Each `expected_outputs` entry must have a path and a 64-hex `sha256`.
4. `git-up evidence` annotates each trusted record with
   `bound_to_current_context` (advisory). If the contract cannot be loaded,
   the flag is `null`.
5. Restore confinement of contract-level `authority.sources` and surface them
   on `inspect`.

## Consequences

- Semver **1.0.6**. Specification v0.1 is not bumped.
- `sudo` cannot be a validator, even if the contract lists it.
- Dry-run `evidence` without `repo.identity` reports `bound_to_current_context:
  false` for records written under a mutating run. That is correct, not PASS.
