"""Explicit parent lineage, emit --check, mute pipeline (ADR-0018)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import PLAN_SCHEMA, emit_contract_file
from git_up.cli import main
from git_up.identity import source_identity
from git_up.contract import load_contract
from tests.support import init_repo, write
from tools.pipeline import run_pipeline


_PLAN = {
    "schema_version": PLAN_SCHEMA,
    "tools": [{"id": "python3", "available": True, "binary": "python3"}],
    "tasks": [{
        "id": "T1",
        "title": "lineage",
        "authority": {"path": "docs/SPEC.md", "requirement_id": "R1"},
        "requirement_refs": ["R1"],
        "specification": {"path": "docs/SPEC.md"},
        "targets": ["src/out.txt"],
        "required_tools": ["python3"],
        "allowed_tools": ["python3"],
        "commands": [{"id": "v1", "command": "python3 -c pass",
                      "expected_exit": 0}],
        "criteria": [{"id": "c1", "statement": "ok", "validator": "v1"}],
    }],
    "requirements": [{"id": "R1", "specification": "docs/SPEC.md",
                      "coverage": [{"task_id": "T1", "obligations": ["x"]}]}],
}


class LineageTests(unittest.TestCase):
    def test_parent_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            write(repo / "docs" / "SPEC.md", "R1\n")
            write(repo / "src" / "out.txt", "x\n")
            plan = repo / "plan.json"
            plan.write_text(json.dumps(_PLAN), encoding="utf-8")
            first = repo / "c1.json"
            emit_contract_file(plan, first)
            second = repo / "c2.json"
            emit_contract_file(plan, second, parent_path=first)
            child = load_contract(second)
            parent_id = source_identity(load_contract(first))
            self.assertEqual(child.provenance.get("parent_contracts"), [parent_id])
            bare = emit_contract_file(plan)
            self.assertEqual(bare["provenance"]["parent_contracts"], [])

    def test_emit_check_catches_escape(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            write(repo / "docs" / "SPEC.md", "R1\n")
            bad = json.loads(json.dumps(_PLAN))
            bad["tasks"][0]["targets"] = ["../outside.txt"]
            plan = repo / "plan.json"
            plan.write_text(json.dumps(bad), encoding="utf-8")
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main([
                    "contract", "emit", "--from", str(plan),
                    "--repo-root", str(repo), "--check",
                ])
            finally:
                sys.stdout = old
            self.assertEqual(code, 2)
            data = json.loads(buf.getvalue())
            self.assertTrue(data.get("confinement_errors"))

    def test_pipeline_is_mute(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            write(repo / "docs" / "SPEC.md", "R1\n")
            write(repo / "src" / "out.txt", "x\n")
            plan = repo / "plan.json"
            plan.write_text(json.dumps(_PLAN), encoding="utf-8")
            out = repo / "c.json"
            payload = run_pipeline(
                plan=str(plan), repo_root=str(repo), out=str(out),
            )
            self.assertEqual(payload["result"], "PASS", payload)
            self.assertEqual(payload["ready_queue"], ["T1"])
            self.assertFalse((repo / ".git-up" / "repo.identity").exists())
            self.assertFalse((repo / ".git-up" / "evidence.jsonl").exists())
            self.assertFalse((repo / ".git-up" / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
