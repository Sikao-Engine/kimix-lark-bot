# -*- coding: utf-8 -*-
# @file _deps.py
# @brief Dependency injection hooks for renderers
# ---------------------------------
"""Dependency injection utilities for card renderers.

Allows external code to override default behaviour (e.g. resolving
command keywords) without hard-coding imports inside renderer modules.
"""

from __future__ import annotations

from typing import Callable, Optional

_StatusVerbResolver = Callable[[], str]

_status_verb_resolver: Optional[_StatusVerbResolver] = None


def set_status_verb_resolver(resolver: _StatusVerbResolver) -> None:
    """Inject a custom resolver for the primary status command verb.

    Example:
        set_status_verb_resolver(lambda: "状态")
    """
    global _status_verb_resolver
    _status_verb_resolver = resolver


def _status_verb() -> str:
    """Return the primary keyword for 'show_status' from CommandRegistry.

    Falls back to a hard-coded default if no resolver is injected.
    """
    if _status_verb_resolver is not None:
        return _status_verb_resolver()
    try:
        from kimix_lark_bot.commands import get_registry

        entry = get_registry().get("show_status")
        if entry and entry.exact_keywords:
            return entry.exact_keywords[0]
    except Exception:
        pass
    return "状态"
