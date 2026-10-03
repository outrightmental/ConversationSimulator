#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Hold the tracker to the shape declared in .github/project-structure.yml.

Labels say WHERE work lands, fields say WHAT KIND it is and HOW URGENT, and
milestones say WHEN it ships (issue #491).  This script is what keeps those
three systems from drifting back into each other.

Usage:
    python scripts/project-structure.py validate        # offline — the CI gate
    python scripts/project-structure.py audit           # live tracker vs. manifest
    python scripts/project-structure.py apply           # converge the tracker
    python scripts/project-structure.py apply --dry-run # print the plan only

`validate` reads files only: the manifest is coherent, the issue forms use no
label the manifest does not define, and CONTRIBUTING's label table lists exactly
the labels that exist.  It needs no network and no credentials.

`audit` and `apply` talk to GitHub through the gh CLI, which must be
authenticated with the `project` scope as well as `repo`:

    gh auth refresh -s project

Exit codes:
    0  Nothing to do (audit) or everything converged (apply).
    1  Drift found (audit), work left for a human (apply), or a check failed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / ".github" / "project-structure.yml"
TEMPLATE_DIR = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
CONTRIBUTING_PATH = REPO_ROOT / "CONTRIBUTING.md"

# The heading whose table has to agree with the manifest, and the heading that
# ends that section.  Prose anywhere else may name a retired label freely —
# explaining why `bug` is gone is the whole point of the section.
CONTRIBUTING_SECTION = "## Labels"


# ── Manifest ─────────────────────────────────────────────────────────────────


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def label_names(manifest: dict[str, Any]) -> list[str]:
    return [entry["name"] for entry in manifest["labels"]]


def retired_names(manifest: dict[str, Any]) -> list[str]:
    return [entry["name"] for entry in manifest.get("retired_labels", [])]


def due_date(value: Any) -> str | None:
    """Normalise a manifest or API due date to YYYY-MM-DD."""
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)[:10]


def _invert(mapping: dict[str, Iterable[int]] | None) -> dict[int, str]:
    """{value: [issue, ...]} -> {issue: value}; last writer wins, which the
    manifest validation forbids anyway."""
    out: dict[int, str] = {}
    for value, numbers in (mapping or {}).items():
        for number in numbers:
            out[number] = value
    return out


def _invert_multi(mapping: dict[str, Iterable[int]] | None) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for value, numbers in (mapping or {}).items():
        for number in numbers:
            out.setdefault(number, []).append(value)
    return out


def manifest_errors(manifest: dict[str, Any]) -> list[str]:
    """Internal coherence of the manifest itself."""
    errors: list[str] = []
    project = manifest.get("project") or {}
    for key in ("owner", "number", "issue_types", "priorities"):
        if not project.get(key):
            errors.append(f"project.{key} is missing")
    types = set(project.get("issue_types") or [])
    priorities = set(project.get("priorities") or [])

    names = label_names(manifest)
    for name in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"label {name!r} is declared twice")
    for entry in manifest["labels"]:
        color = str(entry.get("color", ""))
        if len(color) != 6 or any(c not in "0123456789abcdef" for c in color.lower()):
            errors.append(f"label {entry['name']!r} has a non six-digit-hex color {color!r}")
        if not entry.get("description"):
            errors.append(f"label {entry['name']!r} has no description")

    live = set(names)
    for entry in manifest.get("retired_labels", []):
        name = entry["name"]
        if name in live:
            errors.append(f"{name!r} is both a declared label and a retired one")
        if not (entry.get("type") or entry.get("priority")):
            errors.append(f"retired label {name!r} names no replacement field")
        if entry.get("type") and entry["type"] not in types:
            errors.append(f"retired label {name!r} maps to unknown issue type {entry['type']!r}")
        if entry.get("priority") and entry["priority"] not in priorities:
            errors.append(f"retired label {name!r} maps to unknown priority {entry['priority']!r}")
        target = entry.get("rename_to")
        if target and target not in live:
            errors.append(f"retired label {name!r} renames to undeclared label {target!r}")

    titles = [entry["title"] for entry in manifest.get("milestones", [])]
    for title in sorted({t for t in titles if titles.count(t) > 1}):
        errors.append(f"milestone {title!r} is declared twice")
    for entry in manifest.get("milestones", []):
        if entry.get("state") not in ("open", "closed"):
            errors.append(f"milestone {entry['title']!r} has state {entry.get('state')!r}")
        if not due_date(entry.get("due_on")):
            errors.append(f"milestone {entry['title']!r} has no due date — velocity needs one")

    rules = manifest.get("rules") or {}
    exempt = rules.get("milestone_exempt_label")
    if exempt and exempt not in live:
        errors.append(f"rules.milestone_exempt_label {exempt!r} is not a declared label")
    for name in rules.get("area_exempt_types") or []:
        if name not in types:
            errors.append(f"rules.area_exempt_types names unknown issue type {name!r}")

    backfill = manifest.get("backfill") or {}
    known = {
        "milestones": set(titles),
        "priorities": priorities,
        "types": types,
        "labels": live,
    }
    for section, allowed in known.items():
        seen: dict[int, str] = {}
        for value, numbers in (backfill.get(section) or {}).items():
            if value not in allowed:
                errors.append(f"backfill.{section} names unknown value {value!r}")
            for number in numbers:
                if section != "labels" and number in seen:
                    errors.append(
                        f"backfill.{section} assigns issue #{number} to both "
                        f"{seen[number]!r} and {value!r}"
                    )
                seen[number] = value
    return errors


