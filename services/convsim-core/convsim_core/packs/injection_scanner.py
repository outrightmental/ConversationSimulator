# SPDX-License-Identifier: Apache-2.0
"""Prompt injection scanner for scenario pack text fields.

Scans natural-language fields across a pack directory for patterns that attempt
to override simulator rules, safety policies, output schemas, or privacy
boundaries.

IMPORTANT — This scanner is a guardrail, not a complete security proof.  It
detects common injection patterns using regular expressions; novel phrasing may
evade detection.  Runtime defences (trusted/untrusted content layers, output
schema enforcement, and NPC output validation) remain active regardless of
scanner results and cannot be disabled through scenario text.

All scanning is performed locally — no pack content is ever sent to a remote
service.

Severity classification
-----------------------
WARNING (default)
  Patterns that suggest an injection attempt but may appear in legitimate
  content (e.g. training scenarios about social engineering awareness).

ERROR (high severity)
  Patterns that directly attempt to disable safety filters, exfiltrate hidden
  simulator state, or require network access during play.  These are blocked
  for all packs; the CI official-pack gate treats them as hard failures.

Player-input context
--------------------
Text in test-fixture ``player_input`` turns is already labelled untrusted by
the prompt builder.  Scanner findings in that context are capped at WARNING
severity so packs that intentionally exercise injection-detection can include
example prompts without failing validation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Optional

import yaml

# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _InjectionRule:
    rule_id: str
    severity: str  # "warning" | "error"
    description: str
    pattern: re.Pattern
    suggested_fix: str


def _compile(*patterns: str) -> re.Pattern:
    return re.compile("|".join(patterns), re.IGNORECASE)


# ---------------------------------------------------------------------------
# WARNING-tier rules
# Suspicious patterns that may appear in legitimate content (e.g. a social
# engineering awareness pack that teaches players to recognise these phrases).
# ---------------------------------------------------------------------------

_WARNING_RULES: list[_InjectionRule] = [
    _InjectionRule(
        rule_id="INJECTION_OVERRIDE_INSTRUCTIONS",
        severity="warning",
        description=(
            "Text instructs the AI to ignore or override its own rules or instructions"
        ),
        pattern=_compile(
            r"\bignore\s+(?:previous|prior|all\s+previous|your)\s+instructions?\b",
            r"\bdisregard\s+(?:your\s+)?(?:previous\s+)?(?:instructions?|rules?|guidelines?|directives?)\b",
            r"\bforget\s+(?:all\s+)?(?:previous|prior|your)\s+(?:instructions?|context|rules?)\b",
            r"\boverride\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?|rules?|guidelines?)\b",
            r"\byour\s+new\s+(?:instructions?|rules?|directives?)\s+are\b",
            r"\bfrom\s+now\s+on\s+you\s+(?:will|must|should|are\s+to)\b",
            r"\byou\s+(?:must|will|should|are\s+to)\s+now\s+(?:ignore|disregard|forget|bypass)\b",
            r"\bdiscard\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions?|context|directives?)\b",
        ),
        suggested_fix=(
            "Remove or rewrite this text. If this content is intentional player-side "
            "injection-practice material, move it to the 'player_input' field of a "
            "test fixture (tests/*.yaml) where it is already labelled untrusted."
        ),
    ),

    _InjectionRule(
        rule_id="INJECTION_JAILBREAK_PERSONA",
        severity="warning",
        description=(
            "Text attempts to replace the AI persona with one that has no restrictions"
        ),
        pattern=_compile(
            r"\bact\s+as\s+(?:DAN\b|an?\s+(?:unrestricted|uncensored|unfiltered|unmoderated)\b)",
            r"\bdo\s+anything\s+now\b",
            r"\bpretend\s+(?:you\s+have\s+no\s+restrictions|you\s+are\s+(?:unrestricted|uncensored|unfiltered))\b",
            r"\byou\s+are\s+now\s+(?:an?\s+)?(?:unrestricted|uncensored|unfiltered|DAN|jailbroken)\b",
            r"\bjailbreak\s+(?:mode|prompt|yourself|the\s+(?:AI|model|system))\b",
            r"\bdeveloper\s+mode\s+(?:enabled|on|activated|override)\b",
            r"\bgodmode\b",
            r"\bno\s+(?:ethical\s+)?(?:restrictions?|limits?|constraints?|guidelines?|rules?)\s+(?:enabled|active|mode)\b",
        ),
        suggested_fix=(
            "Remove or rewrite this text. Scenarios must not attempt to remove "
            "AI restrictions or invoke jailbreak patterns. If creating a prompt-injection "
            "detection training pack, use test fixture player_input fields instead."
        ),
    ),

    _InjectionRule(
        rule_id="INJECTION_SEPARATOR_TRICK",
        severity="warning",
        description=(
            "Text uses delimiter patterns that attempt to confuse system/user prompt boundaries"
        ),
        pattern=_compile(
            r"(?:^|\n)\s*#{3,}\s*(?:end\s+of\s+(?:system\s+)?(?:prompt|instructions?)|"
            r"system\s+(?:prompt\s+)?(?:end|over))\s*#{0,3}\s*(?:\n|$)",
            r"(?:^|\n)\s*={3,}\s*(?:end\s+of\s+(?:system\s+)?(?:prompt|instructions?)|"
            r"system\s+(?:prompt\s+)?(?:end|over))\s*={0,3}\s*(?:\n|$)",
            r"(?:^|\n)\s*-{3,}\s*(?:end\s+of\s+(?:system\s+)?(?:prompt|instructions?))\s*-{0,3}\s*(?:\n|$)",
            r"(?:^|\n)\s*\[\s*(?:system\s+override|admin\s+override|developer\s+override|"
            r"new\s+system\s+prompt|end\s+of\s+(?:system\s+)?(?:prompt|instructions?))\s*\]\s*(?:\n|$)",
        ),
        suggested_fix=(
            "Remove prompt-delimiter patterns from scenario text. These patterns can "
            "confuse system/user prompt boundaries and are not permitted in pack content."
        ),
    ),
]

# ---------------------------------------------------------------------------
# ERROR-tier rules
# Patterns that directly attempt to disable safety, extract hidden state, or
# require network access.  These are blocked for all packs and fail CI.
# ---------------------------------------------------------------------------

_ERROR_RULES: list[_InjectionRule] = [
    _InjectionRule(
        rule_id="INJECTION_DISABLE_SAFETY",
        severity="error",
        description=(
            "Text directly attempts to disable safety filters or bypass content policy"
        ),
        pattern=_compile(
            r"\bdisable\s+(?:your\s+)?(?:safety|content)\s+(?:filters?|moderation|policy|checks?|guards?|system)\b",
            r"\bturn\s+off\s+(?:your\s+)?(?:safety|content)\s+(?:filters?|moderation|policy|checks?|guards?|system)\b",
            r"\bbypass\s+(?:your\s+)?(?:safety|content)\s+(?:filters?|moderation|policy|checks?|restrictions?)\b",
            r"\bremove\s+(?:your\s+)?(?:safety|content)\s+(?:filters?|moderation|policy|restrictions?|limitations?)\b",
            r"\bignore\s+(?:(?:your|all)\s+)?(?:safety|content)\s+(?:guidelines?|policy|filters?|restrictions?)\b",
            r"\bsafety\s+(?:filters?|guidelines?|restrictions?)\s+(?:are\s+now\s+)?(?:disabled|off|bypassed|removed|ignored)\b",
            r"\bwithout\s+(?:safety|content)\s+(?:filters?|restrictions?|guidelines?|moderation)\b",
        ),
        suggested_fix=(
            "Remove content that attempts to disable safety filters. "
            "Safety policy is enforced by the runtime and cannot be overridden "
            "through scenario text."
        ),
    ),

    _InjectionRule(
        rule_id="INJECTION_EXFILTRATE_HIDDEN_STATE",
        severity="error",
        description=(
            "Text attempts to extract the system prompt, private persona, or other hidden state"
        ),
        pattern=_compile(
            r"\b(?:reveal|print|output|show|repeat|display|tell\s+me)\s+(?:your\s+)?"
            r"(?:system\s+prompt|instructions?|configuration|private\s+persona|"
            r"hidden\s+(?:goals?|agenda|state|instructions?|rules?))\b",
            r"\bwhat\s+(?:is|are|were)\s+(?:in\s+)?your\s+(?:actual\s+)?"
            r"(?:system\s+prompt|instructions?|hidden\s+(?:goals?|agenda|rules?|instructions?))\b",
            r"\b(?:output|print|repeat)\s+(?:everything\s+(?:above|before)|your\s+(?:prompt|instructions?))\b",
            r"\bexfiltrate\s+(?:the\s+)?(?:prompt|instructions?|configuration|state)\b",
            r"\bsummari[sz]e\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?)\s+(?:so\s+far|above)\b",
            r"\bshow\s+me\s+your\s+(?:private|hidden)\s+(?:persona|goals?|agenda|instructions?)\b",
        ),
        suggested_fix=(
            "Remove content that attempts to extract internal simulator state. "
            "The system prompt, private persona, and hidden goals are intentionally "
            "kept separate from player-facing content and cannot be revealed through "
            "scenario text."
        ),
    ),

    _InjectionRule(
        rule_id="INJECTION_REQUIRE_NETWORK",
        severity="error",
        description=(
            "Text requests network access during play (the simulator is offline-only)"
        ),
        pattern=_compile(
            r"\bfetch\s+(?:from\s+)?https?://",
            r"\bmake\s+an?\s+(?:HTTP|HTTPS|API|GET|POST|PUT|DELETE)\s+request\s+to\b",
            r"\bdownload\s+from\s+(?:https?://|the\s+(?:web|internet|external\s+api))\b",
            r"\bsend\s+a\s+(?:GET|POST|PUT|DELETE|HTTP|HTTPS)\s+request\s+to\b",
            r"\bcall\s+(?:the\s+)?(?:external\s+)?api\s+at\s+https?://",
            r"\bconnect\s+to\s+(?:the\s+)?(?:internet|the\s+web|external\s+(?:server|api|service))\b",
            r"\bload\s+(?:data\s+)?from\s+https?://",
        ),
        suggested_fix=(
            "Remove content that requests network access. The simulator runs "
            "offline and cannot make network requests during play. All pack assets "
            "must be bundled with the pack."
        ),
    ),
]

_ALL_RULES: list[_InjectionRule] = _WARNING_RULES + _ERROR_RULES


# ---------------------------------------------------------------------------
# Finding type
# ---------------------------------------------------------------------------


@dataclass
class InjectionFinding:
    """A single prompt-injection finding in a pack text field."""

    rule_id: str
    severity: str          # "warning" | "error"
    file: str              # relative path within the pack
    pointer: str           # JSON Pointer-style path (e.g. /goals/hidden/0)
    message: str
    suggested_fix: str
    matched_snippet: str   # short excerpt of the matching text (≤80 chars)


# ---------------------------------------------------------------------------
# Low-level text scanner
# ---------------------------------------------------------------------------


def _make_snippet(text: str, match: re.Match, window: int = 35) -> str:
    """Return a short excerpt of *text* centred on *match*, capped at 80 chars."""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    snippet = text[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet[:80]


def scan_text(
    text: str,
    file: str,
    pointer: str,
    *,
    in_player_context: bool = False,
) -> list[InjectionFinding]:
    """Scan a single text value for prompt-injection patterns.

    Args:
        text: The string value to scan.
        file: Relative path of the source file within the pack.
        pointer: JSON Pointer-style path to the scanned field (e.g. ``/title``).
        in_player_context: When ``True``, the text originates from a player turn
            (e.g. a test-fixture ``player_input`` field).  Error-severity
            findings are downgraded to warnings so injection-practice scenarios
            that intentionally include attack examples are not hard-blocked.

    Returns:
        A (possibly empty) list of :class:`InjectionFinding` objects, one per
        matching rule.  At most one finding per rule is returned for a given
        text value.
    """
    if not text or not text.strip():
        return []

    findings: list[InjectionFinding] = []
    for rule in _ALL_RULES:
        match = rule.pattern.search(text)
        if match is None:
            continue
        severity = rule.severity
        if in_player_context and severity == "error":
            severity = "warning"
        snippet = _make_snippet(text, match)
        findings.append(InjectionFinding(
            rule_id=rule.rule_id,
            severity=severity,
            file=file,
            pointer=pointer,
            message=(
                f"{rule.description}: found in {file} at '{pointer}': {snippet!r}"
            ),
            suggested_fix=rule.suggested_fix,
            matched_snippet=snippet,
        ))
    return findings


# ---------------------------------------------------------------------------
# Field extractors — one per file type
# Each returns ``list[tuple[str, str, bool]]``: (text, pointer, in_player_context)
# ---------------------------------------------------------------------------


def _walk_dict(
    data: object,
    pointer: str,
    results: list[tuple[str, str, bool]],
    *,
    player_context: bool,
) -> None:
    """Recursively harvest all string leaves from a nested YAML structure."""
    if isinstance(data, str):
        results.append((data, pointer, player_context))
    elif isinstance(data, dict):
        for key, val in data.items():
            _walk_dict(val, f"{pointer}/{key}", results, player_context=player_context)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _walk_dict(item, f"{pointer}/{i}", results, player_context=player_context)


def _scenario_texts(data: dict) -> list[tuple[str, str, bool]]:
    results: list[tuple[str, str, bool]] = []
    for field in ("title", "summary"):
        val = data.get(field)
        if isinstance(val, str):
            results.append((val, f"/{field}", False))
    player_role = data.get("player_role")
    if isinstance(player_role, dict):
        for field in ("label", "brief"):
            val = player_role.get(field)
            if isinstance(val, str):
                results.append((val, f"/player_role/{field}", False))
    opening = data.get("opening")
    if isinstance(opening, dict):
        val = opening.get("npc_says")
        if isinstance(val, str):
            results.append((val, "/opening/npc_says", False))
    goals = data.get("goals")
    if isinstance(goals, dict):
        for section in ("player_visible", "hidden"):
            items = goals.get(section, [])
            if isinstance(items, list):
                for i, item in enumerate(items):
                    if isinstance(item, str):
                        results.append((item, f"/goals/{section}/{i}", False))
    return results


def _npc_texts(data: dict) -> list[tuple[str, str, bool]]:
    results: list[tuple[str, str, bool]] = []
    for field in ("display_name",):
        val = data.get(field)
        if isinstance(val, str):
            results.append((val, f"/{field}", False))
    public = data.get("public_persona")
    if isinstance(public, dict):
        for field in ("occupation", "speaking_style", "demeanor", "background", "description"):
            val = public.get(field)
            if isinstance(val, str):
                results.append((val, f"/public_persona/{field}", False))
    private = data.get("private_persona")
    if private is not None:
        _walk_dict(private, "/private_persona", results, player_context=False)
    return results


def _rubric_texts(data: dict) -> list[tuple[str, str, bool]]:
    results: list[tuple[str, str, bool]] = []
    val = data.get("title")
    if isinstance(val, str):
        results.append((val, "/title", False))
    for i, dim in enumerate(data.get("dimensions", [])):
        if not isinstance(dim, dict):
            continue
        for field in ("name", "description"):
            val = dim.get(field)
            if isinstance(val, str):
                results.append((val, f"/dimensions/{i}/{field}", False))
        scoring = dim.get("scoring")
        if isinstance(scoring, dict):
            for level, text in scoring.items():
                if isinstance(text, str):
                    results.append((text, f"/dimensions/{i}/scoring/{level}", False))
    return results


def _safety_texts(data: dict) -> list[tuple[str, str, bool]]:
    results: list[tuple[str, str, bool]] = []
    val = data.get("redirect_message")
    if isinstance(val, str):
        results.append((val, "/redirect_message", False))
    return results


def _test_fixture_texts(data: dict) -> list[tuple[str, str, bool]]:
    """Extract texts from a pack-test fixture YAML.

    ``player_input`` turns are marked ``in_player_context=True``: the prompt
    builder already labels such text as untrusted, so error-severity findings
    are downgraded to warnings.  This allows packs that exercise
    injection-detection to include example attack prompts in fixture inputs.
    """
    results: list[tuple[str, str, bool]] = []
    desc = data.get("description")
    if isinstance(desc, str):
        results.append((desc, "/description", False))
    for i, turn in enumerate(data.get("turns", [])):
        if not isinstance(turn, dict):
            continue
        player_input = turn.get("player_input")
        if isinstance(player_input, str):
            results.append((player_input, f"/turns/{i}/player_input", True))
    return results


# ---------------------------------------------------------------------------
# Pack-level scanner
# ---------------------------------------------------------------------------


def _rel(pack_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(pack_dir))
    except ValueError:
        return str(path)


def _load_yaml_safe(path: Path) -> Optional[dict]:
    """Load a YAML file, returning None on any error (parse errors are the
    validator's responsibility — the scanner skips unreadable files)."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _scan_yaml_file(
    path: Path,
    pack_dir: Path,
    extractor: Callable[[dict], list[tuple[str, str, bool]]],
    findings: list[InjectionFinding],
) -> None:
    """Load a YAML file, apply the extractor, and append scanner findings."""
    data = _load_yaml_safe(path)
    if data is None:
        return
    rel = _rel(pack_dir, path)
    for text, pointer, in_player_context in extractor(data):
        findings.extend(scan_text(text, rel, pointer, in_player_context=in_player_context))


