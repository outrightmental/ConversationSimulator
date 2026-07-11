#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Collect telemetry-free marketplace demand signals from public GitHub data.

Outputs a Markdown report suitable for pasting into sections 1.1 and 1.2 of
docs/marketplace-demand-spike.md.

Requirements:
  - The `gh` CLI installed and authenticated (`gh auth status`).
  - Run from any directory inside the repository.

Usage:
  python3 scripts/collect-marketplace-signals.py
  python3 scripts/collect-marketplace-signals.py --repo outrightmental/ConversationSimulator
  python3 scripts/collect-marketplace-signals.py --days 90
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone


REPO_DEFAULT = "outrightmental/ConversationSimulator"


def _gh(*args: str, paginate: bool = True) -> dict | list | None:
    """Run a `gh api` command and return parsed JSON, or None on error.

    Pagination is only safe for array endpoints (`gh` merges pages into one
    JSON array). For object endpoints such as `/search/*`, `--paginate` emits
    one concatenated JSON object per page, which `json.loads` cannot parse, so
    callers that read a single object must pass `paginate=False`.
    """
    cmd = ["gh", "api", *(["--paginate"] if paginate else []), *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as exc:
        print(f"  [warn] gh api failed: {exc.stderr.strip()}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        return None


def _gh_search(type_: str, terms: list[str], repo: str) -> list:
    """Run `gh search <type_>` and return the items list.

    Each search term/qualifier must be a separate argument: `gh search` treats a
    single multi-word positional as one quoted phrase, and appends its own
    `type:` qualifier (so passing `is:pr` to `gh search issues` yields a
    contradictory, always-failing query). Use the dedicated subcommand
    (`prs`/`issues`) and the `--repo` flag instead of a `repo:` qualifier.
    """
    cmd = ["gh", "search", type_, *terms, "--repo", repo,
           "--json", "number,title,createdAt", "--limit", "200"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def fetch_release_download_counts(repo: str) -> list[dict]:
    """Return asset download counts for all releases."""
    data = _gh(f"/repos/{repo}/releases")
    if not data:
        return []
    rows = []
    for release in data:
        tag = release.get("tag_name", "")
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".zip") or "pack" in name.lower():
                rows.append({
                    "release": tag,
                    "asset": name,
                    "downloads": asset.get("download_count", 0),
                })
    return rows


def fetch_community_pack_repos() -> int:
    """Return count of GitHub repos with the convsim-pack topic."""
    # Only the first page's total_count is needed, so do not paginate: the
    # search endpoint returns an object, and --paginate would concatenate one
    # object per page and break JSON parsing when the count exceeds one page.
    data = _gh("/search/repositories?q=topic:convsim-pack&per_page=1", paginate=False)
    if not isinstance(data, dict):
        return 0
    return data.get("total_count", 0)


def fetch_label_issue_count(repo: str, label: str) -> int:
    """Return open + closed issue count for a label."""
    data = _gh(f"/repos/{repo}/issues?labels={label}&state=all&per_page=100")
    if not isinstance(data, list):
        return 0
    return len(data)


def fetch_fork_count(repo: str) -> int:
    data = _gh(f"/repos/{repo}")
    if not data:
        return 0
    return data.get("forks_count", 0)


def fetch_pack_prs(repo: str) -> int:
    """Return count of PRs with 'pack' in the title."""
    items = _gh_search("prs", ["pack", "in:title"], repo)
    return len(items)


def fetch_packs_contributors() -> list[str]:
    """Return unique authors who have committed to packs/ in the current repo."""
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--format=%ae", "--", "packs/"],
            capture_output=True, text=True, check=True,
        )
        emails = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        return sorted(emails)
    except subprocess.CalledProcessError:
        return []


def since_date(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%d")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=REPO_DEFAULT, help="GitHub repo slug (owner/name)")
    parser.add_argument("--days", type=int, default=90, help="Observation window in days")
    args = parser.parse_args()

    repo = args.repo
    days = args.days
    window_start = since_date(days)

    print(f"# Marketplace demand spike — signal collection report")
    print(f"")
    print(f"Repository: {repo}")
    print(f"Observation window: last {days} days (since {window_start})")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print()

    # ── Section 1.1: Pack downloads and imports ────────────────────────────
    print("## 1.1 Pack downloads and imports")
    print()

    print("### Official pack release downloads")
    print()
    rows = fetch_release_download_counts(repo)
    if rows:
        print("| Release | Asset | Downloads |")
        print("|---------|-------|-----------|")
        for r in rows:
            print(f"| {r['release']} | {r['asset']} | {r['downloads']} |")
    else:
        print("_No pack release assets found, or gh API unavailable._")
    print()

    pack_bug_count = fetch_label_issue_count(repo, "pack-bug")
    workbench_count = fetch_label_issue_count(repo, "creator-workbench")
    community_repos = fetch_community_pack_repos()

    print("### Signal summary")
    print()
    print("| Signal | Measurement method | Count / observation |")
    print("|--------|--------------------|---------------------|")
    print(f"| Community packs: GitHub repos tagged `convsim-pack` | GitHub search `topic:convsim-pack` | {community_repos} |")
    print(f"| Pack import issues filed on GitHub | `label:pack-bug` issue count | {pack_bug_count} |")
    print(f"| Creator Workbench issues filed | `label:creator-workbench` issue count | {workbench_count} |")
    print("| Community packs: itch.io items tagged `conversation-simulator` | itch.io browse page | _manual check required_ |")
    print("| Discord `#pack-sharing` channel activity | Post count + unique contributors | _manual check required_ |")
    print()

    # ── Section 1.2: Creator activity on GitHub ────────────────────────────
    print("## 1.2 Creator activity on GitHub")
    print()

    pack_pr_count = fetch_pack_prs(repo)
    fork_count = fetch_fork_count(repo)
    packs_contributors = fetch_packs_contributors()

    print("| Signal | Measurement method | Count / observation |")
    print("|--------|--------------------|---------------------|")
    print(f"| PRs proposing new official packs | Search PRs with `pack` in title | {pack_pr_count} |")
    print(f"| Forks of the repository | GitHub fork count | {fork_count} |")
    print(f"| Contributors who touched `packs/` | `git log --all -- packs/` unique authors | {len(packs_contributors)} |")
    print("| Issues requesting pack distribution improvements | Label filter + keyword search | _manual check required_ |")
    print("| Scenario authoring guide page views | GitHub Insights (traffic API) | _requires repo admin access_ |")
    print()

    if packs_contributors:
        print(f"_Authors who have committed to `packs/` ({len(packs_contributors)} unique):_")
        print()
        for email in packs_contributors:
            print(f"- `{email}`")
        print()

    # ── Paste instructions ─────────────────────────────────────────────────
    print("---")
    print()
    print("## Next steps")
    print()
    print("1. Copy the tables above into `docs/marketplace-demand-spike.md`")
    print("   sections 1.1 and 1.2, filling in the counts.")
    print("2. Complete the manual checks noted above (itch.io, Discord, GitHub Insights).")
    print("3. Proceed to section 1.3 (Steam reviews and discussions) — these require")
    print("   manual review of the Steam review page and discussion boards.")
    print("4. When sections 1–3 of the spike doc are complete, convene the creator")
    print("   survey via the GitHub issue template at:")
    print("   .github/ISSUE_TEMPLATE/marketplace_creator_survey.yml")
    print()


if __name__ == "__main__":
    main()
