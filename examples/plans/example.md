# Example design note

This prose is **not** a plan. Git-Up! must ignore it.

If an adapter inferred tasks from these bullets it would be a planner:

- implement the feature
- add tests
- ship it

The only declared plan is the fence below.

```git-up-plan
{
  "schema_version": "git-up.plan.v0.1",
  "policy": { "timeout_seconds": 60 },
  "tools": [
    { "id": "python3", "available": true, "binary": "python3", "version": "3" }
  ],
  "requirements": [
    {
      "id": "R1",
      "specification": "docs/ARCHITECTURE.md",
      "coverage": [{ "task_id": "T1", "obligations": ["smoke"] }]
    }
  ],
  "tasks": [
    {
      "id": "T1",
      "title": "Example via fenced plan",
      "description": "Declared inside a design note; not inferred from prose.",
      "priority": 10,
      "authority": {
        "path": "docs/ARCHITECTURE.md",
        "anchor": "R1",
        "requirement_id": "R1"
      },
      "requirement_refs": ["R1"],
      "specification": { "path": "docs/ARCHITECTURE.md", "anchor": "R1" },
      "targets": ["README.md"],
      "required_tools": ["python3"],
      "allowed_tools": ["python3"],
      "commands": [
        {
          "id": "v1",
          "command": "python3 -c pass",
          "expected_exit": 0,
          "purpose": "smoke"
        }
      ],
      "criteria": [
        {
          "id": "c1",
          "statement": "the controller can invoke a declared validator",
          "validator": "v1"
        }
      ]
    }
  ]
}
```
