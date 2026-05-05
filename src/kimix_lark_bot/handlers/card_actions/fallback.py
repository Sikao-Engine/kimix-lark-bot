# -*- coding: utf-8 -*-
# @file fallback.py
# @brief Fallback action handler
# @author sailing-innocent
# @date 2026-04-25
# @version 2.0
# ---------------------------------
"""Handler for routing unrecognised card actions to background execution."""

import threading
from typing import Any, Optional

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)

from kimix_lark_bot.handlers.base import BaseHandler, HandlerContext
from kimix_lark_bot.context import ActionPlan


class FallbackActionHandler(BaseHandler):
    """Route action to background thread for execution."""

    def handle(
        self, action_type: str, path: Optional[str], chat_id: str, message_id: str
    ) -> Any:
        """Route action to background thread for execution."""
        ctx = self.ctx.get_or_create_context(chat_id)
        plan = ActionPlan(action=action_type, params={"path": path} if path else {})

        # Execute in background thread
        threading.Thread(
            target=self._execute_plan_background,
            args=(plan, chat_id, message_id, ctx),
            daemon=True,
        ).start()

        # Return success response to Feishu (required!)
        return P2CardActionTriggerResponse(
            {
                "toast": {
                    "type": "info",
                    "content": "处理中...",
                    "i18n": {"zh_cn": "处理中...", "en_us": "Processing..."},
                }
            }
        )

    def _execute_plan_background(
        self, plan: ActionPlan, chat_id: str, message_id: str, ctx: Any
    ) -> None:
        """Execute plan in background (placeholder for agent integration)."""
        # This method should be overridden or the agent should handle this
        # For now, just log that the action was received
        print(f"[FallbackActionHandler] Background execution: {plan.action}")
