"""Patient-facing fixed text, looked up by key."""

from __future__ import annotations

from typing import Protocol


class MessageCatalog(Protocol):
    def get(self, key: str, **params: str) -> str: ...
