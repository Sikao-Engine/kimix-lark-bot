# -*- coding: utf-8 -*-
# @file plan_executor.py
# @brief Plan execution coordinator
# @author sailing-innocent
# @date 2026-04-08
# @version 3.0
# ---------------------------------
"""Plan execution coordinator.

Routes ActionPlans to specific handlers via an action registry.
New actions only need to be registered in ``kimix_lark_bot.commands``;
the executor wiring is assembled dynamically from the registry.
"""

import logging
import threading
from typing import Optional, Callable, Dict

from kimix_lark_bot.handlers.base import BaseHandler, HandlerContext
from kimix_lark_bot.context import ActionPlan, ConversationContext
from kimix_lark_bot.feishu_card_kit.renderer import CardRenderer

logger = logging.getLogger(__name__)


class PlanExecutor(BaseHandler):
    """Executor for ActionPlans.

    Uses the central CommandRegistry to dispatch actions to handlers,
    so that adding a new command only requires updating the registry.
    """

    def __init__(self, ctx: HandlerContext):
        super().__init__(ctx)
        from kimix_lark_bot.handlers.commands.help import HelpHandler
        from kimix_lark_bot.handlers.commands.status import StatusHandler
        from kimix_lark_bot.handlers.workspace_handlers import (
            StartWorkspaceHandler,
            StopWorkspaceHandler,
            SwitchWorkspaceHandler,
            WorkspaceDashboardHandler,
        )
        from kimix_lark_bot.handlers.task_handler import TaskHandler
        from kimix_lark_bot.handlers.self_update_handler import SelfUpdateHandler
        from kimix_lark_bot.commands import get_registry

        self._help = HelpHandler(ctx)
        self._status = StatusHandler(ctx)
        self._dashboard = WorkspaceDashboardHandler(ctx)
        self._start = StartWorkspaceHandler(ctx)
        self._stop = StopWorkspaceHandler(ctx)
        self._switch = SwitchWorkspaceHandler(ctx)
        self._task = TaskHandler(ctx)
        self._update = SelfUpdateHandler(ctx)

        # Map action names to executor methods.
        method_map: Dict[str, Callable] = {
            "show_help": self._exec_help,
            "show_status": self._exec_status,
            "show_workspace_dashboard": self._exec_dashboard,
            "switch_workspace": self._exec_switch,
            "start_workspace": self._exec_start,
            "stop_workspace": self._exec_stop,
            "send_task": self._exec_task,
            "self_update": self._exec_self_update,
            "confirm_self_update": self._exec_confirmed_self_update,
        }

        # Build _registry from the global CommandRegistry so log_msg stays in sync.
        registry = get_registry()
        self._registry: Dict[str, tuple[Callable, str]] = {}
        for action, method in method_map.items():
            entry = registry.get(action)
            log_msg = entry.log_msg if entry else "执行完成"
            self._registry[action] = (method, log_msg)

    def execute(
        self,
        plan: ActionPlan,
        chat_id: str,
        message_id: str,
        ctx: ConversationContext,
        thinking_mid: Optional[str] = None,
    ) -> None:
        """Execute an ActionPlan by dispatching to the registered handler."""
        logger.debug("Executing plan: %s", plan)
        entry = self._registry.get(plan.action)
        if entry:
            handler_fn, log_msg = entry
            handler_fn(plan, chat_id, message_id, ctx)
            ctx.push("bot", log_msg)
        else:
            logger.warning("Unknown action: %s", plan.action)
            self.ctx.messaging.reply_text(message_id, f"未知动作: {plan.action}")

    def _exec_help(
        self, plan: ActionPlan, chat_id: str, mid: str, ctx: ConversationContext
    ) -> None:
        self._help.handle(chat_id, mid)

    def _exec_status(
        self, plan: ActionPlan, chat_id: str, mid: str, ctx: ConversationContext
    ) -> None:
        self._status.handle(chat_id, mid, ctx)

    def _exec_dashboard(
        self, plan: ActionPlan, chat_id: str, mid: str, ctx: ConversationContext
    ) -> None:
        self._dashboard.handle(chat_id, mid)

    def _exec_switch(
        self, plan: ActionPlan, chat_id: str, mid: str, ctx: ConversationContext
    ) -> None:
        path = plan.params.get("path")
        if path:
            self._switch.handle(chat_id, mid, ctx, path)
        else:
            self.ctx.messaging.reply_text(mid, "请指定工作区路径")

    def _exec_start(
        self, plan: ActionPlan, chat_id: str, mid: str, ctx: ConversationContext
    ) -> None:
        self._start.handle(
            chat_id,
            mid,
            ctx,
            path=plan.params.get("path"),
            project_slug=plan.params.get("project"),
        )

    def _exec_stop(
        self, plan: ActionPlan, chat_id: str, mid: str, ctx: ConversationContext
    ) -> None:
        self._stop.handle(chat_id, mid, ctx, path=plan.params.get("path"))

    def _exec_task(
        self, plan: ActionPlan, chat_id: str, mid: str, ctx: ConversationContext
    ) -> None:
        self._task.handle(
            chat_id,
            mid,
            ctx,
            plan.params.get("task", ""),
            path=plan.params.get("path"),
        )

    def _exec_self_update(
        self, plan: ActionPlan, chat_id: str, mid: str, ctx: ConversationContext
    ) -> None:
        trigger = plan.params.get("trigger_source", "manual")
        reason = plan.params.get("reason", "User requested update")
        self._update.handle(chat_id, mid, ctx, reason=f"[{trigger}] {reason}")

    def _exec_confirmed_self_update(
        self, plan: ActionPlan, chat_id: str, mid: str, ctx: ConversationContext
    ) -> None:
        trigger_source = plan.params.get("trigger_source", "manual")
        reason = plan.params.get("reason", "User confirmed update")

        # Save pending update context BEFORE starting the update
        from kimix_lark_bot.self_update_orchestrator import SelfUpdateOrchestrator

        SelfUpdateOrchestrator.save_pending_update(
            chat_id=chat_id,
            reason=f"[{trigger_source}] {reason}",
        )

        def do_self_update():
            result = self.ctx.request_self_update(
                reason=f"[{trigger_source}] {reason} (by {chat_id})",
            )
            if result and result.get("success"):
                card = CardRenderer.result(
                    "更新已启动",
                    f"Bot 即将退出并由 watcher 重启。",
                    success=True,
                )
                self.ctx.messaging.send_card(chat_id, card)
            else:
                # Clear pending update on failure
                SelfUpdateOrchestrator.load_and_clear_pending_update()
                err = result.get("error", "Unknown error") if result else "No response"
                card = CardRenderer.result("更新失败", err, success=False)
                self.ctx.messaging.send_card(chat_id, card)

        threading.Thread(target=do_self_update, daemon=True).start()
        self.ctx.messaging.reply_text(mid, "正在启动更新，请稍候...")
