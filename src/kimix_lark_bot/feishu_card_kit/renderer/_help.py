# -*- coding: utf-8 -*-
# @file _help.py
# @brief Help / welcome card renderers
# ---------------------------------
"""Card templates for help screens and welcome messages."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from kimix_lark_bot.feishu_card_kit.core import (
    CardColor,
    divider,
    text,
    note,
    field_row,
    card,
    get_state_icon,
    get_state_label,
)


class HelpRenderer:
    """Static card templates for help and welcome screens."""

    # ------------------------------------------------------------------
    # Help / Welcome cards
    # ------------------------------------------------------------------

    @staticmethod
    def help(
        commands: Optional[List[tuple]] = None,
        projects: Optional[List[Dict[str, str]]] = None,
        features: Optional[List[tuple]] = None,
        footer: str = "",
    ) -> Dict[str, Any]:
        """Create a help card.

        Args:
            commands: List of (command, description, example) tuples
            projects: List of project dicts
            features: List of (name, status) tuples, e.g. [("LLM", "✅ 已启用")]
            footer: Optional footer note
        """
        elements: List[Dict[str, Any]] = []

        elements.append(text("🚀 **快速开始**", bold=True))
        elements.append(note("直接发送指令即可，支持自然语言"))

        if commands:
            elements.append(divider())
            elements.append(text("📋 **常用指令**", bold=True))
            for cmd, desc, example in commands:
                elements.append(text(f"• **{cmd}** - {desc}"))
                elements.append(note(f"  例：{example}"))

        if projects:
            elements.append(divider())
            elements.append(text("📁 **配置的项目**", bold=True))
            slugs = [p.get("slug", "") for p in projects if p.get("slug")]
            if slugs:
                elements.append(text(f"可用名称：{', '.join(slugs)}"))
            for proj in projects[:5]:
                slug = proj.get("slug", "")
                label = proj.get("label", slug)
                elements.append(note(f"• {label} ({slug})"))
            if len(projects) > 5:
                elements.append(note(f"... 还有 {len(projects) - 5} 个项目"))

        if features:
            elements.append(divider())
            elements.append(text("⚙️ **系统状态**", bold=True))
            elements.append(field_row(features))

        if footer:
            elements.append(divider())
            elements.append(note(footer))

        return card(
            elements=elements,
            title="🤖 使用帮助",
            color=CardColor.BLUE,
        )

    @staticmethod
    def welcome(
        title: str = "欢迎使用",
        description: str = "",
        quick_commands: Optional[List[str]] = None,
        projects: Optional[List[Dict[str, str]]] = None,
        session_states: Optional[Dict[str, str]] = None,
        features: Optional[List[tuple]] = None,
        footer: str = "",
    ) -> Dict[str, Any]:
        """Create a welcome card for new users.

        Args:
            title: Welcome title
            description: Welcome description
            quick_commands: List of quick command hint strings
            projects: List of project dicts
            session_states: Dict mapping paths to state strings
            features: List of (name, status) tuples
            footer: Footer note
        """
        session_states = session_states or {}
        elements: List[Dict[str, Any]] = []

        elements.append(text(f"👋 {title}", bold=True))
        if description:
            elements.append(note(description))

        if features:
            elements.append(divider())
            elements.append(text("⚙️ 系统状态", bold=True))
            elements.append(field_row(features))

        if quick_commands:
            elements.append(divider())
            elements.append(text("💡 快捷指令", bold=True))
            for cmd in quick_commands:
                elements.append(text(cmd))

        if projects:
            elements.append(divider())
            elements.append(text("📁 配置的项目", bold=True))
            for proj in projects[:5]:
                slug = proj.get("slug", "")
                label = proj.get("label", slug)
                path = proj.get("path", "")
                state = session_states.get(path, "idle")
                icon = get_state_icon(state)
                state_label = get_state_label(state)
                elements.append(text(f"{icon} **{label}** ({slug}) - {state_label}"))
            if len(projects) > 5:
                elements.append(note(f"... 还有 {len(projects) - 5} 个项目"))

        if footer:
            elements.append(divider())
            elements.append(note(footer))

        return card(
            elements=elements,
            title=f"🎉 {title}",
            color=CardColor.GREEN,
        )
