# -*- coding: utf-8 -*-
"""Message handler for incoming text messages."""

import json
import re
import logging
import traceback

import lark_oapi as lark

from kimix_lark_bot.context import ActionPlan, ConversationContext
from kimix_lark_bot.card_renderer import result, confirmation

from .base import BaseHandler, HandlerContext, _dedup, _executor
from .plan_executor import PlanExecutor

logger = logging.getLogger(__name__)


class MessageHandler(BaseHandler):
    def handle(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        try:
            if not data or not data.event or not data.event.message:
                logger.debug("Empty data or message, skipping")
                return
            message = data.event.message
            if message.message_type != "text":
                logger.debug("Ignoring non-text message: %s", message.message_type)
                return
            try:
                content = json.loads(message.content or "{}")
            except json.JSONDecodeError:
                logger.debug("Invalid JSON content, skipping")
                return

            text = content.get("text", "").strip()
            chat_id = message.chat_id
            message_id = message.message_id

            logger.debug("[Raw] chat_id=%s message_id=%s text=%r", chat_id, message_id, text)

            if _dedup.is_duplicate(message_id):
                logger.debug("Duplicate message %s, skipping", message_id)
                return
            if not text or not chat_id:
                logger.debug("Empty text or chat_id, skipping")
                return

            logger.info("[%s] User: %s", chat_id, text)
            _executor.submit(self._process_message, text, chat_id, message_id)
        except Exception as exc:
            logger.error("Message handler error: %s", exc, exc_info=True)
            traceback.print_exc()

    def _process_message(self, text: str, chat_id: str, message_id: str) -> None:
        text = re.sub(r"@_user_\S+", "", text).strip()
        text = re.sub(r"@\S+", "", text).strip()
        if not text:
            logger.debug("Empty text after filtering mentions, skipping")
            return

        ctx = self.ctx.get_or_create_context(chat_id)
        ctx.push("user", text)
        logger.debug("[%s] Context mode=%s workspace=%s", chat_id, ctx.mode, ctx.active_workspace)

        plan = self._dispatch_message(text, chat_id, message_id, ctx)
        logger.debug("[%s] Plan action=%s params=%s", chat_id, plan.action, plan.params)

        if plan.action not in ("noop", "chat", "clarify"):
            logger.info("[%s] Executing action=%s", chat_id, plan.action)
            executor = PlanExecutor(self.ctx)
            executor.execute(plan, chat_id, message_id, ctx)
        else:
            logger.debug("[%s] No action to execute (action=%s)", chat_id, plan.action)

    def _dispatch_message(self, text: str, chat_id: str, message_id: str, ctx: ConversationContext) -> ActionPlan:
        # Check for pending confirmation reply
        if ctx.pending:
            logger.debug("[%s] Has pending confirmation: %s", chat_id, ctx.pending.summary)
            decision = self.ctx.brain.check_confirmation_reply(text)
            if decision is True:
                logger.info("[%s] User confirmed pending action: %s", chat_id, ctx.pending.action)
                plan = ActionPlan(action=ctx.pending.action, params=ctx.pending.params)
                ctx.clear_pending()
                return plan
            elif decision is False:
                logger.info("[%s] User cancelled pending action", chat_id)
                ctx.clear_pending()
                self.ctx.messaging.reply_card(message_id, result("已取消", "操作已取消。", success=False))
                ctx.push("bot", "已取消")
                return ActionPlan(action="noop")
            else:
                logger.debug("[%s] Unrelated reply to pending, clearing", chat_id)
                ctx.clear_pending()
                self.ctx.messaging.reply_text(message_id, "确认已超时，请重新发起指令。")
                return ActionPlan(action="noop")

        plan = self.ctx.brain.think(text, ctx)
        logger.debug("[%s] Brain think result: action=%s confirm_required=%s", chat_id, plan.action, plan.confirm_required)

        if plan.action in ("chat", "clarify", "noop"):
            reply = plan.reply or "我不太确定你的意思，能再描述一下吗？"
            ctx.push("bot", reply[:200])
            self.ctx.messaging.reply_text(message_id, reply)
            return plan

        if plan.confirm_required:
            logger.info("[%s] Action requires confirmation: %s", chat_id, plan.confirm_summary)
            ctx.pending = self.ctx.brain.build_confirmation(
                plan.action, plan.params, plan.confirm_summary or plan.action, ctx
            )
            card = confirmation(
                action_summary=plan.confirm_summary or plan.action,
                pending_id=f"pending_{chat_id}",
            )
            self.ctx.messaging.reply_card(message_id, card)
            ctx.push("bot", "需要确认: " + (plan.confirm_summary or plan.action))
            return ActionPlan(action="noop")

        return plan
