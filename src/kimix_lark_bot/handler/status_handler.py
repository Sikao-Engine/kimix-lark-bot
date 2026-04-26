# -*- coding: utf-8 -*-
"""Status handler."""

import logging

from kimix_lark_bot.context import ActionPlan, ConversationContext
from kimix_lark_bot.card_renderer import status_card

from .base import BaseHandler

logger = logging.getLogger(__name__)


class StatusHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        procs = self.ctx.process_mgr.list_processes()
        card = status_card(procs, active_workspace=ctx.active_workspace)
        self.ctx.messaging.reply_card(message_id, card)
        ctx.push("bot", "显示状态")
