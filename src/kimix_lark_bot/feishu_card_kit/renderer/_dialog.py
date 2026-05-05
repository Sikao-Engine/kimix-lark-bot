# -*- coding: utf-8 -*-
# @file _dialog.py
# @brief Confirmation / dialog card renderers
# ---------------------------------
"""Card templates for confirmation dialogs and interactive prompts."""

from __future__ import annotations

from typing import Any, Dict, List

from kimix_lark_bot.feishu_card_kit.core import (
    CardColor,
    ButtonStyle,
    divider,
    text,
    note,
    field_row,
    button,
    action_row,
    card,
)


class DialogRenderer:
    """Static card templates for confirmation and dialog interactions."""

    # ------------------------------------------------------------------
    # Confirmation / Dialog cards
    # ------------------------------------------------------------------

    @staticmethod
    def confirmation(
        action_summary: str,
        action_detail: str = "",
        risk_level: str = "confirm_required",
        can_undo: bool = False,
        pending_id: str = "",
        timeout_minutes: int = 5,
    ) -> Dict[str, Any]:
        """Create a confirmation dialog card.

        Args:
            action_summary: Short summary of the action
            action_detail: Detailed description
            risk_level: "safe", "guarded", or "confirm_required"
            can_undo: Whether the action can be undone
            pending_id: Unique ID for tracking this confirmation
            timeout_minutes: Confirmation timeout in minutes
        """
        risk_icons = {"safe": "🟢", "guarded": "🟡", "confirm_required": "🔴"}
        risk_labels = {
            "safe": "低风险",
            "guarded": "中等风险",
            "confirm_required": "高风险",
        }

        elements: List[Dict[str, Any]] = [text(action_summary, bold=True)]
        if action_detail:
            elements.append(text(action_detail))

        elements.append(divider())
        elements.append(
            field_row(
                [
                    (
                        "风险等级",
                        f"{risk_icons.get(risk_level, '🔴')} {risk_labels.get(risk_level, '需确认')}",
                    ),
                    ("有效期", f"{timeout_minutes} 分钟"),
                ]
            )
        )

        if can_undo:
            elements.append(note("此操作可在 30 秒内撤销"))

        elements.append(divider())

        button_style = (
            ButtonStyle.DANGER
            if risk_level == "confirm_required"
            else ButtonStyle.PRIMARY
        )
        elements.append(
            action_row(
                [
                    button(
                        "✅ 确认执行",
                        "callback",
                        {
                            "action": "confirm_action",
                            "pending_id": pending_id,
                            "decision": "confirm",
                        },
                        button_style,
                    ),
                    button(
                        "❌ 取消",
                        "callback",
                        {
                            "action": "confirm_action",
                            "pending_id": pending_id,
                            "decision": "cancel",
                        },
                        ButtonStyle.DEFAULT,
                    ),
                ]
            )
        )

        elements.append(note("💡 或回复文字：确认 / 取消"))

        return card(
            elements=elements,
            title="⚠️ 请确认操作",
            color=CardColor.YELLOW,
        )
