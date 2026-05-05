# -*- coding: utf-8 -*-
# @file __init__.py
# @brief Pre-built card templates for common Feishu bot scenarios
# @author sailing-innocent
# @date 2026-04-26
# @version 1.0
# ---------------------------------
"""Pre-built card templates for common Feishu bot scenarios.

Provides ready-to-use card templates for:
- Workspace / session management
- Progress indication
- Confirmation dialogs
- Result display
- Error handling
- Help / welcome screens

All templates are generic and can be used with any Feishu bot.
"""

from __future__ import annotations

from kimix_lark_bot.feishu_card_kit.renderer._workspace import WorkspaceRenderer
from kimix_lark_bot.feishu_card_kit.renderer._progress import ProgressRenderer
from kimix_lark_bot.feishu_card_kit.renderer._dialog import DialogRenderer
from kimix_lark_bot.feishu_card_kit.renderer._result import ResultRenderer
from kimix_lark_bot.feishu_card_kit.renderer._help import HelpRenderer

from kimix_lark_bot.feishu_card_kit.renderer._deps import (
    _status_verb,
    set_status_verb_resolver,
)


class CardRenderer(
    WorkspaceRenderer,
    ProgressRenderer,
    DialogRenderer,
    ResultRenderer,
    HelpRenderer,
):
    """Static card templates for common bot interaction patterns.

    All methods return Feishu card dicts. No external dependencies.
    """
    pass


__all__ = [
    "CardRenderer",
    "_status_verb",
    "set_status_verb_resolver",
]
