# SPDX-License-Identifier: Apache-2.0
"""CLI entry point for pack validation.

Usage::

    convsim-validate-pack <path-to-pack-directory>

Exit codes:
  0 — valid (no errors; warnings are informational)
  1 — invalid (one or more errors block import or contribution)
"""
import sys
from pathlib import Path

from convsim_core.packs.models import ValidationSeverity
from convsim_core.packs.validator import validate_pack_dir


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: convsim-validate-pack <pack-directory>", file=sys.stderr)
        sys.exit(1)

    pack_dir = Path(sys.argv[1])
    if not pack_dir.is_dir():
        print(f"Error: '{pack_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    result = validate_pack_dir(pack_dir)

    print(f"Validating pack at: {pack_dir.resolve()}\n")

    if result.errors:
        print(f"ERRORS ({len(result.errors)}):")
        for issue in result.errors:
            print(f"  [{issue.rule_id}] {issue.file} {issue.pointer}: {issue.message}")
            print(f"    Fix: {issue.suggested_fix}")
        print()

    if result.warnings:
        print(f"WARNINGS ({len(result.warnings)}):")
        for issue in result.warnings:
            print(f"  [{issue.rule_id}] {issue.file} {issue.pointer}: {issue.message}")
            print(f"    Fix: {issue.suggested_fix}")
        print()

    if result.valid:
        warning_note = f", {len(result.warnings)} warning(s)" if result.warnings else ""
        print(f"Result: VALID{warning_note}")
        if result.warnings:
            print("  Warnings must be resolved before contributing to the official pack collection.")
        sys.exit(0)
    else:
        print(f"Result: INVALID ({len(result.errors)} error(s), {len(result.warnings)} warning(s))")
        sys.exit(1)
