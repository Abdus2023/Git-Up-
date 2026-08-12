#!/usr/bin/env python3
"""Full 5-stage implementation pipeline orchestrator.

Stage 1 — Extraction:      scan RFCs, specs, wiki, knowledge-base → structured inventory
Stage 2 — Reconstruction:  inspect repository source/tests/runtime → component classification
Stage 3 — Traceability:    build bidirectional requirement↔spec↔task↔evidence graph
Stage 4 — Planning:        validate the implementation plan against extracted knowledge
Stage 5 — Control:         run the Stage-5 controller (existing)

Output: docs/implementation/full-pipeline-status.json

Usage:
  python3 tools/run-full-pipeline.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from impl_controller.controller import Controller


def _repo_root() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return str(Path.cwd())


def _head(root: str) -> str:
    try:
        out = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


# ==========================================================================
# STAGE 1 — EXTRACTION
# ==========================================================================
def stage1_extract(root: Path) -> dict:
    """Extract structured knowledge inventory from authoritative sources."""
    inventory = {"rfcs": [], "specs": [], "wiki_pages": [], "extraction_reports": [],
                 "totals": {}}

    # --- RFCs ---
    for f in sorted((root / "rfcs").glob("RFC-*.md")):
        text = f.read_text(errors="replace")
        rid = re.search(r"RFC-(\d{4})", f.name)
        status = re.search(r"\*\*Status:\*\*\s*(.+?)\s*$", text, re.M)
        version = re.search(r"\*\*Version:\*\*\s*(.+?)\s*$", text, re.M)
        title_m = re.search(r"\*\*RFC-\d{4}\s+—\s+(.+?)\*\*", text)
        parent = re.search(r"\*\*Parent:\*\*\s*(.+?)\s*$", text, re.M)
        inventory["rfcs"].append({
            "id": f"RFC-{rid.group(1)}" if rid else f.stem,
            "file": f.name,
            "title": title_m.group(1).strip() if title_m else "",
            "status": (status.group(1).strip() if status else "UNKNOWN"),
            "version": (version.group(1).strip() if version else ""),
            "parent": (parent.group(1).strip()[:60] if parent else ""),
        })

    # --- Specs ---
    spec_dir = root / "docs" / "specifications" / "red-deep-technical-spec"
    for f in sorted(spec_dir.glob("*.md")):
        inventory["specs"].append({"file": f.name, "path": str(f.relative_to(root))})

    # --- Wiki ---
    for f in sorted((root / "knowledge-base" / "wiki").glob("*.md")):
        inventory["wiki_pages"].append({"file": f.name})

    # --- Extraction reports ---
    for f in sorted((root / "knowledge-base" / "reports").glob("message-*-report.md")):
        inventory["extraction_reports"].append({"file": f.name})

    inventory["totals"] = {
        "rfcs": len(inventory["rfcs"]),
        "unique_rfc_ids": len({r["id"] for r in inventory["rfcs"]}),
        "ratified": sum(1 for r in inventory["rfcs"] if "Ratified" in r["status"]),
        "specs": len(inventory["specs"]),
        "wiki_pages": len(inventory["wiki_pages"]),
        "extraction_reports": len(inventory["extraction_reports"]),
    }
    return inventory


# ==========================================================================
# STAGE 2 — RECONSTRUCTION
# ==========================================================================
def stage2_reconstruct(root: Path) -> dict:
    """Classify repository components by implementation status."""
    components = []

    def classify(name, paths, expected_state):
        exists = any((root / p).exists() for p in paths)
        components.append({
            "name": name,
            "paths": paths,
            "exists": exists,
            "classification": expected_state if exists else "ABSENT",
        })

    classify("Red lexer/compiler", ["lexer.r", "compiler.r", "red.r"], "SCAFFOLDED")
    classify("Red runtime", ["runtime/"], "SCAFFOLDED")
    classify("Red tests", ["tests/source/compiler/lexer-test.r"], "SCAFFOLDED")
    classify("libRed", ["libRed/"], "SCAFFOLDED")
    classify("Cognition runtime", ["cognition/"], "ABSENT")
    classify("RFC-0075 traceability", ["docs/traceability/rfc-0075/"], "SCAFFOLDED")
    classify("Implementation plan", ["docs/implementation/implementation-plan.json"], "SCAFFOLDED")
    classify("Stage-5 controller", ["tools/impl_controller/"], "IMPLEMENTED")

    return {"components": components,
            "cognition_implemented": any(c["name"] == "Cognition runtime"
                                         and c["classification"] not in ("ABSENT",)
                                         for c in components)}


# ==========================================================================
# STAGE 3 — TRACEABILITY
# ==========================================================================
def stage3_trace(root: Path, inventory: dict, reconstruction: dict,
                 plan: dict) -> dict:
    """Build bidirectional traceability graph."""
    edges = []

    # requirement → specification (from task spec_refs)
    for task in plan.get("tasks", []):
        tid = task["task_id"]
        for req in task.get("requirement_refs", []):
            edges.append({"from": req, "to": tid, "kind": "requirement→task"})
        for spec in task.get("specification_refs", []):
            edges.append({"from": tid, "to": spec.get("doc", ""),
                          "kind": "task→specification"})
        for auth in task.get("source_authority", []):
            edges.append({"from": tid, "to": auth.get("doc", ""),
                          "kind": "task→authority"})

    return {
        "edges": edges,
        "total_edges": len(edges),
        "requirement_to_task": sum(1 for e in edges if e["kind"] == "requirement→task"),
        "task_to_specification": sum(1 for e in edges if e["kind"] == "task→specification"),
        "task_to_authority": sum(1 for e in edges if e["kind"] == "task→authority"),
    }


# ==========================================================================
# STAGE 4 — PLANNING VALIDATION
# ==========================================================================
def stage4_plan(root: Path, inventory: dict, reconstruction: dict) -> dict:
    """Validate the implementation plan against extracted knowledge."""
    plan_path = root / "docs" / "implementation" / "implementation-plan.json"
    if not plan_path.is_file():
        return {"valid": False, "error": "implementation-plan.json not found"}

    plan = json.loads(plan_path.read_text())
    issues = []

    known_rfc_ids = {r["id"] for r in inventory["rfcs"]}
    for task in plan.get("tasks", []):
        # validate authority docs exist
        for ref in task.get("source_authority", []):
            doc = ref.get("doc", "")
            if doc and not (root / doc).exists():
                issues.append(f"task {task['task_id']}: authority doc '{doc}' not found")
        # validate specification refs exist
        for ref in task.get("specification_refs", []):
            doc = ref.get("doc", "")
            if doc and not (root / doc).exists():
                issues.append(f"task {task['task_id']}: spec doc '{doc}' not found")

    return {
        "valid": len(issues) == 0,
        "task_count": len(plan.get("tasks", [])),
        "issues": issues,
        "plan_source": str(plan_path.relative_to(root)),
    }


# ==========================================================================
# STAGE 5 — CONTROL
# ==========================================================================
def stage5_control(root: Path) -> dict:
    """Run the Stage-5 controller (dry-run, read-only)."""
    manifest = str(root / "docs" / "implementation" / "implementation-plan.json")
    state = str(root / ".impl_controller" / "pipeline-state.json")
    evidence = str(root / ".impl_controller" / "pipeline-evidence.jsonl")
    try:
        ctrl = Controller(manifest, str(root), state, evidence)
        res = ctrl.run(dry_run=True)
        return {
            "frontier": res.frontier,
            "graph": res.report["graph"],
            "classifications": [c for c in res.report["classifications"]],
            "evidence_integrity": res.report.get("evidence_integrity", {}),
            "result": res.result,
        }
    except Exception as e:
        return {"result": "FAIL", "error": str(e)}


# ==========================================================================
# ORCHESTRATOR
# ==========================================================================
def main() -> int:
    root = Path(_repo_root())
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print("Stage 1 — Extraction...", file=sys.stderr)
    s1 = stage1_extract(root)

    print("Stage 2 — Reconstruction...", file=sys.stderr)
    s2 = stage2_reconstruct(root)

    print("Stage 3 — Traceability...", file=sys.stderr)
    plan_path = root / "docs" / "implementation" / "implementation-plan.json"
    plan = json.loads(plan_path.read_text()) if plan_path.is_file() else {"tasks": []}
    s3 = stage3_trace(root, s1, s2, plan)

    print("Stage 4 — Planning validation...", file=sys.stderr)
    s4 = stage4_plan(root, s1, s2)

    print("Stage 5 — Control...", file=sys.stderr)
    s5 = stage5_control(root)

    status = {
        "pipeline_version": "5.0",
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository_head": _head(str(root)),
        "stage1_extraction": s1,
        "stage2_reconstruction": s2,
        "stage3_traceability": s3,
        "stage4_planning": s4,
        "stage5_control": s5,
        "epistemic_states": {
            "specified": s1["totals"]["rfcs"],
            "implemented": sum(1 for c in s2["components"]
                               if c["classification"] == "IMPLEMENTED"),
            "executed": s5.get("graph", {}).get("PASS", 0),
            "tested": 0,
            "validated": 0,
            "evidenced": 0,
            "formally_verified": 0,
        },
    }

    out_path = root / "docs" / "implementation" / "full-pipeline-status.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    # Summary
    print(json.dumps({
        "pipeline_version": "5.0",
        "stage1": {"rfcs": s1["totals"]["rfcs"], "ratified": s1["totals"]["ratified"],
                    "specs": s1["totals"]["specs"]},
        "stage2": {"components": len(s2["components"]),
                    "cognition": s2["cognition_implemented"]},
        "stage3": {"edges": s3["total_edges"]},
        "stage4": {"valid": s4["valid"], "tasks": s4["task_count"]},
        "stage5": {"frontier": s5.get("frontier"), "graph": s5.get("graph"),
                    "result": s5.get("result")},
        "status_out": str(out_path.relative_to(root)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
