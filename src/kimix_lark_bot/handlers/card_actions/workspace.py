# -*- coding: utf-8 -*-
# @file workspace.py
# @brief Workspace button action handler
# @author sailing-innocent
# @date 2026-04-25
# @version 2.0
# ---------------------------------
"""Handler for workspace dashboard button clicks."""

import threading
import traceback
from typing import Any, Optional

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)

from kimix_lark_bot.handlers.base import BaseHandler, HandlerContext
from kimix_lark_bot.feishu_card_kit.renderer import CardRenderer
from kimix_lark_bot.context import ConversationContext
from kimix_lark_bot.handlers.workspace_handlers import (
    WorkspaceDashboardHandler,
    StartWorkspaceHandler,
    StopWorkspaceHandler,
    SwitchWorkspaceHandler,
)


class WorkspaceButtonHandler(BaseHandler):
    """Handle workspace dashboard button clicks.

    These actions are processed in background threads to meet the 3s
    response requirement for card actions.
    """

    def __init__(
        self,
        ctx: HandlerContext,
        *,
        dashboard: Optional[WorkspaceDashboardHandler] = None,
        start: Optional[StartWorkspaceHandler] = None,
        stop: Optional[StopWorkspaceHandler] = None,
        switch: Optional[SwitchWorkspaceHandler] = None,
    ):
        super().__init__(ctx)
        self._dashboard = dashboard or WorkspaceDashboardHandler(ctx)
        self._start = start or StartWorkspaceHandler(ctx)
        self._stop = stop or StopWorkspaceHandler(ctx)
        self._switch = switch or SwitchWorkspaceHandler(ctx)

    def handle(
        self, action_type: str, value: dict, chat_id: str, message_id: str
    ) -> Any:
        """Handle workspace dashboard button clicks."""
        path = value.get("path") if isinstance(value, dict) else None
        ctx = self.ctx.get_or_create_context(chat_id)

        def execute() -> None:
            try:
                if action_type == "btn_show_dashboard":
                    self._dashboard.handle(chat_id, message_id)

                elif action_type == "btn_refresh_dashboard":
                    self._dashboard.refresh(chat_id, message_id, ctx)

                elif action_type == "btn_start_workspace":
                    if path:
                        self._start.handle(chat_id, message_id, ctx, path=path)
                    else:
                        self.ctx.messaging.reply_text(message_id, "❌ 未指定工作区路径")

                elif action_type == "btn_stop_workspace":
                    if path:
                        self._stop.handle(chat_id, message_id, ctx, path=path)
                    else:
                        # Stop all
                        self._stop.handle(chat_id, message_id, ctx)

                elif action_type == "btn_stop_all":
                    self._stop.handle(chat_id, message_id, ctx)

                elif action_type == "btn_switch_workspace":
                    if path:
                        self._switch.handle(chat_id, message_id, ctx, path=path)
                    else:
                        self.ctx.messaging.reply_text(message_id, "❌ 未指定工作区路径")

            except Exception as exc:
                print(f"[WorkspaceButtonHandler] Workspace button error: {exc}")
                traceback.print_exc()
                error_card = CardRenderer.error(
                    "操作失败", f"执行操作时出错: {str(exc)}"
                )
                self.ctx.messaging.update_card(message_id, error_card)

        threading.Thread(target=execute, daemon=True).start()

        # Return immediate toast response
        toast_messages = {
            "btn_start_workspace": "正在启动工作区...",
            "btn_stop_workspace": "正在停止工作区...",
            "btn_switch_workspace": "正在切换工作区...",
            "btn_show_dashboard": "正在打开面板...",
            "btn_refresh_dashboard": "正在刷新...",
            "btn_stop_all": "正在停止全部工作区...",
        }

        return P2CardActionTriggerResponse(
            {
                "toast": {
                    "type": "info",
                    "content": toast_messages.get(action_type, "处理中..."),
                    "i18n": {
                        "zh_cn": toast_messages.get(action_type, "处理中..."),
                        "en_us": "Processing...",
                    },
                }
            }
        )
