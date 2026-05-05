# -*- coding: utf-8 -*-
# @file _result.py
# @brief Result / error / paginated result card renderers
# ---------------------------------
"""Card templates for operation results, errors and paginated output."""

from __future__ import annotations

import time
from pathlib import Path
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

from ._deps import _status_verb


class ResultRenderer:
    """Static card templates for results, errors and paginated content."""

    # ------------------------------------------------------------------
    # Result / Error cards
    # ------------------------------------------------------------------

    @staticmethod
    def result(
        title: str,
        content: str,
        success: bool = True,
        can_retry: bool = False,
        retry_action: Optional[Dict[str, Any]] = None,
        can_undo: bool = False,
        undo_deadline: Optional[float] = None,
        context_path: str = "",
        max_content_length: int = 8000,
        context_usage: Optional[float] = None,
        session_actions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a result card.

        Args:
            title: Result title
            content: Result content text
            success: Whether the operation succeeded
            can_retry: Whether retry is available
            retry_action: Callback data for retry button
            can_undo: Whether undo is available
            undo_deadline: Unix timestamp for undo window
            context_path: Optional workspace path for context hints
            max_content_length: Maximum content length before truncation
            context_usage: Optional context usage ratio (0.0-1.0)
            session_actions: Optional dict with session_id, port, path for action buttons
        """
        color = CardColor.GREEN if success else CardColor.RED
        icon = "✅" if success else "❌"

        elements: List[Dict[str, Any]] = []
        if content:
            display = content[:max_content_length]
            if len(content) > max_content_length:
                display += (
                    f"\n\n[内容过长，共 {len(content)} 字符，"
                    f"已显示前 {max_content_length} 字符]"
                )
            elements.append(text(display))

        notes: List[str] = []
        if can_retry and retry_action:
            notes.append("💡 发送「重试」重新执行")
        if can_undo and undo_deadline:
            remaining = undo_deadline - time.time()
            if remaining > 0:
                notes.append(f"💡 发送「撤销」撤销此操作（{int(remaining)}秒内有效）")
        if context_path:
            notes.append(
                f"💡 发送「{_status_verb()} {Path(context_path).name}」查看详情"
            )

        if notes:
            elements.append(divider())
            for n in notes:
                elements.append(note(n))

        # Context usage bar + session action buttons
        if context_usage is not None or session_actions:
            elements.append(divider())

        if context_usage is not None:
            pct = min(max(context_usage, 0.0), 1.0) * 100
            filled = int(pct // 10)
            bar = "█" * filled + "░" * (10 - filled)
            color_hint = "🟢" if pct < 50 else "🟡" if pct < 80 else "🔴"
            elements.append(note(f"{color_hint} Context 容量: {bar} {pct:.1f}%"))

        if session_actions:
            buttons: List[Dict[str, Any]] = []
            sess_id = session_actions.get("session_id", "")
            port = session_actions.get("port", 0)
            path = session_actions.get("path", "")
            if sess_id:
                buttons.append(
                    button(
                        "🗑️ 清空对话",
                        "callback",
                        {
                            "action": "clear_session",
                            "session_id": sess_id,
                            "port": port,
                            "path": path,
                        },
                        ButtonStyle.DANGER,
                    )
                )
                buttons.append(
                    button(
                        "🆕 新建对话",
                        "callback",
                        {
                            "action": "new_session",
                            "port": port,
                            "path": path,
                        },
                        ButtonStyle.PRIMARY,
                    )
                )
            if buttons:
                elements.append(action_row(buttons))

        return card(
            elements=elements,
            title=f"{icon} {title}",
            color=color,
        )

    @staticmethod
    def error(
        title: str,
        error_message: str,
        context_path: str = "",
        can_retry: bool = True,
        retry_action: Optional[Dict[str, Any]] = None,
        max_content_length: int = 8000,
    ) -> Dict[str, Any]:
        """Create an error card.

        Args:
            title: Error title
            error_message: Error description
            context_path: Optional workspace path
            can_retry: Whether retry is available
            retry_action: Callback data for retry
            max_content_length: Maximum content length
        """
        elements: List[Dict[str, Any]] = [text(error_message[:max_content_length])]

        notes: List[str] = []
        if can_retry and retry_action:
            notes.append("💡 发送「重试」重新执行")
        if context_path:
            notes.append(
                f"💡 发送「{_status_verb()} {Path(context_path).name}」查看详情"
            )

        if notes:
            elements.append(divider())
            for n in notes:
                elements.append(note(n))

        return card(
            elements=elements,
            title=f"❌ {title}",
            color=CardColor.RED,
        )

    @staticmethod
    def result_paginated(
        title: str,
        content: str,
        page: int = 1,
        total_pages: int = 1,
        success: bool = True,
        context_usage: Optional[float] = None,
        session_actions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a paginated result card for very long content.

        Args:
            title: Card title
            content: Content for this page
            page: Current page number (1-indexed)
            total_pages: Total number of pages
            success: Whether the operation succeeded
            context_usage: Optional context usage ratio (0.0-1.0)
            session_actions: Optional dict with session_id, port, path for action buttons
        """
        color = CardColor.GREEN if success else CardColor.RED
        icon = "✅" if success else "❌"
        elements: List[Dict[str, Any]] = []

        if content:
            elements.append(text(content))

        if total_pages > 1:
            elements.append(divider())
            page_info = f"📄 第 {page}/{total_pages} 页"
            if page < total_pages:
                page_info += " | 发送「下一页」查看更多"
            elements.append(note(page_info))

        # Context usage bar + session action buttons
        if context_usage is not None or session_actions:
            elements.append(divider())

        if context_usage is not None:
            pct = min(max(context_usage, 0.0), 1.0) * 100
            filled = int(pct // 10)
            bar = "█" * filled + "░" * (10 - filled)
            color_hint = "🟢" if pct < 50 else "🟡" if pct < 80 else "🔴"
            elements.append(note(f"{color_hint} Context 容量: {bar} {pct:.1f}%"))

        if session_actions:
            buttons: List[Dict[str, Any]] = []
            sess_id = session_actions.get("session_id", "")
            port = session_actions.get("port", 0)
            path = session_actions.get("path", "")
            if sess_id:
                buttons.append(
                    button(
                        "🗑️ 清空对话",
                        "callback",
                        {
                            "action": "clear_session",
                            "session_id": sess_id,
                            "port": port,
                            "path": path,
                        },
                        ButtonStyle.DANGER,
                    )
                )
                buttons.append(
                    button(
                        "🆕 新建对话",
                        "callback",
                        {
                            "action": "new_session",
                            "port": port,
                            "path": path,
                        },
                        ButtonStyle.PRIMARY,
                    )
                )
            if buttons:
                elements.append(action_row(buttons))

        return card(
            elements=elements,
            title=f"{icon} {title} ({page}/{total_pages})",
            color=color,
        )
