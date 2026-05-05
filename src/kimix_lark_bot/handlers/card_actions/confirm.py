# -*- coding: utf-8 -*-
# @file confirm.py
# @brief Confirm action handler
# @author sailing-innocent
# @date 2026-04-25
# @version 2.0
# ---------------------------------
"""Handler for confirmation button clicks (confirm / cancel)."""

import threading
import traceback
from typing import Any

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)

from kimix_lark_bot.handlers.base import BaseHandler, HandlerContext
from kimix_lark_bot.context import ActionPlan
from kimix_lark_bot.feishu_card_kit.renderer import CardRenderer
from kimix_lark_bot.handlers.plan_executor import PlanExecutor


class ConfirmActionHandler(BaseHandler):
    """Handle confirmation button clicks (confirm or cancel)."""

    def __init__(self, ctx: HandlerContext, executor: PlanExecutor | None = None):
        super().__init__(ctx)
        self._executor = executor

    def handle(self, value: dict, chat_id: str, message_id: str) -> Any:
        """Handle confirmation button clicks.

        Args:
            value: The action value dict containing pending_id and decision
            chat_id: The chat ID
            message_id: The message ID for updating the card

        Returns:
            P2CardActionTriggerResponse to acknowledge the action

        Note:
            Must return response within 3 seconds to avoid "invalid confirmation" error.
            All card updates and action execution are done in background threads.
        """
        pending_id = value.get("pending_id") if isinstance(value, dict) else None
        decision = value.get("decision") if isinstance(value, dict) else None

        if not pending_id:
            return P2CardActionTriggerResponse(
                {
                    "toast": {
                        "type": "error",
                        "content": "无效的操作确认",
                        "i18n": {
                            "zh_cn": "无效的操作确认",
                            "en_us": "Invalid confirmation",
                        },
                    }
                }
            )

        # Get the pending action from ConfirmationManager
        pending = self.ctx.confirm_mgr.consume(pending_id)

        if not pending:
            # Pending action not found or expired - update card in background
            def show_expired():
                error_card = CardRenderer.result(
                    "操作已过期",
                    "该确认请求已过期或已被处理，请重新发起操作。",
                    success=False,
                )
                self.ctx.messaging.update_card(message_id, error_card)

            threading.Thread(target=show_expired, daemon=True).start()

            return P2CardActionTriggerResponse(
                {
                    "toast": {
                        "type": "error",
                        "content": "确认已过期，请重新发起",
                        "i18n": {
                            "zh_cn": "确认已过期，请重新发起",
                            "en_us": "Confirmation expired, please retry",
                        },
                    }
                }
            )

        if decision == "cancel":
            # User cancelled the action - update card and clear context in background
            def do_cancel():
                cancel_card = CardRenderer.result(
                    "已取消",
                    f"操作「{pending.summary}」已取消。",
                    success=True,
                )
                self.ctx.messaging.update_card(message_id, cancel_card)

                # Clear pending from conversation context
                ctx = self.ctx.get_or_create_context(chat_id)
                if ctx.pending and ctx.pending.summary == pending.summary:
                    ctx.clear_pending()
                    self.ctx.save_contexts()

            threading.Thread(target=do_cancel, daemon=True).start()

            return P2CardActionTriggerResponse(
                {
                    "toast": {
                        "type": "info",
                        "content": "操作已取消",
                        "i18n": {
                            "zh_cn": "操作已取消",
                            "en_us": "Operation cancelled",
                        },
                    }
                }
            )

        # decision == "confirm" or default - execute the action
        # IMPORTANT: Update card and execute action in background to meet 3s response time
        def execute_confirmed_action():
            try:
                # Update card to show processing state
                processing_card = CardRenderer.progress(
                    title="正在执行",
                    description=f"正在执行「{pending.summary}」...",
                )
                self.ctx.messaging.update_card(message_id, processing_card)

                # Create a plan from the pending action
                plan = ActionPlan(
                    action=pending.action,
                    params=pending.params,
                )

                # Get or create conversation context
                conv_ctx = self.ctx.get_or_create_context(chat_id)

                # Execute the plan using PlanExecutor
                executor = self._executor or PlanExecutor(self.ctx)
                executor.execute(plan, chat_id, message_id, conv_ctx)

                # Update card with result (executor will handle this)
                print(
                    f"[ConfirmActionHandler] Confirmed action completed: {pending.action}"
                )

            except Exception as exc:
                print(f"[ConfirmActionHandler] Error executing confirmed action: {exc}")
                traceback.print_exc()
                error_card = CardRenderer.result(
                    "执行失败",
                    f"执行「{pending.summary}」时出错：{str(exc)}",
                    success=False,
                )
                self.ctx.messaging.update_card(message_id, error_card)

        threading.Thread(target=execute_confirmed_action, daemon=True).start()

        return P2CardActionTriggerResponse(
            {
                "toast": {
                    "type": "info",
                    "content": "正在执行操作...",
                    "i18n": {
                        "zh_cn": "正在执行操作...",
                        "en_us": "Executing operation...",
                    },
                }
            }
        )
