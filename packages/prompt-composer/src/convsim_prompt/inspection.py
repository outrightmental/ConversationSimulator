"""Dev-only prompt inspection with optional per-layer redaction.

PromptInspector is disabled by default and must never be exposed through
player-facing APIs.  Enable it only in development environments.
"""
from __future__ import annotations

from typing import List, Optional

from .types import PromptBundle

_REDACTED_PLACEHOLDER = "[REDACTED BY INSPECTOR]"


class PromptInspector:
    """
    Structured inspection of a PromptBundle with optional layer redaction.

    Usage::

        inspector = PromptInspector(enabled=True)
        print(inspector.inspect(bundle, redact=["NPC_PRIVATE_PERSONA"]))

    Never pass ``enabled=True`` in production code paths or expose the output
    through any player-visible API endpoint.
    """

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def inspect(
        self,
        bundle: PromptBundle,
        redact: Optional[List[str]] = None,
    ) -> str:
        """
        Return a formatted inspection report.

        Args:
            bundle: The assembled prompt bundle to inspect.
            redact: Layer names whose content is replaced with a redaction
                    placeholder (e.g. ``["NPC_PRIVATE_PERSONA"]``).

        Raises:
            RuntimeError: When the inspector is disabled.
        """
        if not self._enabled:
            raise RuntimeError(
                "PromptInspector is disabled. "
                "Enable it only in development environments and never expose "
                "its output through player-facing APIs."
            )

        redact_set = set(redact or [])
        lines: List[str] = [
            "=== PROMPT INSPECTION REPORT ===",
            f"Estimated tokens: {bundle.estimated_token_count}",
            f"Was truncated:    {bundle.was_truncated}",
            "",
            "--- SYSTEM PROMPT (by layer) ---",
        ]

        for name, content in bundle.layer_map.items():
            if name == "PLAYER_UTTERANCE":
                continue
            section = _REDACTED_PLACEHOLDER if name in redact_set else content
            lines.append(f"\n[Layer: {name}]\n{section}")

        lines += [
            "",
            "--- USER PROMPT ---",
            bundle.user_prompt,
            "",
            "=== END INSPECTION REPORT ===",
        ]
        return "\n".join(lines)