# ── Offline checks ───────────────────────────────────────────────────────────


def template_errors(manifest: dict[str, Any], templates: dict[str, dict[str, Any]]) -> list[str]:
    """Issue forms may only use declared labels, and must set `type:` rather
    than reach for a type label."""
    errors: list[str] = []
    live = set(label_names(manifest))
    retired = set(retired_names(manifest))
    types = set((manifest.get("project") or {}).get("issue_types") or [])
    for name, data in sorted(templates.items()):
        for label in data.get("labels") or []:
            if label in retired:
                errors.append(
                    f"{name}: labels: includes retired label {label!r} — "
                    f"use the issue form's `type:` key or an area label instead"
                )
            elif label not in live:
                errors.append(f"{name}: labels: includes undeclared label {label!r}")
        issue_type = data.get("type")
        if issue_type is not None and issue_type not in types:
            errors.append(f"{name}: type: {issue_type!r} is not a known issue type")
    return errors


def _contributing_section(text: str, heading: str = CONTRIBUTING_SECTION) -> list[str]:
    """The table rows under `heading`, up to the next heading of the same depth."""
    rows: list[str] = []
    depth = heading.split(" ")[0]
    inside = False
    for line in text.splitlines():
        if line.strip() == heading:
            inside = True
            continue
        if inside and line.startswith(depth + " "):
            break
        if inside and line.lstrip().startswith("|"):
            rows.append(line)
    return rows


def contributing_errors(manifest: dict[str, Any], text: str) -> list[str]:
    """The label table in CONTRIBUTING has to list exactly the real labels —
    a doc that lies about the taxonomy is how the taxonomy rots."""
    rows = _contributing_section(text)
    if not rows:
        return [f"CONTRIBUTING.md has no table under {CONTRIBUTING_SECTION!r}"]
    documented = {token for row in rows for token in _backticked(row)}
    live = set(label_names(manifest))
    retired = set(retired_names(manifest))
    errors = []
    for name in sorted(live - documented):
        errors.append(f"CONTRIBUTING.md § Labels does not list label {name!r}")
    for name in sorted(documented - live):
        what = "retired label" if name in retired else "unknown label"
        errors.append(f"CONTRIBUTING.md § Labels table still lists {what} {name!r}")
    return errors


def _backticked(line: str) -> list[str]:
    out, rest = [], line
    while "`" in rest:
        _, _, rest = rest.partition("`")
        token, _, rest = rest.partition("`")
        if token:
            out.append(token)
    return out


def load_templates(directory: Path = TEMPLATE_DIR) -> dict[str, dict[str, Any]]:
    templates = {}
    for path in sorted(directory.glob("*.yml")):
        if path.name == "config.yml":  # not an issue form
            continue
        with open(path, encoding="utf-8") as handle:
            templates[path.name] = yaml.safe_load(handle) or {}
    return templates


