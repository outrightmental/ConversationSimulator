# SPDX-License-Identifier: Apache-2.0
"""Database queries for the scenario library: listing, filtering, FTS, and detail."""
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

import yaml

from convsim_core.packs.models import (
    DifficultyConfigInfo,
    DurationInfo,
    PlayerRoleInfo,
    ScenarioCard,
    ScenarioDetail,
)

_SCENARIO_COLS = """
    s.slug          AS scenario_id,
    p.slug          AS pack_id,
    p.name          AS pack_name,
    COALESCE(s.title, s.name)  AS title,
    s.summary,
    p.tags_json,
    p.supported_languages_json,
    COALESCE(s.content_rating, p.content_rating) AS content_rating,
    s.difficulty_default,
    s.max_turns,
    s.soft_time_limit_minutes,
    s.voice_support,
    s.model_recommendation,
    s.rel_path,
    p.source_path   AS pack_source_path
"""

_BASE_QUERY = f"""
    SELECT {_SCENARIO_COLS}
    FROM scenarios s
    JOIN packs p ON s.pack_id = p.id
"""


def _fts_query(q: str) -> str:
    """Convert user search text to a safe FTS5 query with prefix matching."""
    words = [w.replace('"', "").strip() for w in q.split() if w.strip()]
    words = [w for w in words if w]  # drop words that became empty after stripping quotes
    if not words:
        return ""
    return " ".join(f'"{w}"*' for w in words)


def list_scenarios(
    conn: sqlite3.Connection,
    *,
    q: Optional[str] = None,
    pack: Optional[str] = None,
    tag: Optional[str] = None,
    language: Optional[str] = None,
    content_rating: Optional[str] = None,
    difficulty: Optional[str] = None,
    voice_support: Optional[bool] = None,
) -> list[ScenarioCard]:
    """Return scenario cards, optionally filtered and/or FTS-searched."""
    clauses: list[str] = []
    params: list = []

    if q:
        fts = _fts_query(q)
        if fts:
            clauses.append(
                "(s.id IN (SELECT rowid FROM scenario_fts WHERE scenario_fts MATCH ?))"
            )
            params.append(fts)

    if pack:
        clauses.append("p.slug = ?")
        params.append(pack)

    if tag:
        clauses.append(
            "p.tags_json IS NOT NULL AND"
            " EXISTS(SELECT 1 FROM json_each(p.tags_json) jt WHERE jt.value = ?)"
        )
        params.append(tag)

    if language:
        clauses.append(
            "p.supported_languages_json IS NOT NULL AND"
            " EXISTS(SELECT 1 FROM json_each(p.supported_languages_json) jl WHERE jl.value = ?)"
        )
        params.append(language)

    if content_rating:
        clauses.append("COALESCE(s.content_rating, p.content_rating) = ?")
        params.append(content_rating)

    if difficulty:
        clauses.append("s.difficulty_default = ?")
        params.append(difficulty)

    if voice_support is not None:
        clauses.append("s.voice_support = ?")
        params.append(1 if voice_support else 0)

    sql = _BASE_QUERY
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY title"

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_card(row) for row in rows]


