"""Plan source_identity is bound and wrapping prose is not (ADR-0017)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import PLAN_SCHEMA, emit_contract, parse_plan_text
from git_up.canonical import sha256_json
from git_up.contract import load_contract
from tests.support import init_repo, write
import tempfile


_PLAN = {
    "schema_version": PLAN_SCHEMA,
    "tools": [{"id": "python3", "available": True, "binary": "python3"}],
    "tasks": [{"id": "T1", "title": "same"}],
}


class PlanIdentityTests(unittest.TestCase):
    def test_json_and_fence_share_plan_hash(self):
        a = emit_contract(_PLAN)
        fenced = parse_plan_text(
            "# chatter\n\n```git-up-plan\n" + json.dumps(_PLAN) + "\n```\n",
            source="note.md",
        )
        b = emit_contract(fenced)
        self.assertEqual(a["provenance"]["source_identity"],
                         b["provenance"]["source_identity"])
        self.assertEqual(a["provenance"]["source_identity"], sha256_json(_PLAN))

    def test_task_edit_changes_hash(self):
        other = json.loads(json.dumps(_PLAN))
        other["tasks"][0]["title"] = "different"
        self.assertNotEqual(
            emit_contract(_PLAN)["provenance"]["source_identity"],
            emit_contract(other)["provenance"]["source_identity"],
        )

    def test_load_round_trip_keeps_provenance(self):
        doc = emit_contract(_PLAN)
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            path = repo / "c.json"
            write(path, json.dumps(doc))
            loaded = load_contract(path)
            self.assertEqual(loaded.provenance.get("producer"),
                             "git-up.adapter.plan")
            self.assertEqual(loaded.provenance.get("source_identity"),
                             doc["provenance"]["source_identity"])


if __name__ == "__main__":
    unittest.main()
