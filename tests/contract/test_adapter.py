"""Adapter emits contracts without inventing definition (ADR-0015)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import PLAN_SCHEMA, emit_contract, emit_contract_file
from git_up.cli import main
from git_up.contract import load_contract
from git_up.errors import ContractError
from tests.support import commit_all, init_repo, make_controller, write


def _complete_plan():
    return {
        "schema_version": PLAN_SCHEMA,
        "tools": [{"id": "python3", "available": True, "binary": "python3"}],
        "requirements": [{
            "id": "R1",
            "specification": "docs/SPEC.md",
            "coverage": [{"task_id": "T1", "obligations": ["all"]}],
        }],
        "tasks": [{
            "id": "T1",
            "title": "via adapter",
            "authority": {"path": "docs/SPEC.md", "anchor": "R1",
                          "requirement_id": "R1"},
            "requirement_refs": ["R1"],
            "specification": {"path": "docs/SPEC.md", "anchor": "R1"},
            "targets": ["src/out.txt"],
            "required_tools": ["python3"],
            "allowed_tools": ["python3"],
            "commands": [{"id": "v1", "command": "python3 -c pass",
                          "expected_exit": 0}],
            "criteria": [{"id": "c1", "statement": "ok", "validator": "v1"}],
        }],
    }


class AdapterTests(unittest.TestCase):
    def test_unknown_plan_schema_rejected(self):
        with self.assertRaises(ContractError):
            emit_contract({"schema_version": "nope", "tasks": [{"id": "T1"}]})

    def test_complete_plan_classifies_ready(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            write(repo / "docs" / "SPEC.md", "R1\n")
            write(repo / "src" / "out.txt", "x\n")
            plan = repo / "plan.json"
            plan.write_text(json.dumps(_complete_plan()), encoding="utf-8")
            commit_all(repo, "seed")
            out = repo / "emitted.json"
            emit_contract_file(plan, out)
            c = load_contract(out)
            self.assertEqual(c.schema_version, "git-up.contract.v0.1")
            res = make_controller(repo, contract_path=out).run(dry_run=True)
            states = {x["task_id"]: x["effective_state"]
                      for x in res.report["classifications"]}
            self.assertEqual(states.get("T1"), "READY")

    def test_incomplete_plan_does_not_guess_ready(self):
        plan = {
            "schema_version": PLAN_SCHEMA,
            "tasks": [{"id": "T1", "title": "empty"}],
        }
        doc = emit_contract(plan)
        self.assertEqual(doc["tasks"][0]["validation_commands"], [])
        self.assertEqual(doc["tasks"][0]["acceptance_criteria"], [])
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            write(repo / "docs" / "SPEC.md", "x\n")
            path = repo / "emitted.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            res = make_controller(repo, contract_path=path).run(dry_run=True)
            states = {x["task_id"]: x["effective_state"]
                      for x in res.report["classifications"]}
            self.assertEqual(states.get("T1"), "BLOCKED")

    def test_cli_emit(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            plan = Path(td) / "plan.json"
            plan.write_text(json.dumps(_complete_plan()), encoding="utf-8")
            out = Path(td) / "c.json"
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main([
                    "contract", "emit", "--from", str(plan), "--out", str(out),
                ])
            finally:
                sys.stdout = old
            self.assertEqual(code, 0, buf.getvalue())
            self.assertTrue(out.is_file())
            load_contract(out)


if __name__ == "__main__":
    unittest.main()
