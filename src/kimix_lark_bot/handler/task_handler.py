# -*- coding: utf-8 -*-
"""Task handler with async SSE streaming."""

import asyncio
import threading
import time
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from kimix_lark_bot.context import ActionPlan, ConversationContext
from kimix_lark_bot.card_renderer import progress, error, streaming_progress, paginated_result, result
from kimix_lark_bot.oc_client.client import OpenCodeAsyncClient, EventType, parse_event

from .base import BaseHandler

logger = logging.getLogger(__name__)

# Minimum interval between card updates (seconds) to respect Feishu rate limits
_CARD_UPDATE_INTERVAL = 2.0


class TaskHandler(BaseHandler):
    """Execute a coding task via OpenCodeAsyncClient with SSE streaming.

    Flow:
    1. ensure_running (sync, in thread) to start the kimix server if needed.
    2. Connect via OpenCodeAsyncClient.
    3. Fire prompt_async (non-blocking).
    4. Consume SSE events, updating the Feishu card in real-time.
    5. On completion, send paginated result cards.
    """

    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        task_text = plan.params.get("task", "")
        path = plan.params.get("path")

        if not path:
            running = [p for p in self.ctx.process_mgr.list_processes() if p.is_alive]
            if not running:
                self.ctx.messaging.reply_card(
                    message_id,
                    error("未找到会话", "没有正在运行的 Kimix 会话。\n请先启动一个，例如：启动 myproject"),
                )
                return
            if len(running) == 1:
                path = running[0].path
            elif ctx.active_workspace:
                path = ctx.active_workspace
            else:
                names = [Path(p.path).name for p in running]
                self.ctx.messaging.reply_text(
                    message_id, "有多个会话运行中：" + ", ".join(names) + "\n请指定工作区",
                )
                return

        name = Path(path).name
        logger.info("[%s] Task in %s: %s", chat_id, name, task_text[:60])

        op_id = self.ctx.op_tracker.start(path, task_text[:60], timeout=14400.0)
        prog_card = progress(
            title="🚀 任务已提交",
            description=f"正在初始化...\n\n**任务:** {task_text[:100]}{'...' if len(task_text) > 100 else ''}",
        )
        prog_mid = self.ctx.messaging.reply_card(message_id, prog_card)

        def _run_async_task() -> None:
            """Run the async task pipeline in a fresh event loop on this thread."""
            try:
                asyncio.run(
                    self._do_task_async(
                        task_text=task_text,
                        path=path,
                        chat_id=chat_id,
                        ctx=ctx,
                        op_id=op_id,
                        prog_mid=prog_mid,
                    )
                )
            except Exception as exc:
                logger.error("[%s] Async task runner error: %s", chat_id, exc, exc_info=True)
                self.ctx.op_tracker.finish(op_id)
                err_card = error("任务异常", str(exc), context_path=path)
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, err_card)
                else:
                    self.ctx.messaging.send_card(chat_id, err_card)

        threading.Thread(target=_run_async_task, daemon=True, name=f"task-{chat_id[:8]}").start()

    # ── Async task core ──────────────────────────────────────────

    async def _do_task_async(
        self,
        task_text: str,
        path: str,
        chat_id: str,
        ctx: ConversationContext,
        op_id: str,
        prog_mid: Optional[str],
    ) -> None:
        # --- Phase 1: ensure kimix server is running (blocking I/O) ---
        loop = asyncio.get_running_loop()
        try:
            ok, proc, start_msg = await loop.run_in_executor(
                None, self.ctx.process_mgr.ensure_running, path, chat_id,
            )
        except Exception as exc:
            self.ctx.op_tracker.finish(op_id)
            logger.error("[%s] Exception ensuring server: %s", chat_id, exc, exc_info=True)
            err_card = error("任务异常", str(exc), context_path=path)
            if prog_mid:
                self.ctx.messaging.update_card(prog_mid, err_card)
            else:
                self.ctx.messaging.send_card(chat_id, err_card)
            return

        if not ok:
            logger.error("[%s] Failed to ensure running: %s", chat_id, start_msg)
            self.ctx.op_tracker.finish(op_id)
            err_card = error("启动失败", start_msg, context_path=path)
            if prog_mid:
                self.ctx.messaging.update_card(prog_mid, err_card)
            return

        ctx.mode = "coding"
        ctx.active_workspace = proc.path
        ctx.clear_pending()
        self.ctx.save_contexts()

        if not task_text:
            self.ctx.op_tracker.finish(op_id)
            card = result("就绪", "Kimix 已就绪，请描述你的任务。", success=True)
            if prog_mid:
                self.ctx.messaging.update_card(prog_mid, card)
            return

        # --- Phase 2: connect & create session ---
        async with OpenCodeAsyncClient(host="127.0.0.1", port=proc.port) as client:
            logger.debug("[%s] Connecting to kimix serve port=%s", chat_id, proc.port)
            if not await client.health_check():
                self.ctx.op_tracker.finish(op_id)
                err_card = error("连接失败", f"无法连接到 Kimix server (port={proc.port})", context_path=path)
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, err_card)
                return

            session_id = ctx.active_session_id
            if not session_id:
                logger.debug("[%s] Creating new session", chat_id)
                sess = await client.create_session(title=f"Lark Bot - {Path(path).name}")
                session_id = sess.id
                ctx.active_session_id = session_id
                self.ctx.save_contexts()
                logger.info("[%s] Session created: %s", chat_id, session_id)
            else:
                logger.debug("[%s] Reusing session: %s", chat_id, session_id)

            # --- Phase 3: fire prompt (non-blocking) & stream SSE ---
            await self._stream_task(
                client=client,
                session_id=session_id,
                task_text=task_text,
                chat_id=chat_id,
                path=path,
                ctx=ctx,
                op_id=op_id,
                prog_mid=prog_mid,
            )

    # ── SSE streaming core ───────────────────────────────────────

    async def _stream_task(
        self,
        client: OpenCodeAsyncClient,
        session_id: str,
        task_text: str,
        chat_id: str,
        path: str,
        ctx: ConversationContext,
        op_id: str,
        prog_mid: Optional[str],
    ) -> None:
        start_time = time.time()

        # Mutable state for progress card
        tools: List[Dict[str, str]] = []
        tool_call_registry: Dict[str, Dict[str, str]] = {}
        reasoning_text = ""
        output_text = ""
        last_update = 0.0

        def _elapsed() -> int:
            return int(time.time() - start_time)

        def _update_card_throttled(force: bool = False) -> None:
            """Update the Feishu card, throttled to avoid rate limits."""
            nonlocal last_update
            now = time.time()
            if not force and (now - last_update) < _CARD_UPDATE_INTERVAL:
                return
            last_update = now
            if not prog_mid:
                return
            card = streaming_progress(
                title=f"⏳ 执行中 ({_elapsed()}s)",
                task_text=task_text,
                elapsed=_elapsed(),
                tools=tools,
                reasoning_snippet=reasoning_text,
                text_snippet=output_text,
            )
            try:
                self.ctx.messaging.update_card(prog_mid, card)
            except Exception as exc:
                logger.warning("[%s] Card update failed: %s", chat_id, exc)

        try:
            logger.debug("[%s] Sending prompt_async: %s", chat_id, task_text[:80])
            ok = await client.send_prompt_async(session_id, task_text)
            if not ok:
                raise RuntimeError("prompt_async returned non-204")

            # Consume SSE events
            async for raw_event in client.stream_events_robust(session_id):
                parsed = parse_event(raw_event, session_id)

                if parsed.type == EventType.SKIP:
                    continue

                if parsed.type == EventType.TEXT:
                    output_text = parsed.text
                    _update_card_throttled()

                elif parsed.type == EventType.TEXT_DELTA:
                    output_text += parsed.delta
                    _update_card_throttled()

                elif parsed.type == EventType.TOOL:
                    call_id = parsed.tool_call_id
                    logger.debug(
                        "[TOOL event] call_id=%r tool_name=%r tool_status=%r registry_keys=%s",
                        call_id, parsed.tool_name, parsed.tool_status, list(tool_call_registry.keys()),
                    )
                    # Maintain registry so we can backfill missing tool names on completion
                    if call_id:
                        if parsed.tool_name and parsed.tool_name != "unknown":
                            tool_call_registry[call_id] = {
                                "name": parsed.tool_name,
                                "title": parsed.tool_title or parsed.tool_name,
                            }
                            logger.debug("[TOOL registry] saved call_id=%r name=%r", call_id, parsed.tool_name)
                        elif call_id in tool_call_registry:
                            old_name = parsed.tool_name
                            parsed.tool_name = tool_call_registry[call_id]["name"]
                            parsed.tool_title = tool_call_registry[call_id]["title"]
                            logger.debug("[TOOL registry] backfilled call_id=%r %r -> %r", call_id, old_name, parsed.tool_name)
                        else:
                            logger.debug("[TOOL registry] no entry for call_id=%r", call_id)

                    tool_entry = {
                        "name": parsed.tool_name,
                        "status": parsed.tool_status,
                        "title": parsed.tool_title,
                        "input": parsed.tool_input,
                        "output": parsed.tool_output,
                        "error": parsed.tool_error,
                        "call_id": call_id,
                    }
                    # Update existing tool entry or add new one
                    updated = False
                    for i, t in enumerate(tools):
                        # Prefer call_id matching; fall back to name + non-terminal status
                        if call_id and t.get("call_id") == call_id:
                            tools[i] = tool_entry
                            updated = True
                            break
                        if t["name"] == parsed.tool_name and t["status"] not in ("completed", "done"):
                            tools[i] = tool_entry
                            updated = True
                            break
                    if not updated:
                        tools.append(tool_entry)
                    _update_card_throttled()

                elif parsed.type == EventType.REASONING:
                    reasoning_text = parsed.text
                    _update_card_throttled()

                elif parsed.type == EventType.STEP_START:
                    _update_card_throttled()

                elif parsed.type == EventType.STEP_FINISH:
                    if parsed.is_terminal():
                        logger.info("[%s] Task finished (reason=%s)", chat_id, parsed.text)
                        break
                    # Non-terminal step finish (e.g. tool_calls) — continue
                    _update_card_throttled()

                elif parsed.type == EventType.SESSION_IDLE:
                    logger.info("[%s] Session idle", chat_id)
                    break

                elif parsed.type == EventType.RECONNECTED:
                    logger.info("[%s] SSE reconnected", chat_id)

        except Exception as exc:
            self.ctx.op_tracker.finish(op_id)
            logger.error("[%s] SSE streaming error: %s", chat_id, exc, exc_info=True)
            err_card = error("执行异常", str(exc), context_path=path)
            if prog_mid:
                self.ctx.messaging.update_card(prog_mid, err_card)
            else:
                self.ctx.messaging.send_card(chat_id, err_card)
            ctx.push("bot", f"任务出错: {str(exc)[:50]}")
            return

        # --- Task completed ---
        self.ctx.op_tracker.finish(op_id)
        elapsed = _elapsed()
        final_text = output_text or "（任务已完成，无输出）"

        # Send paginated results
        cards = paginated_result(
            title=f"✅ 任务完成 ({elapsed}s)",
            content=final_text,
            success=True,
        )

        # First card: update the progress card in-place
        if prog_mid and cards:
            self.ctx.messaging.update_card(prog_mid, cards[0])
            # Additional pages: send as new messages
            for extra_card in cards[1:]:
                self.ctx.messaging.send_card(chat_id, extra_card)
        else:
            for c in cards:
                self.ctx.messaging.send_card(chat_id, c)

        ctx.push("bot", f"任务完成（{elapsed}s）")
        logger.info("[%s] Task completed in %ss, %d page(s)", chat_id, elapsed, len(cards))
