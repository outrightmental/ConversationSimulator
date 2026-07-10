#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate model-registry/registry.yaml against the schema and policy rules.

Usage:
    python scripts/validate-registry.py [--url-check]

Flags:
    --url-check   Perform an HTTP HEAD request against every download URL to
                  verify reachability.  Omit for fast local validation; include
                  in nightly CI.  HuggingFace CDN redirects are followed.

Exit codes:
    0  All checks passed.
    1  One or more checks failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import jsonschema
import yaml

REPO_ROOT = Path(__file__).parent.parent
REGISTRY_PATH = REPO_ROOT / "model-registry" / "registry.yaml"
SCHEMA_PATH = REPO_ROOT / "schemas" / "model-registry.schema.json"

_UA = "convsim-registry-check/1.0"
_TIMEOUT = 30


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _check_schema(registry: dict, schema: dict) -> list[str]:
    try:
        jsonschema.validate(instance=registry, schema=schema)
        return []
    except jsonschema.ValidationError as exc:
        return [f"Schema validation failed: {exc.message} (at {list(exc.absolute_path)})"]


def _check_no_pending(registry: dict) -> list[str]:
    errors: list[str] = []
    for model in registry.get("models", []):
        mid = model.get("id", "<unknown>")
        download = model.get("download", {})
        if download.get("url") == "PENDING":
            errors.append(f"  {mid}: download.url is PENDING")
        if download.get("sha256") == "PENDING":
            errors.append(f"  {mid}: download.sha256 is PENDING")
    return errors


def _check_urls(registry: dict) -> list[str]:
    errors: list[str] = []
    for model in registry.get("models", []):
        mid = model.get("id", "<unknown>")
        download = model.get("download", {})
        if download.get("provider") == "user-filesystem":
            continue
        url = download.get("url", "")
        if not url or url == "PENDING":
            continue
        display = url[:90] + ("…" if len(url) > 90 else "")
        print(f"  HEAD {display}", end=" ", flush=True)
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                print(f"→ HTTP {resp.status}")
                if resp.status not in (200, 206):
                    errors.append(f"  {mid}: unexpected HTTP {resp.status}")
        except urllib.error.HTTPError as exc:
            print(f"→ HTTP {exc.code}")
            # 403/405 on HEAD can mean the CDN blocks the HEAD method but allows
            # GET; treat those as a warning rather than a hard failure for
            # HuggingFace URLs.  A 404 is NOT tolerated: it means the pinned file
            # is gone and maintainers should be alerted.
            if exc.code in (403, 405) and "huggingface.co" in url:
                print(f"    (ignoring {exc.code} — HuggingFace CDN blocks HEAD; "
                      "use GET to verify reachability)")
            else:
                errors.append(f"  {mid}: HTTP {exc.code} for {url}")
        except Exception as exc:
            print(f"→ ERROR: {exc}")
            errors.append(f"  {mid}: {exc!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url-check",
        action="store_true",
        help="HEAD-request each download URL to verify reachability (nightly CI).",
    )
    args = parser.parse_args()

    failed = False

    print(f"Registry : {REGISTRY_PATH.relative_to(REPO_ROOT)}")
    print(f"Schema   : {SCHEMA_PATH.relative_to(REPO_ROOT)}")
    print()

    print("Loading files …")
    schema = _load_json(SCHEMA_PATH)
    registry = _load_yaml(REGISTRY_PATH)

    print("1/3  Schema validation …")
    schema_errors = _check_schema(registry, schema)
    if schema_errors:
        print("     FAIL:")
        for e in schema_errors:
            print(f"       {e}")
        failed = True
    else:
        n = len(registry.get("models", []))
        print(f"     OK — {n} model(s) valid")

    print("2/3  No-PENDING check …")
    pending_errors = _check_no_pending(registry)
    if pending_errors:
        print("     FAIL — PENDING values found:")
        for e in pending_errors:
            print(e)
        failed = True
    else:
        print("     OK — no PENDING values")

    if args.url_check:
        print("3/3  URL HEAD checks …")
        url_errors = _check_urls(registry)
        if url_errors:
            print("     FAIL:")
            for e in url_errors:
                print(e)
            failed = True
        else:
            print("     OK — all URLs reachable")
    else:
        print("3/3  URL HEAD checks skipped (pass --url-check to enable)")

    print()
    if failed:
        print("Registry validation FAILED.")
        return 1

    print("Registry validation PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
