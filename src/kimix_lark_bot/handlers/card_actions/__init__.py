# -*- coding: utf-8 -*-
# @file __init__.py
# @brief Card action handlers package
# @author sailing-innocent
# @date 2026-04-25
# @version 2.0
# ---------------------------------
"""Card action handlers — split by dependency-injection pattern.

Each handler is a standalone unit injected into the dispatcher.
"""

from kimix_lark_bot.handlers.card_actions.dispatcher import CardActionDispatcher
from kimix_lark_bot.handlers.card_actions.confirm import ConfirmActionHandler
from kimix_lark_bot.handlers.card_actions.cancel_task import CancelTaskHandler
from kimix_lark_bot.handlers.card_actions.self_update import ConfirmSelfUpdateHandler
from kimix_lark_bot.handlers.card_actions.session import ClearSessionHandler, NewSessionHandler
from kimix_lark_bot.handlers.card_actions.workspace import WorkspaceButtonHandler
from kimix_lark_bot.handlers.card_actions.fallback import FallbackActionHandler

__all__ = [
    "CardActionDispatcher",
    "ConfirmActionHandler",
    "CancelTaskHandler",
    "ConfirmSelfUpdateHandler",
    "ClearSessionHandler",
    "NewSessionHandler",
    "WorkspaceButtonHandler",
    "FallbackActionHandler",
]
