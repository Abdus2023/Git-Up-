# Git-Up! self-plan

This note is not the contract. The fence is.

```git-up-plan
{
  "schema_version": "git-up.plan.v0.1",
  "policy": { "timeout_seconds": 120 },
  "tools": [
    { "id": "python3", "available": true, "binary": "python3", "version": "3" }
  ],
  "requirements": [
    {
      "id": "R-SPEC18",
      "specification": "docs/specification/18-test-strategy.md",
      "coverage": [
        { "task_id": "T-SPEC18", "obligations": ["discharge-invariant-ids"] }
      ]
    }
  ],
  "tasks": [
    {
      "id": "T-SPEC18",
      "title": "Discharge Specification 18 invariant tests",
      "description": "The host implementation satisfies every MUST ID in spec 18.",
      "priority": 10,
      "order": 0,
      "authority": {
        "path": "docs/specification/18-test-strategy.md",
        "anchor": "3",
        "requirement_id": "R-SPEC18"
      },
      "requirement_refs": ["R-SPEC18"],
      "specification": {
        "path": "docs/specification/18-test-strategy.md",
        "anchor": "3"
      },
      "targets": ["git_up", "tests", "git-up"],
      "required_tools": ["python3"],
      "allowed_tools": ["python3"],
      "commands": [
        {
          "id": "v-unittest",
          "command": "python3 -m unittest discover -s tests -p test_*.py -q",
          "expected_exit": 0,
          "purpose": "spec 18 invariant suite"
        }
      ],
      "criteria": [
        {
          "id": "c-suite-green",
          "statement": "python3 -m unittest discover -s tests exits 0",
          "validator": "v-unittest"
        }
      ]
    }
  ]
}
```
