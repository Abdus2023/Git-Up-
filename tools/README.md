# tools/

Git-Up! tooling. **Not** the controller. Tools do not authorize PASS.

| Tool | Role |
|---|---|
| `pipeline.py` | Dry-run emit → validate → classify (ADR-0018) |

```bash
python3 tools/pipeline.py --plan examples/plans/example.json --out /tmp/c.json
python3 tools/pipeline.py --contract git-up.contract.json
```

Prior-art Python from Red/Cognition remains at
[`../reference/red-cognition-controller/`](../reference/red-cognition-controller/README.md).
