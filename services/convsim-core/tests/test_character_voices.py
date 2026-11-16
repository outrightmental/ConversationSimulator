# SPDX-License-Identifier: Apache-2.0
"""The official characters have their own voices, and their packs are voice-ready.

With voice installed, the conversation brief switches the character's voice on
by default for a scenario that is marked voice-ready, and selects the voice the
pack cast for that character. Before this, no official pack declared voice
support, so the brief showed "designed for text" and left voice off.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.tts.voices import APPROVED_VOICES

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"
_VOICE_READY_PACKS = {
    "job-interview-basic",
    "difficult-conversations",
    "everyday-negotiation",
    "dating-confidence-boundaries",
    "language-cafe",
}


def _npc_files() -> list[Path]:
    return sorted(_OFFICIAL_PACKS.glob("*/npcs/*.yaml"))


def _pronoun_counts(text: str) -> tuple[int, int, int]:
    words = re.findall(r"[a-z]+", text.lower())
    she = sum(w in ("she", "her", "hers", "herself") for w in words)
    he = sum(w in ("he", "him", "his", "himself") for w in words)
    they = sum(w in ("they", "them", "their", "themself", "themselves") for w in words)
    return she, he, they


@pytest.mark.parametrize("npc_file", _npc_files(), ids=lambda p: f"{p.parent.parent.name}/{p.stem}")
def test_a_cast_voice_is_approved_and_fits_the_character(npc_file: Path):
    data = yaml.safe_load(npc_file.read_text(encoding="utf-8"))
    voice = data.get("voice") or {}
    if voice.get("engine", "none") == "none":
        assert "voice_id" not in voice
        return
    assert voice["engine"] == "kokoro"
    info = APPROVED_VOICES[voice["voice_id"]]
    # Cast by the pronouns the pack text itself uses for the character. A
    # character written as "they" is left uncast for the pack author to decide.
    she, he, _they = _pronoun_counts(npc_file.read_text(encoding="utf-8"))
    assert she != he, f"{npc_file.name} is cast, but its text does not settle she or he"
    assert info.gender == ("female" if she > he else "male"), npc_file.name


def test_voice_ready_packs_declare_it_and_the_tutorial_does_not():
    for manifest in sorted(_OFFICIAL_PACKS.glob("*/manifest.yaml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        declared = (data.get("requirements") or {}).get("voice_support") is True
        assert declared == (manifest.parent.name in _VOICE_READY_PACKS), manifest.parent.name


@pytest.fixture()
def official_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        exports_dir=str(tmp_path / "exports"),
        cache_dir=str(tmp_path / "cache"),
        crash_bundles_dir=str(tmp_path / "crashes"),
        models_dir=str(tmp_path / "models" / "llm"),
        official_packs_dir=str(_OFFICIAL_PACKS),
    )
    with TestClient(create_app(config)) as client:
        yield client


@pytest.mark.parametrize(
    "scenario_id, voice_id",
    [
        ("behavioral_interview", "af_heart"),      # Dana Reyes
        ("used_car_negotiation", "am_michael"),    # Ray Kowalski
        ("ask_for_raise", "af_nicole"),            # Diane Kowalczyk
        ("spanish_coffee", "af_heart"),            # Rosa Garcia
        ("the_ask", None),                         # Jordan Chen: written as "they", not cast
    ],
)
def test_the_brief_learns_the_scenario_is_voice_ready_and_who_speaks(
    official_client, scenario_id, voice_id
):
    response = official_client.get(f"/api/scenarios/{scenario_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["voice_supported"] is True
    assert body["npc_voice_id"] == voice_id


def test_the_scripted_tutorial_stays_text_only(official_client):
    body = official_client.get("/api/scenarios/first_words_tutorial").json()
    assert body["voice_supported"] is False
    assert body["npc_voice_id"] is None
