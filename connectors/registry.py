from __future__ import annotations
from typing import Dict

from connectors.base import Connector


_REGISTRY: Dict[str, Connector] = {}


def register(name: str):
    """Decorator to register a connector implementation by name."""
    def _wrap(cls):
        instance = cls()
        _REGISTRY[name] = instance
        return cls

    return _wrap


def get_connector(name: str) -> Connector:
    if name not in _REGISTRY:
        raise KeyError(f"Connector '{name}' is not registered")
    return _REGISTRY[name]


def list_connectors() -> list[str]:
    return sorted(_REGISTRY.keys())
