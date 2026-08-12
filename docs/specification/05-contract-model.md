# 05 — Contract Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

The **implementation contract** is the central object of Git-Up!. Core begins here.

## 1. Role

The contract answers: **what is Git-Up! authorized to execute, against which repository state, under which validators, to what acceptance?**

It is not a plan diary. It is not a report. It is not evidence.

## 2. Conceptual schema

Field names are normative for v0.1. Serialization encoding is not frozen beyond: UTF-8, canonical JSON for identity (sorted keys, compact separators, no insignificant whitespace).

```
ImplementationContract {
    schema_version: "git-up.contract.v0.1"

    contract_id: hex(sha256)          // computed; never user-supplied as authority

    repository {
        identity                      // see spec 06
        revision                      // HEAD the contract was bound to
        workspace                     // worktree path identity
        dirty_state                   // declared expectation, if any
    }

    authority {
        sources[]                     // { path, anchor, requirement_id? }
        policy                        // fail_closed = true (required)
    }

    task {
        id
        title
        description
        scope
        implementation_targets[]
        prohibited_scope[]
        priority                      // lower = sooner
        order                         // stable tie-break
    }

    requirements { refs[] }
    specifications { refs[] }         // { path, anchor }

    dependencies[] { ref, required_state }   // required_state other than PASS is not auto-satisfiable

    acceptance { criteria[] }         // { id, statement, validator? }

    execution {
        allowed_tools[]               // bare executable names
        environment                   // declared constraints only
    }

    validation {
        commands[]                    // { id, argv-or-string, expected_exit, purpose }
        expected_results[]
        expected_outputs[]            // { path, sha256 }
    }

    provenance {
        parent_contracts[]            // prior contract_ids, if any
        source_identity               // hash of the producer artifact, if any
        producer                      // adapter name; informational
    }

    policy {
        determinism                   // required
        timeout_seconds
        concurrency                   // exclusive (v0.1: always exclusive)
        failure_mode                  // fail_closed
    }
}
```

A contract MAY contain many tasks. Identity MAY be computed per-task (a *task contract*) from the subset of fields that authorize that task; the per-task `contract_id` is what evidence binds to. See spec 12.

## 3. Required for authorization

A task-shaped contract is **insufficient** (never `READY`) unless all hold:

- at least one authority source
- at least one requirement ref
- at least one specification ref
- at least one validation command
- at least one acceptance criterion
- implementation targets confined to the repository (may be empty only if the task is purely observational and declares that fact)
- `allowed_tools` non-empty if any command will run
- `policy.failure_mode = fail_closed`
- `policy.concurrency = exclusive` (v0.1)

Missing fields are blockers, not defaults.

## 4. Identity

```
contract_id = SHA256(canonical(authoritative_payload))
```

`canonical` = JSON with sorted object keys, lists that are semantically unordered sorted by their canonical form, compact separators, UTF-8.

**Semantic (identity-affecting):** validator identity, repository identity, HEAD, source-document identity, task id, requirement refs, specification refs, targets, prohibited scope, tool ids + declared versions, allowed tools, command content (`id`, command, `expected_exit`), criteria (`id`, validator), expected outputs, satisfied PASS-dependency set, policy fields that affect authorization.

**Non-semantic (canonicalized away):** declaration order of independent lists, documentation-only prose that the schema marks as non-authoritative.

User-supplied `contract_id` values are ignored for authorization. The controller computes identity.

## 5. Who may emit a contract

Any adapter or human. Git-Up! validates; it does not author the intellectual content. An invalid contract is refused, not repaired.

## 6. Emission rule

The controller emits an **execution contract** (a projection) only for a task whose classification is `READY`. Emitting a contract for a `BLOCKED` task is a specification defect.

The execution contract MUST include:

- `contract_id`
- task id, title, scope
- provenance context (repository identity, HEAD, source identity, validator)
- files allowed to change / prohibited
- authority and requirement refs
- dependencies with satisfaction bits
- required and allowed tools
- validation commands and acceptance criteria
- required evidence field list

## 7. Contract vs. checkpoint vs. report

| Artifact | May authorize PASS? |
|---|---|
| Current computed `contract_id` + evidence predicate | Yes (with the rest of spec 11/12) |
| User-edited contract file after identity changed | No — new identity; old evidence will not bind |
| Checkpoint | No |
| JSON report | No |

## 8. Versioning

`schema_version` is required. Unknown versions fail closed. v0.1 implementations MUST reject any other version rather than coerce.