def get_scenario_by_id(
    conn: sqlite3.Connection,
    scenario_id: str,
    *,
    include_hidden: bool = False,
) -> Optional[ScenarioDetail]:
    """Return full scenario detail for a given scenario slug, or None if not found.

    Hidden agenda (goals.hidden) is excluded unless include_hidden is True.
    """
    row = conn.execute(
        _BASE_QUERY + " WHERE s.slug = ? LIMIT 1",
        (scenario_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_detail(row, include_hidden=include_hidden)


def _canonical_fields(row: sqlite3.Row, yaml_data: dict) -> dict:
    """Build the canonical ScenarioInfo fields the frontend contract requires.

    The web app (packages/shared/src/types/scenario.ts) iterates
    ``supported_languages`` and ``difficulty.options`` and dereferences
    ``player_role.label`` without guards, so every field returned here must be
    present and well-typed even when the scenario YAML is missing, partial, or
    unparseable — a scenario row must never be able to blank the library.
    """
    # player_role — always an object with a string label.
    pr_raw = yaml_data.get("player_role")
    if isinstance(pr_raw, dict):
        player_role = PlayerRoleInfo(
            label=str(pr_raw.get("label") or ""),
            brief=pr_raw.get("brief") or "",
        )
    else:
        player_role = PlayerRoleInfo(label="", brief="")

    # difficulty — default + options, YAML first, DB column fallback.
    difficulty_raw = yaml_data.get("difficulty")
    difficulty_raw = difficulty_raw if isinstance(difficulty_raw, dict) else {}
    options = difficulty_raw.get("options")
    options = options if isinstance(options, dict) else {}
    default = (
        difficulty_raw.get("default")
        or row["difficulty_default"]
        or (next(iter(options)) if options else "standard")
    )
    difficulty = DifficultyConfigInfo(default=str(default), options=options)

    # supported_languages — scenario YAML override → pack manifest → ["en"].
    langs = yaml_data.get("supported_languages")
    if not (isinstance(langs, list) and langs):
        try:
            langs = json.loads(row["supported_languages_json"] or "[]")
        except (TypeError, ValueError):
            langs = []
    if not (isinstance(langs, list) and langs):
        langs = ["en"]
    supported_languages = [str(lang) for lang in langs]

    # duration — YAML block with DB column fallback.
    duration_raw = yaml_data.get("duration")
    duration_raw = duration_raw if isinstance(duration_raw, dict) else {}
    max_turns = duration_raw.get("max_turns") or row["max_turns"]
    soft_limit = duration_raw.get("soft_time_limit_minutes") or row["soft_time_limit_minutes"]
    duration = DurationInfo(max_turns=max_turns, soft_time_limit_minutes=soft_limit)

    # state_meters_permitted — true when any state variable is player-visible.
    state_raw = yaml_data.get("state")
    variables = (state_raw or {}).get("variables") if isinstance(state_raw, dict) else None
    state_meters_permitted = False
    if isinstance(variables, dict):
        for spec in variables.values():
            if isinstance(spec, dict) and str(
                spec.get("visibility", spec.get("visible", ""))
            ).lower() in ("visible", "true"):
                state_meters_permitted = True
                break
    if isinstance(state_raw, dict) and state_raw.get("visible_to_player"):
        state_meters_permitted = True

    # estimated_length_label — human label derived from duration.
    if soft_limit:
        estimated_length_label = f"~{soft_limit} min"
    elif max_turns:
        estimated_length_label = f"~{max_turns} turns"
    else:
        estimated_length_label = "Varies"

    # safety_summary — content-rating line; scenario YAML may refine it later.
    rating = row["content_rating"] or "G"
    safety_summary = f"Rated {rating}. Conversations stay on this device."

    recommended = row["model_recommendation"]
    recommended_model = [recommended] if recommended else []

    taught = yaml_data.get("taught_dimensions")
    tested = yaml_data.get("tested_dimensions")
    ladder = yaml_data.get("ladder_position")

    return {
        "player_role": player_role,
        "difficulty": difficulty,
        "supported_languages": supported_languages,
        "duration": duration,
        "state_meters_permitted": state_meters_permitted,
        "voice_supported": bool(row["voice_support"]),
        "safety_summary": safety_summary,
        "estimated_length_label": estimated_length_label,
        "recommended_model": recommended_model,
        "ladder_position": str(ladder) if ladder else None,
        "taught_dimensions": taught if isinstance(taught, list) else [],
        "tested_dimensions": tested if isinstance(tested, list) else [],
    }


def _row_to_card(row: sqlite3.Row) -> ScenarioCard:
    tags = json.loads(row["tags_json"] or "[]")
    yaml_data = _load_scenario_yaml(row["pack_source_path"], row["rel_path"])
    return ScenarioCard(
        scenario_id=row["scenario_id"],
        pack_id=row["pack_id"],
        pack_name=row["pack_name"],
        title=row["title"] or row["scenario_id"],
        summary=row["summary"] or "",
        tags=tags,
        content_rating=row["content_rating"],
        difficulty_default=row["difficulty_default"],
        max_turns=row["max_turns"],
        estimated_length_minutes=row["soft_time_limit_minutes"],
        voice_support=bool(row["voice_support"]),
        model_recommendation=row["model_recommendation"],
        **_canonical_fields(row, yaml_data),
    )


def _row_to_detail(row: sqlite3.Row, *, include_hidden: bool) -> ScenarioDetail:
    tags = json.loads(row["tags_json"] or "[]")
    yaml_data = _load_scenario_yaml(row["pack_source_path"], row["rel_path"])

    opening_npc_says: Optional[str] = None
    opening = yaml_data.get("opening")
    if isinstance(opening, dict):
        opening_npc_says = opening.get("npc_says")

    goals = yaml_data.get("goals") or {}
    player_visible_goals: list[str] = goals.get("player_visible") or []
    hidden_goals: Optional[list[str]] = goals.get("hidden") if include_hidden else None

    difficulty_raw = yaml_data.get("difficulty") or {}
    difficulty_options: dict = difficulty_raw.get("options") or {}
    if not difficulty_options:
        difficulty_options = {"standard": {}}
    difficulty_default_str = str(
        difficulty_raw.get("default")
        or row["difficulty_default"]
        or next(iter(difficulty_options))
    )
    difficulty_nested = {"default": difficulty_default_str, "options": difficulty_options}

    langs_raw = yaml_data.get("supported_languages")
    supported_languages = (
        [str(l) for l in langs_raw]
        if isinstance(langs_raw, list) and langs_raw
        else ["en"]
    )

    return ScenarioDetail(
        scenario_id=row["scenario_id"],
        pack_id=row["pack_id"],
        pack_name=row["pack_name"],
        title=row["title"] or row["scenario_id"],
        summary=row["summary"] or "",
        tags=tags,
        content_rating=row["content_rating"],
        difficulty_default=row["difficulty_default"],
        difficulty_options=difficulty_options,
        difficulty=difficulty_nested,
        supported_languages=supported_languages,
        max_turns=row["max_turns"],
        estimated_length_minutes=row["soft_time_limit_minutes"],
        voice_support=bool(row["voice_support"]),
        model_recommendation=row["model_recommendation"],
        opening_npc_says=opening_npc_says,
        player_visible_goals=player_visible_goals,
        hidden_goals=hidden_goals,
        **_canonical_fields(row, yaml_data),
    )


# mtime-keyed cache so the list endpoint (which now loads YAML per scenario to
# build the canonical contract fields) stays O(stat) per request instead of
# O(read+parse). Bounded by the number of installed scenarios.
_YAML_CACHE: dict[str, tuple[float, dict]] = {}


def _load_scenario_yaml(pack_source_path: Optional[str], rel_path: Optional[str]) -> dict:
    """Load scenario YAML from disk. Returns {} if path is unavailable or parse fails."""
    if not pack_source_path or not rel_path:
        return {}
    try:
        base = Path(pack_source_path).resolve()
        path = (base / rel_path).resolve()
        path.relative_to(base)  # raises ValueError if outside pack directory
        key = str(path)
        mtime = os.path.getmtime(path)
        cached = _YAML_CACHE.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        data = raw if isinstance(raw, dict) else {}
        _YAML_CACHE[key] = (mtime, data)
        return data
    except Exception:
        return {}
