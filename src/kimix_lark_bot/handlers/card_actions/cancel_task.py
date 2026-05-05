# -*- coding: utf-8 -*-
# @file cancel_task.py
# @brief Cancel task action handler
# @author sailing-innocent
# @date 2026-04-25
# @version 2.0
# ---------------------------------
"""Handler for task cancellation requests."""

import logging
from typing import Any

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)

from kimix_lark_bot.handlers.base import BaseHandler, HandlerContext

logger = logging.getLogger(__name__)


class CancelTaskHandler(BaseHandler):
    """Handle task cancellation request.

    Cancellation flow:
    1. Extract task_id from button value
    2. Call op_tracker.cancel(task_id) which:
       a. Sets op.cancelled = True
       b. Invokes the registered cancel callback (SessionRunner.cancel)
    3. SessionRunner.cancel() sets _cancel_event, causing the SSE loop to exit
    4. TaskHandler detects was_cancelled and updates card to "已取消"
    5. TaskHandler calls op_tracker.finish() to clean up
    """

    def handle(self, value: dict, chat_id: str) -> Any:
        """Handle task cancellation request."""
        task_id = (
            value.get("task_id") or value.get("op_id")
            if isinstance(value, dict)
            else None
        )

        if not task_id:
            return P2CardActionTriggerResponse(
                {
                    "toast": {
                        "type": "error",
                        "content": "取消失败：缺少任务 ID",
                        "i18n": {
                            "zh_cn": "取消失败：缺少任务 ID",
                            "en_us": "Cancel failed: missing task ID",
                        },
                    }
                }
            )

        logger.info("[CancelTaskHandler] Cancel request for task: %s", task_id)
        cancelled = self.ctx.op_tracker.cancel(task_id)

        if cancelled:
            return P2CardActionTriggerResponse(
                {
                    "toast": {
                        "type": "info",
                        "content": "正在取消任务...",
                        "i18n": {
                            "zh_cn": "正在取消任务...",
                            "en_us": "Cancelling task...",
                        },
                    }
                }
            )

        # Operation not found — it may have already completed or been cancelled
        return P2CardActionTriggerResponse(
            {
                "toast": {
                    "type": "warning",
                    "content": "任务可能已完成或已取消",
                    "i18n": {
                        "zh_cn": "任务可能已完成或已取消",
                        "en_us": "Task may have already finished or been cancelled",
                    },
                }
            }
        )
