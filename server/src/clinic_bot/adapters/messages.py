"""JSON-file message catalog."""

from __future__ import annotations

import json
from pathlib import Path


class JsonMessageCatalog:
    def __init__(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a JSON object")
        self._messages: dict[str, str] = {str(k): str(v) for k, v in data.items()}

    def get(self, key: str, **params: str) -> str:
        """Raises KeyError for an unknown key so a missing string fails loudly in tests."""
        template = self._messages[key]
        return template.format(**params) if params else template
