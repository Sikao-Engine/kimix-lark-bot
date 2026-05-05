# -*- coding: utf-8 -*-
# @file self_update.py
# @brief Self-update confirmation handler
# @author sailing-innocent
# @date 2026-04-25
# @version 2.0
# ---------------------------------
"""Handler for self-update confirmation button clicks."""

import logging
import threading
import time
from typing import Any

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)

from kimix_lark_bot.handlers.base import BaseHandler, HandlerContext
from kimix_lark_bot.feishu_card_kit.renderer import CardRenderer
from kimix_lark_bot.self_update_orchestrator import SelfUpdateOrchestrator

logger = logging.getLogger(__name__)


class ConfirmSelfUpdateHandler(BaseHandler):
    """Handle self-update confirmation."""

    def handle(self, value: dict, chat_id: str) -> Any:
        """Handle self-update confirmation."""
        reason = value.get("reason", "用户确认更新")

        # Extract message_id from event context for updating the original card later
        # Note: message_id is captured from the card action event
        # We need to pass it through so the restarted bot can update the card
        # However, the message_id from card action is the *original* message that contains the card
        # After restart, we can only send a new message (cannot update old card without message_id)
        # So we save chat_id and reason; the restarted bot will send a new completion card

        # Save pending update context BEFORE starting the update
        # so that even if the process exits immediately, the context is persisted
        SelfUpdateOrchestrator.save_pending_update(
            chat_id=chat_id,
            reason=reason,
        )

        # Start self-update in background
        def do_self_update():
            try:
                # Give a moment for the save to complete and card response to return
                time.sleep(0.5)

                result = self.ctx.request_self_update(reason=reason)

                if result.get("success"):
                    success_card = CardRenderer.result(
                        "✅ 更新已启动",
                        f"{result.get('message', '')}\n\n即将退出并由 watcher 重启。",
                        success=True,
                    )
                    self.ctx.messaging.send_card(chat_id, success_card)
                else:
                    # Clear pending update on failure
                    SelfUpdateOrchestrator.load_and_clear_pending_update()
                    error_card = CardRenderer.error(
                        "❌ 更新失败",
                        result.get("message", "Unknown error"),
                    )
                    self.ctx.messaging.send_card(chat_id, error_card)
            except Exception as exc:
                logger.error("[SelfUpdate] Error: %s", exc, exc_info=True)
                # Clear pending update on exception
                SelfUpdateOrchestrator.load_and_clear_pending_update()

        threading.Thread(target=do_self_update, daemon=True).start()

        # Return immediate response
        return P2CardActionTriggerResponse(
            {
                "toast": {
                    "type": "info",
                    "content": "正在启动更新...",
                    "i18n": {
                        "zh_cn": "正在启动更新...",
                        "en_us": "Starting update...",
                    },
                }
            }
        )
