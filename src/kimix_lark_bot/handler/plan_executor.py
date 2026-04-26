# -*- coding: utf-8 -*-
"""Plan executor that dispatches actions to specific handlers."""

import logging
from typing import Dict, Any

from kimix_lark_bot.context import ActionPlan, ConversationContext

from .base import BaseHandler, HandlerContext
from .help_handler import HelpHandler
from .status_handler import StatusHandler
from .workspace_handlers import StartWorkspaceHandler, StopWorkspaceHandler, SwitchWorkspaceHandler, ExitWorkspaceHandler
from .task_handler import TaskHandler

logger = logging.getLogger(__name__)


class PlanExecutor(BaseHandler):
    def __init__(self, ctx: HandlerContext):
        super().__init__(ctx)
        self._help = HelpHandler(ctx)
        self._status = StatusHandler(ctx)
        self._start = StartWorkspaceHandler(ctx)
        self._stop = StopWorkspaceHandler(ctx)
        self._switch = SwitchWorkspaceHandler(ctx)
        self._exit = ExitWorkspaceHandler(ctx)
        self._task = TaskHandler(ctx)

        self._registry: Dict[str, Any] = {
            "show_help": self._help.handle,
            "show_status": self._status.handle,
            "switch_workspace": self._switch.handle,
            "start_workspace": self._start.handle,
            "stop_workspace": self._stop.handle,
            "exit_workspace": self._exit.handle,
            "send_task": self._task.handle,
        }

    def execute(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        handler_fn = self._registry.get(plan.action)
        if handler_fn:
            logger.info("[%s] Executing handler for %s", chat_id, plan.action)
            handler_fn(plan, chat_id, message_id, ctx)
            ctx.push("bot", plan.action)
        else:
            logger.warning("[%s] Unknown action: %s", chat_id, plan.action)
            self.ctx.messaging.reply_text(message_id, f"未知动作: {plan.action}")