# ── Plan ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Action:
    kind: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict, compare=True)

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.kind:<20} {self.summary}"


def plan_labels(manifest: dict[str, Any], live: list[dict[str, Any]]) -> list[Action]:
    """Create, rename, and recolour labels.  Deletions are planned separately so
    they can run after the signal has been migrated into a field."""
    by_name = {entry["name"]: entry for entry in live}
    actions: list[Action] = []
    for want in manifest["labels"]:
        name, color = want["name"], str(want["color"]).lower()
        description = want.get("description") or ""
        source = want.get("renamed_from")
        have = by_name.get(name)
        if have is None and source and source in by_name:
            actions.append(
                Action(
                    "label.rename",
                    f"{source} -> {name}",
                    {"old": source, "name": name, "color": color, "description": description},
                )
            )
            continue
        if have is None:
            actions.append(
                Action(
                    "label.create",
                    name,
                    {"name": name, "color": color, "description": description},
                )
            )
            continue
        if str(have.get("color", "")).lower() != color or (have.get("description") or "") != description:
            actions.append(
                Action(
                    "label.update",
                    name,
                    {"name": name, "color": color, "description": description},
                )
            )
    return actions


def plan_label_deletions(manifest: dict[str, Any], live: list[dict[str, Any]]) -> list[Action]:
    present = {entry["name"] for entry in live}
    actions = []
    for entry in manifest.get("retired_labels", []):
        name = entry["name"]
        # A rename removes the old name for us; deleting would throw the
        # assignments away instead of carrying them over.
        if entry.get("rename_to"):
            continue
        if name in present:
            actions.append(Action("label.delete", name, {"name": name}))
    return actions


def plan_milestones(manifest: dict[str, Any], live: list[dict[str, Any]]) -> list[Action]:
    by_title = {entry["title"]: entry for entry in live}
    actions = []
    for want in manifest.get("milestones", []):
        title = want["title"]
        payload = {
            "title": title,
            "due_on": due_date(want.get("due_on")),
            "state": want.get("state", "open"),
            "description": (want.get("description") or "").strip(),
        }
        have = by_title.get(title)
        if have is None:
            actions.append(Action("milestone.create", title, payload))
            continue
        drift = {
            key: value
            for key, value in payload.items()
            if key != "title"
            and value != (due_date(have.get(key)) if key == "due_on" else (have.get(key) or ""))
        }
        if drift:
            actions.append(
                Action(
                    "milestone.update",
                    f"{title} ({', '.join(sorted(drift))})",
                    {**payload, "number": have["number"]},
                )
            )
    return actions


def plan_issues(manifest: dict[str, Any], issues: list[dict[str, Any]]) -> list[Action]:
    """Migrate retired labels into fields, then apply the one-time backfill.

    Nothing here overwrites a value that is already set, so a second run is a
    no-op and a human's triage always wins over the manifest.
    """
    rules = manifest.get("rules") or {}
    backfill = manifest.get("backfill") or {}
    want_milestone = _invert(backfill.get("milestones"))
    want_priority = _invert(backfill.get("priorities"))
    want_type = _invert(backfill.get("types"))
    want_phase = _invert(backfill.get("phases"))
    want_labels = _invert_multi(backfill.get("labels"))
    retired = manifest.get("retired_labels", [])

    actions: list[Action] = []
    for issue in sorted(issues, key=lambda i: i["number"]):
        number = issue["number"]
        labels = set(issue.get("labels") or [])

        if not issue.get("type"):
            migrated = next(
                (e["type"] for e in retired if e.get("type") and e["name"] in labels), None
            )
            new_type = migrated or want_type.get(number)
            if new_type:
                why = "from label" if migrated else "backfill"
                actions.append(
                    Action("issue.type", f"#{number} -> {new_type} ({why})",
                           {"number": number, "type": new_type})
                )

        if not issue.get("priority"):
            migrated = next(
                (e["priority"] for e in retired if e.get("priority") and e["name"] in labels), None
            )
            new_priority = migrated or want_priority.get(number)
            if new_priority:
                why = "from label" if migrated else "backfill"
                actions.append(
                    Action("issue.priority", f"#{number} -> {new_priority} ({why})",
                           {"number": number, "priority": new_priority})
                )

        missing = [name for name in want_labels.get(number, []) if name not in labels]
        if missing:
            actions.append(
                Action("issue.labels", f"#{number} += {', '.join(missing)}",
                       {"number": number, "add": missing})
            )
            labels.update(missing)

        exempt = rules.get("milestone_exempt_label")
        if (
            issue.get("state") == "OPEN"
            and not issue.get("milestone")
            and not (exempt and exempt in labels)
            and number in want_milestone
        ):
            actions.append(
                Action("issue.milestone", f"#{number} -> {want_milestone[number]}",
                       {"number": number, "milestone": want_milestone[number]})
            )

        if (
            issue.get("state") == "CLOSED"
            and not issue.get("phase")
            and not issue.get("milestone")
            and number in want_phase
        ):
            actions.append(
                Action("issue.phase", f"#{number} -> {want_phase[number]}",
                       {"number": number, "phase": want_phase[number]})
            )

        if rules.get("require_project_membership") and not issue.get("in_project"):
            actions.append(
                Action("project.add", f"#{number}", {"number": number, "url": issue.get("url")})
            )
    return actions


