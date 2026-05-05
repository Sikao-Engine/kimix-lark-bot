# -*- coding: utf-8 -*-
# @file dispatcher.py
# @brief Card action dispatcher
# @author sailing-innocent
# @date 2026-04-25
# @version 2.0
# ---------------------------------
"""Dispatcher for interactive card button clicks.

Injects specific handlers via constructor so each action type is processed
by a standalone, testable unit.
"""

import json
import traceback
from typing import Optional, Any

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)

from kimix_lark_bot.handlers.base import BaseHandler, HandlerContext
from kimix_lark_bot.handlers.card_actions.confirm import ConfirmActionHandler
from kimix_lark_bot.handlers.card_actions.cancel_task import CancelTaskHandler
from kimix_lark_bot.handlers.card_actions.self_update import ConfirmSelfUpdateHandler
from kimix_lark_bot.handlers.card_actions.session import ClearSessionHandler, NewSessionHandler
from kimix_lark_bot.handlers.card_actions.workspace import WorkspaceButtonHandler
from kimix_lark_bot.handlers.card_actions.fallback import FallbackActionHandler


class CardActionDispatcher(BaseHandler):
    """Dispatches card action (button click) events to specific handlers.

    Responsibilities:
    - Parse card action events
    - Route to the appropriate injected handler
    """

    def __init__(
        self,
        ctx: HandlerContext,
        *,
        confirm: Optional[ConfirmActionHandler] = None,
        cancel_task: Optional[CancelTaskHandler] = None,
        self_update: Optional[ConfirmSelfUpdateHandler] = None,
        clear_session: Optional[ClearSessionHandler] = None,
        new_session: Optional[NewSessionHandler] = None,
        workspace: Optional[WorkspaceButtonHandler] = None,
        fallback: Optional[FallbackActionHandler] = None,
    ):
        super().__init__(ctx)
        self._confirm = confirm or ConfirmActionHandler(ctx)
        self._cancel_task = cancel_task or CancelTaskHandler(ctx)
        self._self_update = self_update or ConfirmSelfUpdateHandler(ctx)
        self._clear_session = clear_session or ClearSessionHandler(ctx)
        self._new_session = new_session or NewSessionHandler(ctx)
        self._workspace = workspace or WorkspaceButtonHandler(ctx)
        self._fallback = fallback or FallbackActionHandler(ctx)

    def handle(self, data: Any) -> Optional[Any]:
        """Handle a card button click action.

        Args:
            data: The P2CardActionTrigger event data

        Returns:
            P2CardActionTriggerResponse to acknowledge the action, or None
        """
        try:
            if not data or not data.event or not data.event.action:
                return None

            action = data.event.action
            value = action.value if hasattr(action, "value") else {}

            # value could be a dict or string
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = {}

            action_type = value.get("action") if isinstance(value, dict) else None
            path = value.get("path") if isinstance(value, dict) else None

            # Get context info
            event_context = (
                data.event.context if hasattr(data.event, "context") else None
            )
            chat_id = event_context.open_chat_id if event_context else None
            message_id = event_context.open_message_id if event_context else None

            if not chat_id or not action_type:
                print("[CardActionDispatcher] Missing chat_id or action_type")
                return None

            print(f"[CardActionDispatcher] {action_type} for {path} in {chat_id}")

            # Route to specific handler
            if action_type == "confirm_action":
                return self._confirm.handle(value, chat_id, message_id)

            if action_type == "cancel_task":
                return self._cancel_task.handle(value, chat_id)

            if action_type == "confirm_self_update":
                return self._self_update.handle(value, chat_id)

            if action_type == "clear_session":
                return self._clear_session.handle(value, chat_id, message_id)

            if action_type == "new_session":
                return self._new_session.handle(value, chat_id, message_id)

            if action_type in (
                "btn_start_workspace",
                "btn_stop_workspace",
                "btn_switch_workspace",
                "btn_show_dashboard",
                "btn_refresh_dashboard",
                "btn_stop_all",
            ):
                return self._workspace.handle(action_type, value, chat_id, message_id)

            # Fallback
            return self._fallback.handle(action_type, path, chat_id, message_id)

        except Exception as exc:
            print(f"[CardActionDispatcher] Error: {exc}")
            traceback.print_exc()
            return None