def _resolve_safety_path(pack_dir: Path) -> Optional[Path]:
    """Return the resolved safety policy YAML path, or None if not found."""
    for manifest_name in ("manifest.yaml", "pack.json"):
        manifest_path = pack_dir / manifest_name
        if not manifest_path.exists():
            continue
        try:
            if manifest_name.endswith(".yaml"):
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            else:
                import json
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            safety = raw.get("safety") or {}
            policy_str = safety.get("policy", "") if isinstance(safety, dict) else ""
            if not policy_str:
                return None
            candidate = (pack_dir / policy_str).resolve()
            candidate.relative_to(pack_dir)  # path-traversal guard
            return candidate if candidate.is_file() else None
        except Exception:
            return None
    return None


def scan_pack_dir(pack_dir: Path) -> list[InjectionFinding]:
    """Scan all natural-language text fields in a pack directory.

    Scans the following locations:
    - ``scenarios/*.yaml`` — scenario titles, summaries, player role briefs,
      opening NPC lines, and player/hidden goal strings.
    - ``npcs/*.yaml`` — NPC display names, public persona descriptions, and all
      private persona string fields.
    - ``rubrics/*.yaml`` — rubric titles, dimension names/descriptions, and
      scoring level text.
    - Safety policy file (resolved from manifest) — redirect message.
    - ``README.md`` — full document text (findings capped at WARNING severity).
    - ``tests/*.yaml`` — fixture descriptions and player_input turns (player
      context: error findings downgraded to warnings).

    No network requests are made.  All scanning is local and read-only.

    Returns:
        A list of :class:`InjectionFinding` objects ordered by file path.
        May be empty if no patterns are detected.
    """
    pack_dir = pack_dir.resolve()
    findings: list[InjectionFinding] = []

    # Scenarios
    scenarios_dir = pack_dir / "scenarios"
    if scenarios_dir.is_dir():
        for path in sorted(scenarios_dir.glob("*.yaml")):
            _scan_yaml_file(path, pack_dir, _scenario_texts, findings)

    # NPCs
    npcs_dir = pack_dir / "npcs"
    if npcs_dir.is_dir():
        for path in sorted(npcs_dir.glob("*.yaml")):
            _scan_yaml_file(path, pack_dir, _npc_texts, findings)

    # Rubrics
    rubrics_dir = pack_dir / "rubrics"
    if rubrics_dir.is_dir():
        for path in sorted(rubrics_dir.glob("*.yaml")):
            _scan_yaml_file(path, pack_dir, _rubric_texts, findings)

    # Safety policy
    safety_path = _resolve_safety_path(pack_dir)
    if safety_path is not None:
        _scan_yaml_file(safety_path, pack_dir, _safety_texts, findings)

    # README (findings capped at warning — it's documentation, not runtime content)
    readme = pack_dir / "README.md"
    if readme.is_file():
        try:
            text = readme.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if text.strip():
            rel = _rel(pack_dir, readme)
            for finding in scan_text(text, rel, "(document)"):
                if finding.severity == "error":
                    finding = replace(finding, severity="warning")
                findings.append(finding)

    # Test fixtures (player_input turns are already in player context)
    tests_dir = pack_dir / "tests"
    if tests_dir.is_dir():
        for path in sorted(tests_dir.glob("*.yaml")):
            _scan_yaml_file(path, pack_dir, _test_fixture_texts, findings)

    return findings
