#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Hold the tracker to the shape declared in .github/project-structure.yml.

Labels say WHERE work lands, fields say WHAT KIND it is and HOW URGENT, and
milestones say WHEN it ships (issue #491).  This script is what keeps those
three systems from drifting back into each other.

Usage:
    python scripts/project-structure.py validate        # offline — the CI gate
    python scripts/project-structure.py self-test       # offline — the CI gate
    python scripts/project-structure.py audit           # live tracker vs. manifest
    python scripts/project-structure.py apply           # converge the tracker
    python scripts/project-structure.py apply --dry-run # print the plan only

`validate` reads files only: the manifest is coherent, the issue forms use no
label the manifest does not define, and CONTRIBUTING's label tables list exactly
the labels that exist.  It needs no network and no credentials.

`self-test` drives the planner and the rule checker against fixtures instead of
the live tracker, so the behaviour this script's comments promise is checked on
every pull request rather than only when a maintainer runs `apply`.

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

# The heading whose tables have to agree with the manifest.  The section runs to
# the next heading of the same depth, so its `###` subsections are included, and
# only table rows are inspected: prose may name a retired label freely, since
# explaining why `bug` is gone is half the point of the section.  A consequence
# worth knowing: anything backticked inside a table row is read as a label name,
# so field values in those tables are deliberately left unquoted.
CONTRIBUTING_SECTION = "## Labels, fields, and milestones"
# How that section is named in error messages.  Derived, so renaming the heading
# cannot leave a message pointing at a section that no longer exists.
CONTRIBUTING_REF = f"CONTRIBUTING.md § {CONTRIBUTING_SECTION.lstrip('# ')}"


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
    for key in ("owner", "number", "issue_types", "priorities", "phases"):
        if not project.get(key):
            errors.append(f"project.{key} is missing")
    types = set(project.get("issue_types") or [])
    priorities = set(project.get("priorities") or [])
    phases = set(project.get("phases") or [])

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
    meta = rules.get("meta_label")
    if meta and meta not in live:
        errors.append(f"rules.meta_label {meta!r} is not a declared label")
    for name in rules.get("area_exempt_types") or []:
        if name not in types:
            errors.append(f"rules.area_exempt_types names unknown issue type {name!r}")

    backfill = manifest.get("backfill") or {}
    known = {
        "milestones": set(titles),
        "priorities": priorities,
        "types": types,
        "phases": phases,
        "labels": live,
    }
    # A section the planner does not read is a silent no-op, which is the worst
    # kind of typo: `apply` reports success and changes nothing.
    for section in sorted(set(backfill) - set(known)):
        errors.append(f"backfill.{section!r} is not a section this script applies")
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
    than reach for a type label.

    The `type:` key is required, not merely validated: `require_type_when_open`
    means an issue filed without a Type is out of compliance the moment it is
    opened, and the form is the only place that can set one before a human
    sees it.  A form that omits it manufactures the drift the audit then
    reports.
    """
    errors: list[str] = []
    live = set(label_names(manifest))
    retired = set(retired_names(manifest))
    types = set((manifest.get("project") or {}).get("issue_types") or [])
    require_type = bool((manifest.get("rules") or {}).get("require_type_when_open"))
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
        if issue_type is None:
            if require_type:
                errors.append(
                    f"{name}: has no `type:` — every issue this form opens would "
                    f"land with no Type, which rules.require_type_when_open forbids"
                )
        elif issue_type not in types:
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
        errors.append(f"{CONTRIBUTING_REF} does not list label {name!r}")
    for name in sorted(documented - live):
        what = "retired label" if name in retired else "unknown label"
        errors.append(f"{CONTRIBUTING_REF} table still lists {what} {name!r}")
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

        # The board row comes first.  Priority and Phase are project fields
        # addressed by the issue's item id, so writing either one to an issue
        # that is not on the board yet aborts the whole run.
        if rules.get("require_project_membership") and not issue.get("in_project"):
            actions.append(
                Action("project.add", f"#{number}", {"number": number, "url": issue.get("url")})
            )

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

        meta = rules.get("meta_label")
        if (
            issue.get("state") == "OPEN"
            and not issue.get("milestone")
            and not (meta and meta in labels)
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
    return actions


def plan(manifest, labels, milestones, issues) -> list[Action]:
    """Order matters: a milestone has to exist before an issue can point at it,
    an issue has to be on the board before a project field can be written to
    it, and a retired label has to reach its field before it is deleted."""
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
    meta_label = rules.get("meta_label")
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
        is_meta = bool(meta_label) and meta_label in labels
        if issue.get("state") == "OPEN":
            if (
                rules.get("require_milestone_when_open")
                and not issue.get("milestone")
                and not is_meta
            ):
                findings.append(f"{ref} is open with no milestone")
            if rules.get("require_type_when_open") and not issue.get("type"):
                findings.append(f"{ref} is open with no Type")
            if rules.get("require_priority_when_open") and not issue.get("priority"):
                findings.append(f"{ref} is open with no Priority")
            if (
                rules.get("require_area_when_open")
                and not is_meta
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
        self._fields: dict[str, dict[str, Any]] | None = None

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
            # Record the id `item-add` hands back rather than re-reading the
            # board: the GraphQL item list is eventually consistent, so a
            # refetch can still miss a row that was just created, and the
            # Priority write queued behind this action would then abort.
            out = self._run(
                ["gh", "project", "item-add", str(self.project["number"]),
                 "--owner", self.project["owner"], "--url", payload["url"],
                 "--format", "json"]
            )
            try:
                self._item_ids[payload["number"]] = json.loads(out)["id"]
            except (ValueError, KeyError, TypeError):
                pass  # `_item_id` falls back to re-reading the board
        elif action.kind == "issue.priority":
            self._set_field(payload["number"], self.project["priority_field"], payload["priority"])
        elif action.kind == "issue.phase":
            self._set_field(payload["number"], self.project["phase_field"], payload["phase"])
        else:  # pragma: no cover - guard against a planner/executor mismatch
            raise SystemExit(f"no executor for action kind {action.kind!r}")

    def fields(self) -> dict[str, dict[str, Any]]:
        """{field name: {"id", "options": {option name: option id}}} for the board."""
        if self._fields is None:
            raw = self._json(
                [
                    "gh", "project", "field-list", str(self.project["number"]),
                    "--owner", self.project["owner"], "--limit", "100", "--format", "json",
                ]
            )
            self._fields = {
                entry["name"]: {
                    "id": entry["id"],
                    "options": {
                        option["name"]: option["id"] for option in entry.get("options") or []
                    },
                }
                for entry in raw["fields"]
            }
        return self._fields

    def _item_id(self, number: int) -> str | None:
        """The issue's board item id, re-reading the board once on a miss."""
        if number not in self._item_ids:
            self._item_ids.update(
                {n: data["item_id"] for n, data in self.project_items().items()}
            )
        return self._item_ids.get(number)

    def _set_field(self, number: int, field_name: str, value: str) -> None:
        """Set a single-select field on an issue's board item.

        Addressed entirely by node id: `gh project item-edit` refuses `--field`
        together with `--id`, and resolving the option id ourselves also turns a
        mis-spelled option — an en dash where the board has an em dash — into a
        legible error instead of a silent no-op.
        """
        item_id = self._item_id(number)
        if item_id is None:
            raise SystemExit(f"issue #{number} is not on the project board; cannot set {field_name}")
        meta = self.fields().get(field_name)
        if meta is None:
            raise SystemExit(f"the board has no field named {field_name!r}")
        option_id = meta["options"].get(value)
        if option_id is None:
            known = ", ".join(sorted(meta["options"])) or "none"
            raise SystemExit(
                f"field {field_name!r} has no option {value!r}; the board offers: {known}"
            )
        self._run(
            ["gh", "project", "item-edit", "--id", item_id,
             "--project-id", self.project_id(),
             "--field-id", meta["id"], "--single-select-option-id", option_id]
        )


# ── Self-test ────────────────────────────────────────────────────────────────
#
# The planner and the rule checker are pure functions, so they can be driven
# offline against fixtures — no gh CLI, no network, no live tracker.  `validate`
# proves the real manifest is coherent; this proves the code that reads it does
# what the comments above claim, including the three behaviours that are easy to
# get wrong and expensive to get wrong: retired-label precedence, never
# overwriting a field a human already set, and modelling a repo-wide label
# delete or rename before the rules are checked.

_FIXTURE = """
project:
  owner: acme
  number: 1
  priority_field: Priority
  phase_field: Phase
  issue_types: [Task, Bug, Feature, Epic]
  priorities: [P0, P1]
  phases: ["01"]
labels:
  - name: area:engine
    color: "1d76db"
    description: The engine
  - name: area:docs
    color: "1d76db"
    renamed_from: docs
    description: The docs
  - name: meta
    color: "cfd3d7"
    description: Housekeeping
retired_labels:
  - name: epic
    type: Epic
  - name: bug
    type: Bug
  - name: docs
    type: Task
    rename_to: area:docs
  - name: "priority:P0"
    priority: P0
milestones:
  - title: v1
    due_on: 2026-01-31
    state: open
    description: The first train
rules:
  require_project_membership: true
  meta_label: meta
  require_milestone_when_open: true
  require_type_when_open: true
  require_priority_when_open: true
  require_area_when_open: true
  area_exempt_types: [Epic]
  require_phase_or_milestone_when_closed: true
backfill:
  milestones:
    v1: [3]
  priorities:
    P1: [3]
  labels:
    area:engine: [3]
"""

# As the repo looks before `apply` runs: the retired labels are all still there.
_FIXTURE_LIVE_LABELS = [
    {"name": "area:engine", "color": "1d76db", "description": "The engine"},
    {"name": "docs", "color": "0075ca", "description": "Documentation"},
    {"name": "bug", "color": "d73a4a", "description": "Something isn't working"},
    {"name": "epic", "color": "5319e7", "description": "Umbrella issue"},
    {"name": "priority:P0", "color": "b60205", "description": "Blocker"},
]


def _issue(number: int, **overrides: Any) -> dict[str, Any]:
    issue = {
        "number": number,
        "state": "OPEN",
        "url": f"https://example.invalid/{number}",
        "labels": [],
        "milestone": None,
        "type": None,
        "priority": None,
        "phase": None,
        "in_project": True,
    }
    issue.update(overrides)
    return issue


def _fixture_issues() -> list[dict[str, Any]]:
    return [
        # Two type labels at once: `epic` is listed first, so it wins.
        _issue(1, state="CLOSED", labels=["bug", "docs"], phase="01"),
        _issue(2, labels=["epic", "bug", "priority:P0"], milestone="v1"),
        # Type already set by a human; the backfill fills only the gaps.
        _issue(3, labels=[], type="Feature", in_project=False),
        # Housekeeping: no milestone and no area, and that is correct.
        _issue(4, labels=["meta"], type="Task", priority="P0"),
    ]


def _contributing(*rows: str) -> str:
    body = "\n".join(f"| Axis | {row} | Question |" for row in rows)
    return (
        f"## Paths by role\n\nSome prose that mentions `bug` and `priority:P0`.\n\n"
        f"{CONTRIBUTING_SECTION}\n\n"
        f"| Axis | Labels | Question |\n| ---- | ------ | -------- |\n{body}\n\n"
        f"Prose below the table may name the retired `enhancement` label freely.\n\n"
        f"## Development setup\n\n`bug` again, out of section.\n"
    )


def _kinds(actions: list[Action]) -> list[tuple[str, str]]:
    return [(action.kind, action.summary) for action in actions]


def self_test() -> int:
    manifest = yaml.safe_load(_FIXTURE)
    labels, issues = _FIXTURE_LIVE_LABELS, _fixture_issues()
    actions = plan(manifest, labels, [], issues)
    after = simulate(issues, actions)
    by_number = {issue["number"]: issue for issue in after}

    broken = yaml.safe_load(_FIXTURE)
    broken["labels"].append({"name": "area:engine", "color": "nothex"})
    broken["labels"].append({"name": "bug", "color": "d73a4a", "description": "Dup"})
    broken["retired_labels"].append({"name": "stale"})
    broken["milestones"].append({"title": "v2", "state": "open"})
    broken["rules"]["meta_label"] = "nope"
    broken["backfill"]["milestones"]["v9"] = [7]
    broken["backfill"]["priorities"]["P0"] = [3]
    broken["backfill"]["phases"] = {"99 · Never": [7]}
    broken["backfill"]["labelz"] = {"area:engine": [7]}

    cases: list[tuple[str, Any, Any]] = [
        # -- the manifest checks
        ("fixture manifest is coherent", manifest_errors(manifest), []),
        ("real manifest is coherent", manifest_errors(load_manifest()), []),
        ("duplicate label is reported",
         any("declared twice" in e for e in manifest_errors(broken)), True),
        ("non-hex colour is reported",
         any("non six-digit-hex" in e for e in manifest_errors(broken)), True),
        ("missing description is reported",
         any("has no description" in e for e in manifest_errors(broken)), True),
        ("label that is both live and retired is reported",
         any("both a declared label and a retired one" in e for e in manifest_errors(broken)),
         True),
        ("retired label with no replacement field is reported",
         any("names no replacement field" in e for e in manifest_errors(broken)), True),
        ("milestone with no due date is reported",
         any("has no due date" in e for e in manifest_errors(broken)), True),
        ("undeclared meta_label is reported",
         any("rules.meta_label" in e for e in manifest_errors(broken)), True),
        ("backfill naming an unknown milestone is reported",
         any("unknown value 'v9'" in e for e in manifest_errors(broken)), True),
        ("backfill assigning one issue twice is reported",
         any("assigns issue #3 to both" in e for e in manifest_errors(broken)), True),
        ("backfill naming an undeclared phase is reported",
         any("unknown value '99 · Never'" in e for e in manifest_errors(broken)), True),
        ("a backfill section the planner never reads is reported",
         any("'labelz' is not a section this script applies" in e
             for e in manifest_errors(broken)), True),
        ("due_on normalises to YYYY-MM-DD",
         [due_date(dt.date(2026, 1, 31)), due_date("2026-01-31T12:00:00Z"), due_date(None)],
         ["2026-01-31", "2026-01-31", None]),

        # -- the issue forms
        ("clean issue form passes",
         template_errors(manifest, {"a.yml": {"labels": ["area:docs"], "type": "Bug"}}), []),
        ("issue form using a retired label is pointed at `type:`",
         template_errors(manifest, {"a.yml": {"labels": ["bug"], "type": "Bug"}}),
         ["a.yml: labels: includes retired label 'bug' — use the issue form's "
          "`type:` key or an area label instead"]),
        ("issue form using an undeclared label is reported",
         template_errors(manifest, {"a.yml": {"labels": ["area:nope"], "type": "Bug"}}),
         ["a.yml: labels: includes undeclared label 'area:nope'"]),
        ("issue form with an unknown type is reported",
         template_errors(manifest, {"a.yml": {"type": "Chore"}}),
         ["a.yml: type: 'Chore' is not a known issue type"]),
        ("issue form with no `type:` is reported",
         template_errors(manifest, {"a.yml": {"labels": ["area:docs"]}}),
         ["a.yml: has no `type:` — every issue this form opens would land with "
          "no Type, which rules.require_type_when_open forbids"]),
        ("a form needs no `type:` when the rule is off",
         template_errors({**manifest, "rules": {}}, {"a.yml": {"labels": ["area:docs"]}}), []),

        # -- CONTRIBUTING
        ("CONTRIBUTING table matching the manifest passes",
         contributing_errors(manifest, _contributing("`area:engine` · `area:docs`", "`meta`")),
         []),
        ("prose outside the table may name retired labels",
         any("'bug'" in e or "'enhancement'" in e
             for e in contributing_errors(
                 manifest, _contributing("`area:engine` · `area:docs`", "`meta`"))),
         False),
        ("CONTRIBUTING table listing a retired label is reported",
         contributing_errors(
             manifest, _contributing("`area:engine` · `area:docs`", "`meta` · `bug`")),
         ["CONTRIBUTING.md § Labels, fields, and milestones table still lists "
          "retired label 'bug'"]),
        ("CONTRIBUTING table missing a label is reported",
         contributing_errors(manifest, _contributing("`area:engine` · `area:docs`")),
         ["CONTRIBUTING.md § Labels, fields, and milestones does not list label 'meta'"]),
        ("a missing CONTRIBUTING section is reported",
         contributing_errors(manifest, "# Nothing here\n"),
         ["CONTRIBUTING.md has no table under '## Labels, fields, and milestones'"]),

        # -- the plan
        ("label with a renamed_from is renamed, not recreated",
         _kinds(plan_labels(manifest, labels)),
         [("label.rename", "docs -> area:docs"), ("label.create", "meta")]),
        ("a matching label plans no action", plan_labels(manifest, [
            {"name": "area:engine", "color": "1D76DB", "description": "The engine"},
            {"name": "area:docs", "color": "1d76db", "description": "The docs"},
            {"name": "meta", "color": "cfd3d7", "description": "Housekeeping"},
         ]), []),
        ("a recoloured label is updated in place", _kinds(plan_labels(manifest, [
            {"name": "area:engine", "color": "ff0000", "description": "The engine"},
            {"name": "area:docs", "color": "1d76db", "description": "The docs"},
            {"name": "meta", "color": "cfd3d7", "description": "Housekeeping"},
         ])), [("label.update", "area:engine")]),
        ("retired labels are deleted, except the renamed one",
         _kinds(plan_label_deletions(manifest, labels)),
         [("label.delete", "epic"), ("label.delete", "bug"),
          ("label.delete", "priority:P0")]),
        ("a missing milestone is created",
         _kinds(plan_milestones(manifest, [])), [("milestone.create", "v1")]),
        ("a drifted milestone names the drifted keys",
         _kinds(plan_milestones(manifest, [
             {"number": 9, "title": "v1", "state": "open",
              "due_on": "2026-02-28", "description": "The first train"}])),
         [("milestone.update", "v1 (due_on)")]),
        ("a matching milestone plans no action", plan_milestones(manifest, [
            {"number": 9, "title": "v1", "state": "open",
             "due_on": "2026-01-31", "description": "The first train"}]), []),
        ("deletions are planned last, after the signal reaches its field",
         [action.kind for action in actions].index("label.delete")
         > max(i for i, a in enumerate(actions) if a.kind.startswith("issue.")), True),
        ("milestones are created before an issue points at one",
         [a.kind for a in actions].index("milestone.create")
         < [a.kind for a in actions].index("issue.milestone"), True),

        # -- field migration and backfill
        ("the first retired label listed wins the type", by_number[1]["type"], "Bug"),
        ("`epic` outranks `bug` for the type", by_number[2]["type"], "Epic"),
        ("priority migrates out of its label", by_number[2]["priority"], "P0"),
        ("a type a human set is never overwritten", by_number[3]["type"], "Feature"),
        ("backfill fills the priority gap", by_number[3]["priority"], "P1"),
        ("backfill fills the milestone gap", by_number[3]["milestone"], "v1"),
        ("backfill adds the area label", by_number[3]["labels"], ["area:engine"]),
        ("an issue off the board is added to it",
         ("project.add", "#3") in _kinds(actions), True),
        # Priority and Phase are written to a board item id, so the row has to
        # exist first or `apply` aborts partway through.
        ("an issue joins the board before any field is written to it",
         next(a.kind for a in actions if a.payload.get("number") == 3), "project.add"),
        ("a meta issue is given no milestone", by_number[4]["milestone"], None),

        # -- simulate: label renames and deletes are repo-wide
        ("a deleted label leaves every issue that carried it",
         [issue["number"] for issue in after if "bug" in issue["labels"]], []),
        ("a renamed label carries its assignments over",
         by_number[1]["labels"], ["area:docs"]),
        ("labels_after reflects the whole plan",
         [entry["name"] for entry in labels_after(labels, actions)],
         ["area:docs", "area:engine", "meta"]),

        # -- the rules, against the end state
        ("the fixture plan leaves nothing for a human",
         check_rules(manifest, after, labels_after(labels, actions)), []),
        ("a repo label missing from the manifest needs a human",
         check_rules(manifest, [], [{"name": "wildcat"}]),
         ["label 'wildcat' exists on the repo but is not in the manifest — "
          "declare it or delete it by hand"]),
        ("a surviving retired label is reported",
         check_rules(manifest, [_issue(5, labels=["bug", "area:engine"], type="Bug",
                                       priority="P0", milestone="v1")], []),
         ["#5 still carries retired label(s) bug"]),
        ("an undeclared label is reported",
         check_rules(manifest, [_issue(5, labels=["area:engine", "wildcat"], type="Bug",
                                       priority="P0", milestone="v1")], []),
         ["#5 carries undeclared label(s) wildcat"]),
        ("an open issue with no milestone is reported",
         check_rules(manifest, [_issue(5, labels=["area:engine"], type="Bug",
                                       priority="P0")], []),
         ["#5 is open with no milestone"]),
        ("an open issue with no Type or Priority is reported",
         check_rules(manifest, [_issue(5, labels=["area:engine"], milestone="v1")], []),
         ["#5 is open with no Type", "#5 is open with no Priority"]),
        ("an open issue with no area is reported",
         check_rules(manifest, [_issue(5, type="Bug", priority="P0", milestone="v1")], []),
         ["#5 is open with no area: label"]),
        ("an Epic needs no area",
         check_rules(manifest, [_issue(5, type="Epic", priority="P0", milestone="v1")], []),
         []),
        ("a meta issue needs neither milestone nor area",
         check_rules(manifest, [_issue(5, labels=["meta"], type="Task", priority="P0")], []),
         []),
        ("a meta issue still needs a Type and a Priority",
         check_rules(manifest, [_issue(5, labels=["meta"])], []),
         ["#5 is open with no Type", "#5 is open with no Priority"]),
        ("an issue off the board is reported",
         check_rules(manifest, [_issue(5, labels=["meta"], type="Task", priority="P0",
                                       in_project=False)], []),
         ["#5 is not on the project board"]),
        ("closed work attributed to neither Phase nor milestone is reported",
         check_rules(manifest, [_issue(5, state="CLOSED")], []),
         ["#5 is closed but belongs to no Phase or milestone"]),
        ("closed work with a Phase is fine",
         check_rules(manifest, [_issue(5, state="CLOSED", phase="01")], []), []),
    ]

    failed = False
    for name, got, want in cases:
        if got != want:
            failed = True
            print(f"FAIL self-test: {name}\n       got  {got!r}\n       want {want!r}")
        else:
            print(f"ok   self-test: {name}")
    print("")
    print(f"{len(cases)} case(s), {'FAILED' if failed else 'all passed'}.")
    print("")
    return 1 if failed else 0


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
    print("  OK  issue forms all set a type: and use declared labels only")
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
    sub.add_parser(
        "self-test", help="verify the planner and the rules against fixtures"
    ).set_defaults(func=lambda _args: self_test())
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