def plan(manifest, labels, milestones, issues) -> list[Action]:
    """Order matters: a milestone has to exist before an issue can point at it,
    and a retired label has to reach its field before it is deleted."""
    return [
        *plan_milestones(manifest, milestones),
        *plan_labels(manifest, labels),
        *plan_issues(manifest, issues),
        *plan_label_deletions(manifest, labels),
    ]


def simulate(issues: list[dict[str, Any]], actions: list[Action]) -> list[dict[str, Any]]:
    """The issue list as it would look after the plan runs.

    Label renames and deletions are repo-wide: deleting `chore` strips it from
    every issue that carried it, and renaming `docs` carries its assignments
    over to `area:docs`.  Modelling that is what lets the rule check run against
    the end state instead of flagging a hundred issues for labels the same plan
    is about to remove.
    """
    out = {issue["number"]: dict(issue) for issue in issues}
    for action in actions:
        if action.kind in ("label.delete", "label.rename"):
            old = action.payload.get("old", action.payload.get("name"))
            new = action.payload["name"] if action.kind == "label.rename" else None
            for issue in out.values():
                labels = set(issue.get("labels") or [])
                if old in labels:
                    labels.discard(old)
                    if new:
                        labels.add(new)
                    issue["labels"] = sorted(labels)
            continue
        number = action.payload.get("number")
        issue = out.get(number)
        if issue is None:
            continue
        if action.kind == "issue.type":
            issue["type"] = action.payload["type"]
        elif action.kind == "issue.priority":
            issue["priority"] = action.payload["priority"]
        elif action.kind == "issue.milestone":
            issue["milestone"] = action.payload["milestone"]
        elif action.kind == "issue.phase":
            issue["phase"] = action.payload["phase"]
        elif action.kind == "issue.labels":
            issue["labels"] = sorted(set(issue.get("labels") or []) | set(action.payload["add"]))
        elif action.kind == "project.add":
            issue["in_project"] = True
    return list(out.values())


