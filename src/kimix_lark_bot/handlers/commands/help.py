from pathlib import Path
from typing import Optional

from kimix_lark_bot.handlers.base import BaseHandler
from kimix_lark_bot.feishu_card_kit.renderer import CardRenderer


class HelpHandler(BaseHandler):
    """Handler for help command."""

    def handle(self, chat_id: str, message_id: str) -> None:
        """Send help information."""
        print("Handling help command")
        help_card = CardRenderer.help(
            commands=[
                ("启动 <项目>", "启动工作区", "启动 sz"),
                ("停止", "停止工作区", "停止 sz"),
            ],
            projects=self.ctx.config.projects,
        )
        self.ctx.messaging.reply_card(message_id, help_card, "help")
