"""Base classes and helpers for plugins."""
from __future__ import annotations

from typing import Any, Dict, List


class PluginError(Exception):
    pass


class PluginBase:
    """Base class for plugins.

    Plugins should subclass this and implement `capabilities`, `validate` and `execute`.
    """

    name: str = "base"
    version: str = "0.0"

    def capabilities(self) -> List[str]:
        """Return list of available actions (strings)."""
        return []

    def validate(self, action: str, payload: Dict[str, Any]) -> None:
        """Validate payload for given action. Raise PluginError on invalid."""
        return None

    async def execute(self, action: str, payload: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Execute action asynchronously. Return a dict with result info."""
        raise NotImplementedError()