def check_rules(
    manifest: dict[str, Any],
    issues: list[dict[str, Any]],
    live_labels: list[dict[str, Any]] | None = None,
) -> list[str]:
    """What is still wrong once the plan has run — the part needing a human."""
    rules = manifest.get("rules") or {}
    retired = set(retired_names(manifest))
    declared = set(label_names(manifest))
    exempt_label = rules.get("milestone_exempt_label")
    area_exempt = set(rules.get("area_exempt_types") or [])
    findings: list[str] = []

    for entry in live_labels or []:
        name = entry["name"]
        if name not in declared and name not in retired:
            findings.append(
                f"label {name!r} exists on the repo but is not in the manifest — "
                f"declare it or delete it by hand"
            )

    for issue in sorted(issues, key=lambda i: i["number"]):
        number, labels = issue["number"], set(issue.get("labels") or [])
        ref = f"#{number}"
        still_retired = sorted(labels & retired)
        if still_retired:
            findings.append(f"{ref} still carries retired label(s) {', '.join(still_retired)}")
        unknown = sorted(labels - declared - retired)
        if unknown:
            findings.append(f"{ref} carries undeclared label(s) {', '.join(unknown)}")
        if rules.get("require_project_membership") and not issue.get("in_project"):
            findings.append(f"{ref} is not on the project board")
        if issue.get("state") == "OPEN":
            if (
                rules.get("require_milestone_when_open")
                and not issue.get("milestone")
                and not (exempt_label and exempt_label in labels)
            ):
                findings.append(f"{ref} is open with no milestone")
            if rules.get("require_type_when_open") and not issue.get("type"):
                findings.append(f"{ref} is open with no Type")
            if rules.get("require_priority_when_open") and not issue.get("priority"):
                findings.append(f"{ref} is open with no Priority")
            if (
                rules.get("require_area_when_open")
                and issue.get("type") not in area_exempt
                and not any(name.startswith("area:") for name in labels)
            ):
                findings.append(f"{ref} is open with no area: label")
        elif rules.get("require_phase_or_milestone_when_closed"):
            if not issue.get("phase") and not issue.get("milestone"):
                findings.append(f"{ref} is closed but belongs to no Phase or milestone")
    return findings


# ── GitHub ───────────────────────────────────────────────────────────────────


