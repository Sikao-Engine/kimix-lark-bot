# -*- coding: utf-8 -*-
# @file registry.py
# @brief Central command registry for bot capabilities
# @date 2026-04-26
# ---------------------------------
"""Central command registry.

Provides CommandRegistry as a singleton that holds metadata for every bot
command.  This enables:
- Brain to build keyword maps dynamically instead of hard-coding.
- PlanExecutor to build action mappings dynamically.
- HelpHandler / WelcomeHandler to generate cards automatically from the
  same source of truth.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type, Any


@dataclass
class CommandEntry:
    """Metadata for a single bot command.

    All fields are optional except ``action``; fill in what your consumer
    needs (brain, executor, help renderer, etc.).
    """

    action: str
    # --- Matching ---------------------------------------------------------
    exact_keywords: List[str] = field(default_factory=list)
    fuzzy_keywords: List[str] = field(default_factory=list)
    # --- Help rendering ---------------------------------------------------
    title: str = ""
    description: str = ""
    examples: List[str] = field(default_factory=list)
    category: str = "通用"
    format_hint: str = ""          # e.g. "启动 <项目>"
    # --- Execution metadata -----------------------------------------------
    confirm_required: bool = False
    confirm_summary_template: str = ""
    log_msg: str = "执行完成"
    hidden: bool = False           # hide from help / welcome cards
    # --- Handler wiring (optional) ----------------------------------------
    handler_class: Optional[Type] = None


class CommandRegistry:
    """Singleton registry holding every CommandEntry by action name."""

    _instance: Optional["CommandRegistry"] = None

    def __new__(cls) -> "CommandRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._entries: Dict[str, CommandEntry] = {}
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, entry: CommandEntry) -> None:
        """Register or overwrite a command entry."""
        self._entries[entry.action] = entry

    def get(self, action: str) -> Optional[CommandEntry]:
        """Fetch a single entry by action name."""
        return self._entries.get(action)

    def list_all(self) -> List[CommandEntry]:
        """Return all registered entries."""
        return list(self._entries.values())

    def list_visible(self) -> List[CommandEntry]:
        """Return entries that should appear in help / welcome cards."""
        return [e for e in self._entries.values() if not e.hidden]

    # ------------------------------------------------------------------
    # Brain helpers
    # ------------------------------------------------------------------

    def build_exact_keyword_map(self) -> Dict[str, str]:
        """Return {lowercase_keyword: action} for exact matching."""
        result: Dict[str, str] = {}
        for entry in self._entries.values():
            for kw in entry.exact_keywords:
                result[kw.lower()] = entry.action
        return result

    def build_fuzzy_keyword_map(self) -> Dict[str, str]:
        """Return {lowercase_keyword: action} for fuzzy (contains) matching."""
        result: Dict[str, str] = {}
        for entry in self._entries.values():
            for kw in entry.fuzzy_keywords:
                result[kw.lower()] = entry.action
        return result

    def get_by_keyword(self, keyword: str) -> Optional[CommandEntry]:
        """Look up an entry by an exact keyword (case-insensitive)."""
        keyword = keyword.lower()
        for entry in self._entries.values():
            if keyword in [k.lower() for k in entry.exact_keywords]:
                return entry
        return None
