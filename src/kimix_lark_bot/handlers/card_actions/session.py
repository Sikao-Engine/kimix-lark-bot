# -*- coding: utf-8 -*-
# @file session.py
# @brief Session action handlers
# @author sailing-innocent
# @date 2026-04-25
# @version 2.0
# ---------------------------------
"""Handlers for clear_session and new_session button clicks."""

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)

from kimix_lark_bot.handlers.base import BaseHandler, HandlerContext
from kimix_lark_bot.feishu_card_kit.renderer import CardRenderer
from kimix_lark_bot.opencode.client import OpenCodeAsyncClient

logger = logging.getLogger(__name__)


class ClearSessionHandler(BaseHandler):
    """Handle clear session button click."""

    def handle(self, value: dict, chat_id: str, message_id: str) -> Any:
        """Handle clear session button click."""
        session_id = value.get("session_id") if isinstance(value, dict) else None
        port = value.get("port") if isinstance(value, dict) else None

        if not session_id or not port:
            return P2CardActionTriggerResponse(
                {
                    "toast": {
                        "type": "error",
                        "content": "缺少会话信息",
                        "i18n": {
                            "zh_cn": "缺少会话信息",
                            "en_us": "Missing session info",
                        },
                    }
                }
            )

        def do_clear():
            async def _clear():
                client = OpenCodeAsyncClient(port=port)
                try:
                    ok = await client.clear_session(session_id)
                    return ok
                finally:
                    await client.close()

            try:
                ok = asyncio.run(_clear())
                if ok:
                    card = CardRenderer.result(
                        "已清空",
                        "当前对话的 context 已清空，可以继续提问。",
                        success=True,
                    )
                else:
                    card = CardRenderer.error(
                        "清空失败",
                        "后端返回失败，请稍后重试。",
                    )
            except Exception as exc:
                logger.error("[ClearSessionHandler] clear_session error: %s", exc, exc_info=True)
                card = CardRenderer.error(
                    "清空失败",
                    f"调用后端出错: {exc}",
                )
            self.ctx.messaging.update_card(message_id, card)

        threading.Thread(target=do_clear, daemon=True).start()

        return P2CardActionTriggerResponse(
            {
                "toast": {
                    "type": "info",
                    "content": "正在清空对话...",
                    "i18n": {
                        "zh_cn": "正在清空对话...",
                        "en_us": "Clearing session...",
                    },
                }
            }
        )


class NewSessionHandler(BaseHandler):
    """Handle new session button click."""

    def handle(self, value: dict, chat_id: str, message_id: str) -> Any:
        """Handle new session button click."""
        port = value.get("port") if isinstance(value, dict) else None
        path = value.get("path") if isinstance(value, dict) else None

        if not port or not path:
            return P2CardActionTriggerResponse(
                {
                    "toast": {
                        "type": "error",
                        "content": "缺少会话信息",
                        "i18n": {
                            "zh_cn": "缺少会话信息",
                            "en_us": "Missing session info",
                        },
                    }
                }
            )

        def do_new():
            async def _new():
                client = OpenCodeAsyncClient(port=port)
                try:
                    sess = await client.create_session(
                        title=f"SailZen - {Path(path).name}"
                    )
                    return sess.id if sess else None
                finally:
                    await client.close()

            try:
                new_sess_id = asyncio.run(_new())
                if new_sess_id:
                    # Update process manager session id
                    self.ctx.process_mgr.set_session_id(path, new_sess_id)
                    card = CardRenderer.result(
                        "新对话已创建",
                        f"新 session ID: `{new_sess_id[:16]}...`\n可以直接发送新任务。",
                        success=True,
                    )
                else:
                    card = CardRenderer.error(
                        "创建失败",
                        "后端未返回 session ID。",
                    )
            except Exception as exc:
                logger.error("[NewSessionHandler] new_session error: %s", exc, exc_info=True)
                card = CardRenderer.error(
                    "创建失败",
                    f"调用后端出错: {exc}",
                )
            self.ctx.messaging.update_card(message_id, card)

        threading.Thread(target=do_new, daemon=True).start()

        return P2CardActionTriggerResponse(
            {
                "toast": {
                    "type": "info",
                    "content": "正在创建新对话...",
                    "i18n": {
                        "zh_cn": "正在创建新对话...",
                        "en_us": "Creating new session...",
                    },
                }
            }
        )
