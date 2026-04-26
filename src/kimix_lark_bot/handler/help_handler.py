# -*- coding: utf-8 -*-
"""Help handler."""

import logging

from kimix_lark_bot.context import ActionPlan, ConversationContext
from kimix_lark_bot.card_renderer import help_card

from .base import BaseHandler

logger = logging.getLogger(__name__)


class HelpHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        procs = self.ctx.process_mgr.list_processes()
        card = help_card(self.ctx.config.projects, procs)
        self.ctx.messaging.reply_card(message_id, card)
        ctx.push("bot", "显示帮助")
