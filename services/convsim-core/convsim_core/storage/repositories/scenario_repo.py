# SPDX-License-Identifier: Apache-2.0
"""Database queries for the scenario library: listing, filtering, FTS, and detail."""
import json
import sqlite3
from pathlib import Path
from typing import Optional

import yaml

from convsim_core.packs.models import PlayerRoleInfo, ScenarioCard, ScenarioDetail

_SCENARIO_COLS = """
    s.slug          AS scenario_id,
    p.slug          AS pack_id,
    p.name          AS pack_name,
    COALESCE(s.title, s.name)  AS title,
    s.summary,
    p.tags_json,
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


def _row_to_card(row: sqlite3.Row) -> ScenarioCard:
    tags = json.loads(row["tags_json"] or "[]")
    return ScenarioCard(
        scenario_id=row["scenario_id"],
        pack_id=row["pack_id"],
        pack_name=row["pack_name"],
        title=row["title"] or row["scenario_id"],
        summary=row["summary"],
        tags=tags,
        content_rating=row["content_rating"],
        difficulty_default=row["difficulty_default"],
        max_turns=row["max_turns"],
        estimated_length_minutes=row["soft_time_limit_minutes"],
        voice_support=bool(row["voice_support"]),
        model_recommendation=row["model_recommendation"],
    )


def _row_to_detail(row: sqlite3.Row, *, include_hidden: bool) -> ScenarioDetail:
    tags = json.loads(row["tags_json"] or "[]")
    yaml_data = _load_scenario_yaml(row["pack_source_path"], row["rel_path"])

    player_role: Optional[PlayerRoleInfo] = None
    pr_raw = yaml_data.get("player_role")
    if isinstance(pr_raw, dict):
        player_role = PlayerRoleInfo(
            label=pr_raw.get("label", ""),
            brief=pr_raw.get("brief"),
        )

    opening_npc_says: Optional[str] = None
    opening = yaml_data.get("opening")
    if isinstance(opening, dict):
        opening_npc_says = opening.get("npc_says")

    goals = yaml_data.get("goals") or {}
    player_visible_goals: list[str] = goals.get("player_visible") or []
    hidden_goals: Optional[list[str]] = goals.get("hidden") if include_hidden else None

    difficulty_raw = yaml_data.get("difficulty") or {}
    difficulty_options: dict = difficulty_raw.get("options") or {}

    return ScenarioDetail(
        scenario_id=row["scenario_id"],
        pack_id=row["pack_id"],
        pack_name=row["pack_name"],
        title=row["title"] or row["scenario_id"],
        summary=row["summary"],
        tags=tags,
        content_rating=row["content_rating"],
        difficulty_default=row["difficulty_default"],
        difficulty_options=difficulty_options,
        max_turns=row["max_turns"],
        estimated_length_minutes=row["soft_time_limit_minutes"],
        voice_support=bool(row["voice_support"]),
        model_recommendation=row["model_recommendation"],
        player_role=player_role,
        opening_npc_says=opening_npc_says,
        player_visible_goals=player_visible_goals,
        hidden_goals=hidden_goals,
    )


def _load_scenario_yaml(pack_source_path: Optional[str], rel_path: Optional[str]) -> dict:
    """Load scenario YAML from disk. Returns {} if path is unavailable or parse fails."""
    if not pack_source_path or not rel_path:
        return {}
    try:
        path = Path(pack_source_path) / rel_path
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}
