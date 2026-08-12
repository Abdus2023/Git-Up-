#!/usr/bin/env python3
"""Thin launcher for the Implementation Execution Controller.

Usage:
    python3 tools/impl-controller.py --dry-run
    python3 tools/impl-controller.py --self-test
    python3 tools/impl-controller.py --execute --allow-tool python3

This wrapper keeps ``tools/`` a non-package directory (no __init__.py added)
by inserting its own directory onto sys.path and importing the package.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from impl_controller.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
