# 12 — Provenance Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

## 1. Invariant

A task may reach PASS only when every provenance edge is valid, identity-consistent, repository-consistent, and cryptographically bound. A successful command alone is never sufficient.

## 2. Validator identity

```
validator = "git-up"
```

Evidence with any other validator identity cannot authorize PASS for this controller.

## 3. Provenance context (per locked run)

```
{
    repo_identity,
    head,
    source_identity,     // hash of the contract document
    validator: "git-up",
    tool_versions        // declared versions from the contract registry
}
```

Built **under the lease** for mutating runs. Dry-run may build an advisory context and MUST NOT persist identity files.

## 4. Command identity

```
command_id = SHA256(canonical({ id, command, expected_exit }))
```

Declaration order of commands is non-semantic for identity. Content is semantic.

## 5. Contract identity (per task)

```
contract_id = SHA256(canonical({
    validator,
    repository,          // repo_identity
    head,
    source,              // source_identity
    task_id,
    requirements,        // sorted
    specifications,      // sorted "path|anchor"
    targets,             // sorted
    prohibited,          // sorted
    tools,               // sorted (id, declared_version)
    allowed_tools,       // sorted
    commands,            // sorted command_id set
    criteria,            // sorted (id, validator)
    expected_outputs,    // sorted (path, sha256)
    dependency_state,    // sorted PASS-satisfied dependency refs
    policy               // authorization-affecting fields
}))
```

Replay across tasks, repos, commits, or contract revisions is impossible if this binding is honored.

## 6. Criterion attestation (strict mode)

When any criterion declares a validator, each criterion gets a derived attestation:

```
criterion_evidence_id = SHA256(canonical({
    contract_id, task_id, criterion_id, validator, command_id, result: "PASS"
}))
```

Attested iff a trusted PASS record exists for that `command_id` under the current `contract_id`. No new storage; no inference of undeclared edges.

## 7. Closure

`closure_gaps(task, contract_id, task_evidence, ctx)` returns the missing provenance edges. Empty means closed.

Minimum edges:

```
requirement → specification → task → validation → acceptance → evidence
```

Gaps include: missing requirement, missing specification, missing validation, missing acceptance, missing per-command or per-criterion PASS bound to current `contract_id`, validator identity mismatch.

## 8. Parent contracts

`provenance.parent_contracts` is informational lineage. A parent id does not authorize the child. Child evidence cannot satisfy a parent `contract_id`.

## 9. Coverage identity (derived)

A hash over the requirement-coverage graph detects change. It is never an input to task PASS.
