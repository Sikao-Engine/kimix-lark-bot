# -*- coding: utf-8 -*-
# @file card_action.py
# @brief Card action handler — compatibility re-export
# @author sailing-innocent
# @date 2026-04-25
# @version 2.0
# ---------------------------------
"""Backward-compatible re-export of CardActionDispatcher as CardActionHandler.

The monolithic implementation has been split into the ``card_actions`` sub-package
following the dependency-injection pattern.  Import from there for new code.
"""

from kimix_lark_bot.handlers.card_actions.dispatcher import CardActionDispatcher

# Backward-compatible alias
CardActionHandler = CardActionDispatcher

__all__ = ["CardActionHandler"]
