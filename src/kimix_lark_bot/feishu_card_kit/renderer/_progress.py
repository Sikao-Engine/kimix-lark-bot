# -*- coding: utf-8 -*-
# @file _progress.py
# @brief Progress / task card renderers
# ---------------------------------
"""Card templates for progress indication and task tracking."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from kimix_lark_bot.feishu_card_kit.core import (
    CardColor,
    ButtonStyle,
    divider,
    text,
    note,
    button,
    action_row,
    card,
)

from ._constants import _SPINNER_CHARS


class ProgressRenderer:
    """Static card templates for progress and task feedback."""

    # ------------------------------------------------------------------
    # Progress / Task cards
    # ------------------------------------------------------------------

    @staticmethod
    def progress(
        title: str,
        description: str = "",
        progress_pct: Optional[int] = None,
        elapsed_seconds: Optional[float] = None,
        spinner_tick: int = 0,
        show_cancel_button: bool = False,
        cancel_action_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a progress indicator card.

        Args:
            title: Progress title
            description: Optional description text
            progress_pct: Optional percentage (0-100)
            elapsed_seconds: Optional elapsed time
            spinner_tick: Spinner animation frame index
            show_cancel_button: Whether to show cancel button
            cancel_action_data: Callback data for cancel button
        """
        spinner = _SPINNER_CHARS[spinner_tick % len(_SPINNER_CHARS)]

        elements: List[Dict[str, Any]] = []
        if description:
            elements.append(text(description))

        if progress_pct is not None:
            filled = progress_pct // 10
            bar = "█" * filled + "░" * (10 - filled)
            elements.append(text(f"{bar}  {progress_pct}%"))
        else:
            elements.append(text(f"{spinner} 处理中，请稍候..."))

        if elapsed_seconds is not None:
            elements.append(note(f"已用时 {int(elapsed_seconds)}s"))

        if show_cancel_button:
            elements.append(divider())
            if cancel_action_data:
                elements.append(
                    action_row(
                        [
                            button(
                                "❌ 取消任务",
                                "callback",
                                cancel_action_data,
                                ButtonStyle.DANGER,
                            )
                        ]
                    )
                )
            else:
                elements.append(note("💡 发送「取消」可中断当前任务"))

        return card(
            elements=elements,
            title=f"⏳ {title}",
            color=CardColor.BLUE,
        )

    @staticmethod
    def task_progress(
        title: str,
        task_text: str = "",
        tools: Optional[List[Dict[str, Any]]] = None,
        reasoning: str = "",
        elapsed_seconds: Optional[float] = None,
        spinner_tick: int = 0,
        show_cancel_button: bool = False,
        cancel_action_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a detailed task progress card with reasoning and tool calls.

        Args:
            title: Progress title
            task_text: Original task description
            tools: List of tool call dicts with keys: name, status, title, error
            reasoning: Current reasoning text (rolling sampled)
            elapsed_seconds: Optional elapsed time
            spinner_tick: Spinner animation frame index
            show_cancel_button: Whether to show cancel button
            cancel_action_data: Callback data for cancel button
        """
        spinner = _SPINNER_CHARS[spinner_tick % len(_SPINNER_CHARS)]
        _tool_icons = {
            "pending": "⏳",
            "running": "⚙️",
            "completed": "✅",
            "done": "✅",
            "error": "❌",
            "failed": "❌",
        }

        elements: List[Dict[str, Any]] = []

        if task_text:
            display_task = task_text[:120] + ("..." if len(task_text) > 120 else "")
            elements.append(text(f"📝 **任务:** {display_task}"))

        if reasoning:
            elements.append(divider())
            elements.append(text(f"{spinner} **思考中...**", bold=True))
            # Show last 300 chars of reasoning to keep card compact
            display_reasoning = reasoning[-300:]
            if len(reasoning) > 300:
                display_reasoning = "..." + display_reasoning
            elements.append(note(display_reasoning))

        if tools:
            elements.append(divider())
            total_tools = len(tools)
            elements.append(text(f"🔧 **工具调用** ({total_tools} 次)", bold=True))

            # Only show the most recent 10 calls to keep the card compact
            display_tools = tools[-10:]
            for tc in display_tools:
                name = tc.get("title") or tc.get("name", "unknown")
                status = tc.get("status", "unknown")
                icon = _tool_icons.get(status, "🔧")
                error = tc.get("error", "")
                call_id = tc.get("call_id", "")
                tool_input = tc.get("input", "")

                # Shorten call_id: strip 'tool_' prefix and keep first 6 hex chars
                short_id = call_id[5:11] if call_id.startswith("tool_") else call_id[:6]

                # Main line: icon + name
                main_line = f"{icon} {name}"
                if error:
                    main_line += f" ❌ {error[:40]}"
                elements.append(note(main_line))

                # Detail line in smaller text (grey tone via note)
                details: List[str] = []
                if short_id:
                    details.append(f"id: {short_id}")
                if tool_input:
                    inp = (
                        tool_input[:60] + "..." if len(tool_input) > 60 else tool_input
                    )
                    details.append(f"args: {inp}")
                if details:
                    elements.append(note(f"  ┗ {' | '.join(details)}"))

            if total_tools > 10:
                elements.append(note(f"... 还有 {total_tools - 10} 个较早的调用"))

        if elapsed_seconds is not None:
            elements.append(divider())
            elements.append(note(f"⏱️ 已用时 {int(elapsed_seconds)}s"))

        if show_cancel_button:
            elements.append(divider())
            if cancel_action_data:
                elements.append(
                    action_row(
                        [
                            button(
                                "❌ 取消任务",
                                "callback",
                                cancel_action_data,
                                ButtonStyle.DANGER,
                            )
                        ]
                    )
                )
            else:
                elements.append(note("💡 发送「取消」可中断当前任务"))

        return card(
            elements=elements,
            title=f"⏳ {title}",
            color=CardColor.BLUE,
        )

    @staticmethod
    def timeout_warning(
        operation: str,
        elapsed_seconds: float,
        context_path: str = "",
    ) -> Dict[str, Any]:
        """Create a timeout warning card.

        Args:
            operation: Operation name
            elapsed_seconds: Elapsed time in seconds
            context_path: Optional context path for cancel callback
        """
        elements = [
            text(f"操作「{operation}」比预期用时更长。"),
            text(f"已用时 {int(elapsed_seconds)}s，系统仍在工作中。"),
        ]
        buttons = [button("继续等待", "callback", {"action": "noop"})]
        if context_path:
            buttons.append(
                button(
                    "取消操作",
                    "callback",
                    {"action": "cancel_operation", "path": context_path},
                    ButtonStyle.DANGER,
                )
            )
        elements.append(divider())
        elements.append(action_row(buttons))

        return card(
            elements=elements,
            title="⏰ 操作超时警告",
            color=CardColor.YELLOW,
        )
