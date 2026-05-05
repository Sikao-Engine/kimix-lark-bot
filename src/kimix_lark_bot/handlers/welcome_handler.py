# -*- coding: utf-8 -*-
# @file welcome_handler.py
# @brief Welcome handler for new P2P chat users
# @author sailing-innocent
# @date 2026-04-06
# @version 2.0
# ---------------------------------
"""Welcome handler for bot_p2p_chat_entered_v1 events.

This module handles the welcome flow when a user enters a P2P chat with the bot.

v2.0: quick_commands are assembled from CommandRegistry so they stay in sync
with the actual command set.
"""

from typing import Any, Dict
from pathlib import Path

from kimix_lark_bot.handlers.base import BaseHandler, HandlerContext
from kimix_lark_bot.feishu_card_kit.renderer import CardRenderer
from kimix_lark_bot.commands import get_registry


class WelcomeHandler(BaseHandler):
    """Handler for welcome messages when users enter P2P chat."""

    def handle(self, chat_id: str) -> None:
        """Send welcome card to the new chat.

        Args:
            chat_id: The chat ID of the P2P conversation
        """
        try:
            print(f"[WelcomeHandler] Sending welcome card to {chat_id}")

            # Collect session states from process manager
            session_states: Dict[str, str] = {}
            proc_map = {p.path: p for p in self.ctx.process_mgr.list_processes()}
            for proj in self.ctx.config.projects:
                path = proj.get("path", "")
                if path:
                    try:
                        resolved_path = str(Path(path).expanduser().resolve())
                    except Exception:
                        resolved_path = path

                    proc = proc_map.get(resolved_path)
                    if proc:
                        session_states[path] = proc.status.value
                    else:
                        session_states[path] = "idle"

            # Build feature status list
            features: list[tuple[str, str]] = []

            # Build quick commands from registry
            registry = get_registry()
            quick_commands: list[str] = []
            for entry in registry.list_visible():
                kw = ""
                if entry.exact_keywords:
                    kw = entry.exact_keywords[0]
                elif entry.fuzzy_keywords:
                    kw = entry.fuzzy_keywords[0]
                if kw:
                    quick_commands.append(f"• {kw} - {entry.description}")

            # Generate welcome card
            registry = get_registry()
            help_entry = registry.get("show_help")
            help_kw = help_entry.exact_keywords[0] if help_entry and help_entry.exact_keywords else "帮助"
            welcome_card = CardRenderer.welcome(
                projects=self.ctx.config.projects,
                session_states=session_states,
                features=features,
                quick_commands=quick_commands,
                footer=f'请回复"{help_kw}"来获取更多的信息',
            )

            # Send welcome card
            self.ctx.messaging.send_card(chat_id, welcome_card)
            print(f"[WelcomeHandler] Welcome card sent to {chat_id}")

        except Exception as exc:
            print(f"[WelcomeHandler] Error sending welcome card: {exc}")
            import traceback

            traceback.print_exc()
