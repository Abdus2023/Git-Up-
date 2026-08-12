# Prior art — Red/Cognition controller (not product code)

This tree is a snapshot of `tools/` from
[`Abdus2023/Red-Cognition-` @ `arena/019ff593-red-cognition`](https://github.com/Abdus2023/Red-Cognition-/tree/arena/019ff593-red-cognition/tools).

It exists so Git-Up! can **audit and extract principles**. It is **not** Git-Up!.

See:

- [ADR-0001](../../docs/decisions/ADR-0001-independence.md) — independence
- [ADR-0004](../../docs/decisions/ADR-0004-lock-first.md) — lock-first (this code acquires the lease too late)
- [ADR-0009](../../docs/decisions/ADR-0009-prior-art-reference.md) — why this directory exists

Do not import these modules from a future `git-up` binary. Do not treat their tests as Git-Up! evidence.
