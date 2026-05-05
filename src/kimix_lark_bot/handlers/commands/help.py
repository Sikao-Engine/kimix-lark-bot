# -*- coding: utf-8 -*-
# @file help.py
# @brief Handler for help command
# @date 2026-04-26
# @version 2.0
# ---------------------------------
"""Handler for help command.

v2.0: Content is assembled dynamically from CommandRegistry so that any
new command automatically appears in the help card.
"""

from typing import List, Tuple

from kimix_lark_bot.handlers.base import BaseHandler
from kimix_lark_bot.feishu_card_kit.renderer import CardRenderer
from kimix_lark_bot.commands import get_registry


class HelpHandler(BaseHandler):
    """Handler for help command."""

    def handle(self, chat_id: str, message_id: str) -> None:
        """Send help information — dynamically synced from CommandRegistry."""
        print("Handling help command")
        registry = get_registry()

        commands: List[Tuple[str, str, str]] = []
        for entry in registry.list_visible():
            fmt = entry.format_hint or (entry.exact_keywords[0] if entry.exact_keywords else entry.title)
            desc = entry.description or entry.title
            example = entry.examples[0] if entry.examples else fmt
            commands.append((fmt, desc, example))

        help_card = CardRenderer.help(
            commands=commands,
            projects=self.ctx.config.projects,
        )
        self.ctx.messaging.reply_card(message_id, help_card, "help")
