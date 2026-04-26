# -*- coding: utf-8 -*-
"""Workspace operation handlers: start, stop, switch, exit."""

import threading
import logging
from pathlib import Path

from kimix_lark_bot.context import ActionPlan, ConversationContext
from kimix_lark_bot.card_renderer import (
    result, progress, error, session_status, current_workspace, workspace_selection,
)
from kimix_lark_bot.process_manager import extract_path_from_text

from .base import BaseHandler

logger = logging.getLogger(__name__)


class StartWorkspaceHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        path = plan.params.get("path")
        project_slug = plan.params.get("project")

        if project_slug:
            path = extract_path_from_text(project_slug, self.ctx.config.projects)
        elif path:
            path = extract_path_from_text(path, self.ctx.config.projects)

        if not path:
            logger.info("[%s] No path resolved, showing workspace selection", chat_id)
            projects = self.ctx.config.projects
            state_map = {}
            for proc in self.ctx.process_mgr.list_processes():
                state_map[proc.path] = proc.status.value
            card = workspace_selection(projects, session_states=state_map)
            self.ctx.messaging.reply_card(message_id, card)
            return

        name = Path(path).name
        logger.info("[%s] Starting workspace: %s", chat_id, path)

        op_id = self.ctx.op_tracker.start(path, f"启动 {name}", timeout=30.0)
        prog_card = progress(f"正在启动 {name}", "初始化 Kimix 服务...")
        prog_mid = self.ctx.messaging.reply_card(message_id, prog_card)

        def do_start() -> None:
            stop_event = threading.Event()

            def _poll_progress():
                elapsed = 0
                while not stop_event.wait(3.0):
                    elapsed += 3
                    card = progress(f"正在启动 {name}", f"已等待 {elapsed} 秒，请稍候...")
                    if prog_mid:
                        self.ctx.messaging.update_card(prog_mid, card)

            poll_thread = threading.Thread(target=_poll_progress, daemon=True)
            poll_thread.start()
            try:
                ok, proc, msg = self.ctx.process_mgr.ensure_running(path, chat_id)
            except Exception as exc:
                stop_event.set()
                self.ctx.op_tracker.finish(op_id)
                logger.error("[%s] Exception in start workspace: %s", chat_id, exc, exc_info=True)
                err_card = error("启动异常", str(exc), context_path=path)
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, err_card)
                else:
                    self.ctx.messaging.send_card(chat_id, err_card)
                return
            finally:
                stop_event.set()

            self.ctx.op_tracker.finish(op_id)

            if ok:
                ctx.mode = "coding"
                ctx.active_workspace = proc.path
                ctx.clear_pending()
                self.ctx.save_contexts()

                result_card = session_status(
                    path=proc.path,
                    state="running",
                    port=proc.port,
                    pid=proc.pid,
                )
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, result_card)
                else:
                    self.ctx.messaging.send_card(chat_id, result_card)

                ws_card = current_workspace(proc.path, mode="coding")
                self.ctx.messaging.send_card(chat_id, ws_card)
                ctx.push("bot", "Kimix 已启动: " + proc.path)
                logger.info("[%s] Workspace started: %s port=%s", chat_id, proc.path, proc.port)
            else:
                logger.error("[%s] Failed to start workspace: %s", chat_id, msg)
                err_card = error("启动失败", msg, context_path=path)
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, err_card)
                else:
                    self.ctx.messaging.send_card(chat_id, err_card)

        threading.Thread(target=do_start, daemon=True).start()


class StopWorkspaceHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        path = plan.params.get("path")
        if path:
            path = extract_path_from_text(path, self.ctx.config.projects) or path

        if path:
            name = Path(path).name
            logger.info("[%s] Stopping workspace: %s", chat_id, path)
            ok, msg = self.ctx.process_mgr.stop(path)
            if ok and ctx.active_workspace == path:
                ctx.mode = "idle"
                ctx.active_workspace = None
                ctx.active_session_id = None
                ctx.clear_pending()
                self.ctx.save_contexts()
            card = result("已停止" if ok else "停止失败", f"{name} {'已停止。' if ok else msg}", success=ok)
            self.ctx.messaging.reply_card(message_id, card)
            ctx.push("bot", "已停止: " + path)
        else:
            procs = self.ctx.process_mgr.list_processes()
            if not procs:
                self.ctx.messaging.reply_text(message_id, "没有正在运行的会话。")
                return
            logger.info("[%s] Stopping all workspaces (%d)", chat_id, len(procs))
            results = []
            for p in procs:
                ok, msg = self.ctx.process_mgr.stop(p.path)
                results.append(Path(p.path).name + ": " + ("已停止" if ok else msg))
            ctx.mode = "idle"
            ctx.active_workspace = None
            ctx.active_session_id = None
            ctx.clear_pending()
            self.ctx.save_contexts()
            self.ctx.messaging.reply_card(message_id, result("全部停止", "\n".join(results), success=True))
            ctx.push("bot", "全部停止")


class SwitchWorkspaceHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        path = plan.params.get("path")
        if not path:
            self.ctx.messaging.reply_text(message_id, "请指定工作区路径")
            return
        name = Path(path).name
        logger.info("[%s] Switching workspace to: %s", chat_id, path)
        ctx.mode = "coding"
        ctx.active_workspace = path
        ctx.clear_pending()
        self.ctx.save_contexts()
        card = result(title=f"🔄 已切换到工作区", content=f"**工作区:** {name}\n**路径:** `{path}`", success=True)
        self.ctx.messaging.reply_card(message_id, card)
        ctx.push("bot", f"已切换到工作区: {name}")


class ExitWorkspaceHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        old = ctx.active_workspace
        logger.info("[%s] Exiting workspace: %s", chat_id, old)
        ctx.mode = "idle"
        ctx.active_workspace = None
        ctx.active_session_id = None
        ctx.clear_pending()
        self.ctx.save_contexts()
        self.ctx.messaging.reply_text(message_id, f"已退出工作区{f' ({Path(old).name})' if old else ''}。")
        ctx.push("bot", "已退出工作区")
