# 07 — Task Model

**Status:** FROZEN  
**Freeze:** Git-Up! Specification v0.1

## 1. Task

A **task** is the smallest unit the controller classifies and (optionally) executes validators for.

```
Task {
    id, title, description
    priority, order
    scope
    source_authority[]
    requirement_refs[]
    specification_refs[]
    implementation_targets[]
    prohibited_scope[]
    dependency_refs[]          // { ref, required_state }
    required_tools[]
    allowed_tools[]
    validation_commands[]      // { id, command, expected_exit, purpose }
    acceptance_criteria[]      // { id, statement, validator? }
    expected_outputs[]         // { path, sha256 }
    declared_blockers[]        // { category, satisfied, evidence, detail }
    spec_conflicts[]
    spec_gaps[]
    rejected: bool
    deferred: bool
}
```

The controller implements **no product feature**. Changing implementation targets is the agent's job, inside the emitted execution contract. Git-Up! v0.1's execute path runs **declared validation commands**, not arbitrary implementation edits.

## 2. Definition gate

A task lacking any of the following is `BLOCKED` / `INSUFFICIENT_TASK_DEFINITION`:

- `source_authority`
- `requirement_refs`
- `specification_refs`
- `validation_commands`
- `acceptance_criteria`

No field is inferred. Empty means insufficient.

## 3. Coverage modes

### 3.1 Legacy presence mode

If **no** criterion names a `validator`, the task uses *presence-based* acceptance: every validation command must eventually have PASS evidence. Git-Up! MUST NOT invent criterion↔command edges.

### 3.2 Strict coverage mode

If **any** criterion names a `validator`, the task is strict:

- every criterion MUST name a declared command;
- every command MUST cover ≥ 1 criterion;
- closure is per-criterion attestation.

Gaps are `INSUFFICIENT_TASK_DEFINITION`. Missing semantics are never guessed.

## 4. Dependencies

A dependency with `required_state = PASS` is satisfied only if the referenced task is in the **authoritative PASS set** (spec 09, 11).

Any other `required_state` is **not auto-satisfiable** in v0.1 and BLOCKS.

Cycles in the dependency graph never yield `READY`. They are reported as a blocking chain.

The authoritative PASS set is a **fixpoint**: a task joins it only if all of its PASS-required dependencies are already in it, and the rest of the authorization predicate holds.

## 5. Tools

A required tool is available only if:

1. it is declared in the contract's tool registry,
2. it is claimed available,
3. its executable is actually present on `PATH` (ground truth).

A claim without a binary is `TOOLCHAIN` blocked.

`allowed_tools` is the execution allowlist. Empty allowlist + execute = fail closed.

## 6. Declared blockers

Humans/adapters MAY attach evidence-grounded blockers (`ARCHITECTURE`, `PROVISIONING`, `AUTHORIZATION`, …). The engine NEVER auto-satisfies a declared blocker. Only an explicit `satisfied = true` in the contract does.

## 7. Specification conflicts and gaps

Non-empty `spec_conflicts` → `SPECIFICATION_CONFLICT`.  
Non-empty `spec_gaps` → `INCOMPLETE_SPECIFICATION`.  
These outrank dependency and toolchain in primary-blocker precedence (spec 08).

## 8. Classification (component E)

Evaluation order for the **primary** blocker:

1. `rejected` → `REJECTED`
2. spec conflict / gap
3. dependency not PASS
4. tool unavailable
5. authority missing / insufficient definition / coverage gaps
6. unsatisfied declared blocker
7. otherwise → `READY`

Every applicable reason is collected. A `BLOCKED` task is never `READY` and never auto-executed.

The engine **never** promotes a task to `PASS`. Only the authorization predicate does.

## 9. Ready queue

Among `READY` tasks, order by `(priority asc, order asc, id asc)`. Deterministic. The execute path of v0.1 considers the head of this queue only.
