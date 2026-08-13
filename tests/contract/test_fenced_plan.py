"""Fenced plans only — prose is never a source (ADR-0016)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import PLAN_SCHEMA, emit_contract, parse_plan_text
from git_up.cli import main
from git_up.contract import load_contract
from git_up.errors import ContractError
from tests.support import commit_all, init_repo, make_controller, write


_PLAN = {
    "schema_version": PLAN_SCHEMA,
    "tools": [{"id": "python3", "available": True, "binary": "python3"}],
    "requirements": [{
        "id": "R1",
        "specification": "docs/SPEC.md",
        "coverage": [{"task_id": "T1", "obligations": ["all"]}],
    }],
    "tasks": [{
        "id": "T1",
        "title": "fenced",
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


class FencedPlanTests(unittest.TestCase):
    def test_prose_without_fence_fails(self):
        with self.assertRaises(ContractError):
            parse_plan_text("# Design\n\n- do the thing\n", source="note.md")

    def test_multiple_fences_fail(self):
        body = json.dumps(_PLAN)
        text = f"```git-up-plan\n{body}\n```\n\n```git-up-plan\n{body}\n```\n"
        with self.assertRaises(ContractError):
            parse_plan_text(text, source="two.md")

    def test_single_fence_emits_ready(self):
        text = "# note\n\n```git-up-plan\n" + json.dumps(_PLAN) + "\n```\n"
        plan = parse_plan_text(text, source="one.md")
        doc = emit_contract(plan)
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            write(repo / "docs" / "SPEC.md", "R1\n")
            write(repo / "src" / "out.txt", "x\n")
            commit_all(repo, "seed")
            path = repo / "c.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            res = make_controller(repo, contract_path=path).run(dry_run=True)
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertEqual(states.get("T1"), "READY")

    def test_cli_emit_from_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            md = Path(td) / "note.md"
            md.write_text(
                "ignore this\n\n```git-up-plan\n" + json.dumps(_PLAN) + "\n```\n",
                encoding="utf-8",
            )
            out = Path(td) / "c.json"
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main([
                    "contract", "emit", "--from", str(md), "--out", str(out),
                ])
            finally:
                sys.stdout = old
            self.assertEqual(code, 0, buf.getvalue())
            load_contract(out)

    def test_cli_emit_stdin(self):
        oldin, oldout = sys.stdin, sys.stdout
        sys.stdin = StringIO(json.dumps(_PLAN))
        sys.stdout = StringIO()
        try:
            code = main(["contract", "emit", "--from", "-"])
            payload = json.loads(sys.stdout.getvalue())
        finally:
            sys.stdin, sys.stdout = oldin, oldout
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload.get("task_count"), 1)
        self.assertEqual(payload["contract"]["tasks"][0]["id"], "T1")


if __name__ == "__main__":
    unittest.main()