class GitHub:
    """A thin shell around the gh CLI — no extra Python dependencies."""

    def __init__(self, manifest: dict[str, Any], dry_run: bool = False) -> None:
        self.project = manifest["project"]
        self.dry_run = dry_run
        repo = self._json(["gh", "repo", "view", "--json", "owner,name"])
        self.owner = repo["owner"]["login"]
        self.name = repo["name"]
        self._item_ids: dict[int, str] = {}
        self._project_id: str | None = None

    # -- reads

    @staticmethod
    def _run(args: list[str]) -> str:
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(
                f"command failed: {' '.join(args)}\n{result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout

    @classmethod
    def _json(cls, args: list[str]) -> Any:
        return json.loads(cls._run(args))

    def labels(self) -> list[dict[str, Any]]:
        return self._json(
            ["gh", "label", "list", "--limit", "200", "--json", "name,color,description"]
        )

    def milestones(self) -> list[dict[str, Any]]:
        raw = self._json(
            [
                "gh", "api", "--paginate",
                f"repos/{self.owner}/{self.name}/milestones?state=all&per_page=100",
            ]
        )
        return [
            {
                "number": entry["number"],
                "title": entry["title"],
                "state": entry["state"],
                "due_on": due_date(entry.get("due_on")),
                "description": entry.get("description") or "",
            }
            for entry in raw
        ]

    _ITEMS_QUERY = """
    query($id: ID!, $cursor: String) {
      node(id: $id) {
        ... on ProjectV2 {
          items(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              content { ... on Issue { number } }
              fieldValues(first: 30) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    def project_id(self) -> str:
        if self._project_id is None:
            data = self._json(
                [
                    "gh", "project", "view", str(self.project["number"]),
                    "--owner", self.project["owner"], "--format", "json",
                ]
            )
            self._project_id = data["id"]
        return self._project_id

    def project_items(self) -> dict[int, dict[str, Any]]:
        """{issue number: {item_id, Priority, Phase, ...}} for the whole board."""
        items: dict[int, dict[str, Any]] = {}
        cursor: str | None = None
        project_id = self.project_id()
        while True:
            args = [
                "gh", "api", "graphql",
                "-f", f"query={self._ITEMS_QUERY}",
                "-F", f"id={project_id}",
            ]
            if cursor:
                args += ["-F", f"cursor={cursor}"]
            page = self._json(args)["data"]["node"]["items"]
            for node in page["nodes"]:
                content = node.get("content") or {}
                number = content.get("number")
                if number is None:  # draft item or a pull request
                    continue
                fields = {
                    value["field"]["name"]: value["name"]
                    for value in node["fieldValues"]["nodes"]
                    if value and value.get("field")
                }
                items[number] = {"item_id": node["id"], **fields}
            if not page["pageInfo"]["hasNextPage"]:
                return items
            cursor = page["pageInfo"]["endCursor"]

    def issues(self) -> list[dict[str, Any]]:
        raw = self._json(
            [
                "gh", "issue", "list", "--state", "all", "--limit", "1000",
                "--json", "number,state,url,labels,milestone,issueType",
            ]
        )
        items = self.project_items()
        self._item_ids = {number: data["item_id"] for number, data in items.items()}
        issues = []
        for entry in raw:
            item = items.get(entry["number"], {})
            issues.append(
                {
                    "number": entry["number"],
                    "state": entry["state"],
                    "url": entry["url"],
                    "labels": [label["name"] for label in entry["labels"]],
                    "milestone": (entry.get("milestone") or {}).get("title"),
                    "type": (entry.get("issueType") or {}).get("name"),
                    "in_project": entry["number"] in items,
                    "priority": item.get(self.project["priority_field"]),
                    "phase": item.get(self.project["phase_field"]),
                }
            )
        return issues

    # -- writes

    def execute(self, action: Action) -> None:
        if self.dry_run:
            return
        payload = action.payload
        if action.kind == "label.create":
            self._run(
                ["gh", "label", "create", payload["name"], "--color", payload["color"],
                 "--description", payload["description"], "--force"]
            )
        elif action.kind == "label.rename":
            self._run(
                ["gh", "label", "edit", payload["old"], "--name", payload["name"],
                 "--color", payload["color"], "--description", payload["description"]]
            )
        elif action.kind == "label.update":
            self._run(
                ["gh", "label", "edit", payload["name"], "--color", payload["color"],
                 "--description", payload["description"]]
            )
        elif action.kind == "label.delete":
            self._run(["gh", "label", "delete", payload["name"], "--yes"])
        elif action.kind == "milestone.create":
            self._run(
                ["gh", "api", "--silent", "--method", "POST",
                 f"repos/{self.owner}/{self.name}/milestones",
                 "-f", f"title={payload['title']}",
                 "-f", f"state={payload['state']}",
                 "-f", f"description={payload['description']}",
                 "-f", f"due_on={payload['due_on']}T12:00:00Z"]
            )
        elif action.kind == "milestone.update":
            self._run(
                ["gh", "api", "--silent", "--method", "PATCH",
                 f"repos/{self.owner}/{self.name}/milestones/{payload['number']}",
                 "-f", f"title={payload['title']}",
                 "-f", f"state={payload['state']}",
                 "-f", f"description={payload['description']}",
                 "-f", f"due_on={payload['due_on']}T12:00:00Z"]
            )
        elif action.kind == "issue.type":
            self._run(["gh", "issue", "edit", str(payload["number"]), "--type", payload["type"]])
        elif action.kind == "issue.milestone":
            self._run(
                ["gh", "issue", "edit", str(payload["number"]), "--milestone", payload["milestone"]]
            )
        elif action.kind == "issue.labels":
            self._run(
                ["gh", "issue", "edit", str(payload["number"]),
                 "--add-label", ",".join(payload["add"])]
            )
        elif action.kind == "project.add":
            self._run(
                ["gh", "project", "item-add", str(self.project["number"]),
                 "--owner", self.project["owner"], "--url", payload["url"]]
            )
            self._item_ids = {}  # the new item id is not known yet
        elif action.kind == "issue.priority":
            self._set_field(payload["number"], self.project["priority_field"], payload["priority"])
        elif action.kind == "issue.phase":
            self._set_field(payload["number"], self.project["phase_field"], payload["phase"])
        else:  # pragma: no cover - guard against a planner/executor mismatch
            raise SystemExit(f"no executor for action kind {action.kind!r}")

    def _set_field(self, number: int, field_name: str, value: str) -> None:
        if not self._item_ids:
            self._item_ids = {n: d["item_id"] for n, d in self.project_items().items()}
        item_id = self._item_ids.get(number)
        if item_id is None:
            raise SystemExit(f"issue #{number} is not on the project board; cannot set {field_name}")
        self._run(
            ["gh", "project", "item-edit", "--id", item_id,
             "--project-id", self.project_id(), "--field", field_name, "--value", value]
        )


# ── Commands ─────────────────────────────────────────────────────────────────


def cmd_validate(_args: argparse.Namespace) -> int:
    manifest = load_manifest()
    errors = manifest_errors(manifest)
    errors += template_errors(manifest, load_templates())
    errors += contributing_errors(manifest, CONTRIBUTING_PATH.read_text(encoding="utf-8"))
    print("")
    print("Project structure — manifest validation")
    print("=======================================")
    print("")
    if errors:
        for message in errors:
            print(f"  FAIL  {message}")
        print("")
        print(f"FAIL: {len(errors)} problem(s) in the declared project structure.")
        print("")
        return 1
    manifest_labels = label_names(manifest)
    print(f"  OK  {len(manifest_labels)} labels declared, {len(retired_names(manifest))} retired")
    print(f"  OK  {len(manifest.get('milestones', []))} milestones declared")
    print("  OK  issue forms use declared labels and types only")
    print("  OK  CONTRIBUTING.md documents exactly the declared labels")
    print("")
    return 0


def _report(actions: list[Action], findings: list[str]) -> None:
    if actions:
        print(f"Plan — {len(actions)} change(s):")
        print("")
        for action in actions:
            print(f"  {action}")
        print("")
    else:
        print("The live tracker already matches the manifest.")
        print("")
    if findings:
        print(f"Needs a human — {len(findings)} item(s) the manifest cannot decide:")
        print("")
        for finding in findings:
            print(f"  {finding}")
        print("")


def labels_after(labels: list[dict[str, Any]], actions: list[Action]) -> list[dict[str, Any]]:
    """The repo's label list as the plan would leave it."""
    names = {entry["name"] for entry in labels}
    for action in actions:
        if action.kind == "label.delete":
            names.discard(action.payload["name"])
        elif action.kind == "label.rename":
            names.discard(action.payload["old"])
            names.add(action.payload["name"])
        elif action.kind == "label.create":
            names.add(action.payload["name"])
    return [{"name": name} for name in sorted(names)]


def _collect(manifest: dict[str, Any], dry_run: bool) -> tuple[GitHub, list[Action], list[str]]:
    github = GitHub(manifest, dry_run=dry_run)
    labels, milestones, issues = github.labels(), github.milestones(), github.issues()
    actions = plan(manifest, labels, milestones, issues)
    findings = check_rules(manifest, simulate(issues, actions), labels_after(labels, actions))
    return github, actions, findings


def cmd_audit(_args: argparse.Namespace) -> int:
    manifest = load_manifest()
    print("")
    print("Project structure — audit")
    print("=========================")
    print("")
    _, actions, findings = _collect(manifest, dry_run=True)
    _report(actions, findings)
    if actions or findings:
        print(f"FAIL: tracker drifts from {MANIFEST_PATH.name}.")
        print("      Run: python scripts/project-structure.py apply")
        print("")
        return 1
    print("All checks passed.")
    print("")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    print("")
    print("Project structure — apply" + (" (dry run)" if args.dry_run else ""))
    print("=========================")
    print("")
    github, actions, findings = _collect(manifest, dry_run=args.dry_run)
    _report(actions, findings)
    if not args.dry_run:
        for action in actions:
            print(f"  applying  {action}")
            github.execute(action)
        print("")
    if findings:
        print(f"FAIL: {len(findings)} item(s) still need a human decision.")
        print("")
        return 1
    print("Converged." if not args.dry_run else "Dry run only — nothing was changed.")
    print("")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="offline manifest and documentation checks").set_defaults(
        func=cmd_validate
    )
    sub.add_parser("audit", help="compare the live tracker against the manifest").set_defaults(
        func=cmd_audit
    )
    apply_parser = sub.add_parser("apply", help="converge the live tracker on the manifest")
    apply_parser.add_argument(
        "--dry-run", action="store_true", help="print the plan without changing anything"
    )
    apply_parser.set_defaults(func=cmd_apply)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
