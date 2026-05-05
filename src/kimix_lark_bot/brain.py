# -*- coding: utf-8 -*-
# @file brain.py
# @brief Bot brain with LLM intent recognition
# @author sailing-innocent
# @date 2026-04-06
# @version 2.0
# ---------------------------------
"""Bot brain with LLM-driven intent recognition.

This module provides the BotBrain class for converting user text
into structured ActionPlan objects using LLM or deterministic matching.

v2.0: Keyword maps are built dynamically from CommandRegistry so that
new commands automatically participate in deterministic matching.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from kimix_lark_bot.context import (
    ConversationContext,
    ActionPlan,
    PendingConfirmation,
)
from kimix_lark_bot.opencode import extract_path_from_text
import logging

logger = logging.getLogger(__name__)

_CONFIRM_WORDS = {
    "是",
    "是的",
    "确认",
    "确定",
    "y",
    "yes",
    "ok",
    "好",
    "行",
    "可以",
    "没错",
    "对",
    "对的",
}
_CANCEL_WORDS = {"否", "不是", "取消", "不", "n", "no", "算了", "别", "不要", "拒绝"}


class BotBrain:
    """LLM-driven intent recognizer for the Feishu bot.

    Converts raw user text + conversation context into a structured ActionPlan.
    Falls back to deterministic keyword matching when LLM is unavailable.
    """

    _CONFIRM_TTL = timedelta(minutes=5)

    def __init__(
        self,
        projects: List[Dict[str, str]],
    ):
        self.projects = projects
        # Dynamic keyword maps from the central registry
        from kimix_lark_bot.commands import get_registry

        self._registry = get_registry()
        self._exact_map = self._registry.build_exact_keyword_map()
        self._fuzzy_map = self._registry.build_fuzzy_keyword_map()

    def think(self, text: str, ctx: ConversationContext) -> ActionPlan:
        """Main entry: text + context → ActionPlan.

        渐进式意图识别策略:
        Level 1: 快速 regex/关键词匹配 (可靠、快速)
        Level 2: LLM 语义理解 (复杂意图)
        Level 3: 优雅降级到通用 chat
        """
        # Level 1: 先尝试确定性匹配
        plan = self._think_deterministic(text, ctx)
        if plan.action != "chat":
            # 确定性匹配成功，直接返回
            from kimix_lark_bot.log_formatter import brain

            brain(f"Level 1 matched: {plan.action}")
            return plan
        # TODO: Level 2 - LLM 语义理解（目前未实现，直接降级）
        # Level 3: 优雅降级 - 返回通用 chat
        brain("Level 3 fallback to chat")
        return self._create_fallback_plan(text, ctx)

    async def think_with_feedback(
        self,
        text: str,
        ctx: ConversationContext,
        chat_id: str,
        message_id: str,
        agent: "FeishuBotAgent",  # noqa: F821
        use_thinking_card: bool = True,
    ) -> tuple[ActionPlan, Optional[str]]:
        """Think with UX feedback - returns (ActionPlan, thinking_card_message_id or None).

        渐进式识别流程:
        1. 先尝试 regex 匹配 (不显示 thinking card)
        2. regex 失败才显示 thinking card 并调用 LLM
        3. LLM 失败优雅降级
        """
        # Resolve messaging client from agent
        messaging = agent.messaging
        # Level 1: 先尝试确定性匹配 (不显示 thinking card)
        plan = self._think_deterministic(text, ctx)
        if plan.action != "chat":
            logger.info(f"[BotBrain] Level 1 matched (no LLM needed): {plan.action}")
            return plan, None

        # Level 2: 需要 LLM，显示 thinking card
        # TODO: 实际调用 LLM 进行语义理解，目前直接降级
        thinking_mid = None

        plan = self._create_fallback_plan(text, ctx)
        return plan, thinking_mid

    def _create_fallback_plan(self, text: str, ctx: ConversationContext) -> ActionPlan:
        """创建优雅降级的 chat 响应。"""
        # 根据当前状态提供更智能的提示
        if ctx.mode == "coding" and ctx.active_workspace:
            return ActionPlan(
                action="send_task",
                params={"task": text, "path": ctx.active_workspace},
            )

        # Build hint from registry so examples stay in sync
        registry = self._registry
        start_kw = "启动"
        start_entry = registry.get("start_workspace")
        if start_entry and start_entry.fuzzy_keywords:
            start_kw = start_entry.fuzzy_keywords[0]
        status_kw = "状态"
        status_entry = registry.get("show_status")
        if status_entry and status_entry.exact_keywords:
            status_kw = status_entry.exact_keywords[0]

        return ActionPlan(
            action="chat",
            reply=(
                f"我可以帮你控制 Agent 开发环境。试试这些指令：\n"
                f"• {start_kw} sailzen\n"
                f"• {start_kw} ~/projects/myapp\n"
                f"• {status_kw}\n"
                f"• 帮我写代码...\n\n"
                f"或者直接描述你需要做什么。"
            ),
        )

    def build_confirmation(
        self,
        action: str,
        params: Dict[str, Any],
        summary: str,
        ctx: ConversationContext,
    ) -> PendingConfirmation:
        return PendingConfirmation(
            action=action,
            params=params,
            summary=summary,
            expires_at=datetime.now() + self._CONFIRM_TTL,
        )

    def check_confirmation_reply(self, text: str) -> Optional[bool]:
        """Return True=confirmed, False=cancelled, None=unrelated."""
        t = text.strip().lower()
        if t in _CONFIRM_WORDS:
            return True
        if t in _CANCEL_WORDS:
            return False
        return None

    def _think_deterministic(self, text: str, ctx: ConversationContext) -> ActionPlan:
        """确定性意图识别 - 基于当前状态进行不同的处理逻辑。

        状态1 - 不在工作区（idle）:
            正常执行三级意图匹配（关键词 → LLM → 降级）

        状态2 - 在工作区（coding）:
            绝大部分消息直接转发给Agent
            只有以感叹号开头的消息才在Bot层执行控制指令
        """
        t = text.lower().strip()

        # === 状态2：在工作区 ===
        if ctx.mode == "coding" and ctx.active_workspace:
            # 感叹号开头的消息 -> 在Bot层执行控制指令（去掉感叹号后的内容）
            if t.startswith("!") or t.startswith("！"):
                cmd_text = text.lstrip("!！").strip()
                cmd_lower = cmd_text.lower()

                # 1) 精确匹配
                for kw, action in self._exact_map.items():
                    if cmd_lower == kw:
                        return ActionPlan(action=action, params={})

                # 2) 模糊匹配（包含关键词）+ path 提取
                for kw, action in self._fuzzy_map.items():
                    if kw in cmd_lower:
                        plan = self._build_plan_for_action(action, cmd_text)
                        if plan:
                            return plan

                # 不认识的指令 -> 提示用户
                available = self._build_available_commands_hint()
                return ActionPlan(
                    action="chat",
                    reply=f"未知的控制指令: {cmd_text}\n\n可用的控制指令:\n{available}",
                )

            # 非感叹号开头的消息 -> 直接转发给Agent
            return ActionPlan(
                action="send_task", params={"task": text, "path": ctx.active_workspace}
            )

        # === 状态1：不在工作区（idle）===
        # Level 1: 精确匹配
        for kw, action in self._exact_map.items():
            if t == kw:
                return ActionPlan(action=action, params={})

        # Level 1: 模糊匹配 + path 提取
        for kw, action in self._fuzzy_map.items():
            if kw in t:
                plan = self._build_plan_for_action(action, text)
                if plan:
                    return plan

        # 返回 chat action 表示需要 LLM 处理（Level 2）
        return ActionPlan(action="chat")

    def _build_plan_for_action(self, action: str, text: str) -> Optional[ActionPlan]:
        """Build an ActionPlan for a fuzzy-matched action.

        Handles path extraction and special per-action rules (confirm, etc.).
        Returns None when the match should be skipped (e.g. switch without path).
        """
        entry = self._registry.get(action)
        path = extract_path_from_text(text, self.projects)
        params: Dict[str, Any] = {}
        if path:
            params["path"] = path

        # switch_workspace requires a path
        if action == "switch_workspace" and not path:
            return None

        plan = ActionPlan(action=action, params=params)

        # stop_workspace always needs confirmation
        if action == "stop_workspace":
            plan.confirm_required = True
            plan.confirm_summary = f"停止 {'所有会话' if not path else path}"

        # self_update confirmations are handled by the handler itself,
        # but we can flag it here if the registry says so.
        if entry and entry.confirm_required and action != "stop_workspace":
            plan.confirm_required = True
            plan.confirm_summary = entry.confirm_summary_template or f"确认执行 {entry.title}"

        return plan

    def _build_available_commands_hint(self) -> str:
        """Build a bullet list of visible commands for unknown-command replies."""
        lines: List[str] = []
        for entry in self._registry.list_visible():
            kws = entry.exact_keywords or entry.fuzzy_keywords[:2]
            if not kws:
                continue
            prefix = "!"
            lines.append(f"• {prefix}{kws[0]} - {entry.description}")
        return "\n".join(lines)
