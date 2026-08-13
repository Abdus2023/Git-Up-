"""Unique IDs, dangling refs, and fail-closed directory emit."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import PLAN_SCHEMA, emit_contract_file
from git_up.contract import load_contract
from git_up.errors import ContractError
from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree, write,
)


class ReferentialIntegrityTests(unittest.TestCase):
    def test_duplicate_command_id_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["tasks"][0]["validation_commands"].append(
                dict(doc["tasks"][0]["validation_commands"][0])
            )
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(p)
            self.assertIn("duplicate", str(ctx.exception))

    def test_duplicate_tool_id_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["tools"].append(dict(doc["tools"][0]))
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(p)
            self.assertIn("duplicate tool", str(ctx.exception))

    def test_coverage_unknown_task_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["requirements"][0]["coverage"].append(
                {"task_id": "T-GHOST", "obligations": ["x"]}
            )
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(p)
            self.assertIn("T-GHOST", str(ctx.exception))

    def test_dangling_requirement_ref_is_traceability(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(requirement_refs=["R1", "R-GHOST"])
            seed_worktree(repo, contract_doc([task]))
            res = make_controller(repo).run(dry_run=True)
            by = {c["task_id"]: c for c in res.report["classifications"]}
            self.assertEqual(by["T1"]["effective_state"], "BLOCKED")
            self.assertEqual(by["T1"]["blocker_class"], "TRACEABILITY")
            self.assertTrue(any("R-GHOST" in d for d in by["T1"]["detail"]))

    def test_emit_from_directory_one_plan(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "plans"
            d.mkdir()
            write(d / "notes.md", "prose only, no fence\n")
            plan = {
                "schema_version": PLAN_SCHEMA,
                "tasks": [{"id": "T1", "title": "one"}],
            }
            (d / "only.json").write_text(json.dumps(plan), encoding="utf-8")
            out = Path(td) / "c.json"
            doc = emit_contract_file(d, out)
            self.assertEqual(doc["tasks"][0]["id"], "T1")
            load_contract(out)

    def test_emit_from_directory_multiple_plans_refused(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "plans"
            d.mkdir()
            plan = {
                "schema_version": PLAN_SCHEMA,
                "tasks": [{"id": "T1"}],
            }
            (d / "a.json").write_text(json.dumps(plan), encoding="utf-8")
            (d / "b.json").write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                emit_contract_file(d)
            self.assertIn("multiple plans", str(ctx.exception))

    def test_emit_from_empty_directory_refused(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "plans"
            d.mkdir()
            write(d / "readme.txt", "not a plan\n")
            with self.assertRaises(ContractError) as ctx:
                emit_contract_file(d)
            self.assertIn("no git-up.plan", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
