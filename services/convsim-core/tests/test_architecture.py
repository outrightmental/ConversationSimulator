# SPDX-License-Identifier: Apache-2.0
"""Architecture guard: scenario-engine code must not import concrete LLM drivers."""
import sys

import convsim_core  # noqa: F401 — loads the full package
import convsim_core.runtime  # noqa: F401 — registers built-in adapters


def test_convsim_core_does_not_import_llama_cpp():
    """Importing convsim_core must not pull llama_cpp into sys.modules."""
    leaked = [m for m in sys.modules if m == "llama_cpp" or m.startswith("llama_cpp.")]
    assert not leaked, f"llama_cpp was imported by convsim_core: {leaked}"


def test_convsim_core_does_not_import_ollama():
    """Importing convsim_core must not pull ollama into sys.modules."""
    leaked = [m for m in sys.modules if m == "ollama" or m.startswith("ollama.")]
    assert not leaked, f"ollama was imported by convsim_core: {leaked}"
