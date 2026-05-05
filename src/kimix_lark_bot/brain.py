# -*- coding: utf-8 -*-
# @file brain.py
# @brief Bot brain with LLM intent recognition
# @author sailing-innocent
# @date 2026-04-06
# @version 1.1
# ---------------------------------
"""Bot brain with LLM-driven intent recognition.

This module provides the BotBrain class for converting user text
into structured ActionPlan objects using LLM or deterministic matching.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
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


# ---------------------------------------------------------------------------
# LLM-driven brain
# ---------------------------------------------------------------------------

_BRAIN_FALLBACK_ACTIONS = {
    "帮助": ("show_help", {}),
    "help": ("show_help", {}),
    "状态": ("show_status", {}),
    "status": ("show_status", {}),
    # Phase 0: Self-update commands
    "更新": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested update"},
    ),
    "更新bot": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested bot update"},
    ),
    "更新 bots": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested bot update"},
    ),
    "update": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested update"},
    ),
    "update bot": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested bot update"},
    ),
    "升级": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested upgrade"},
    ),
    "升级bot": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested bot upgrade"},
    ),
    "restart": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested restart"},
    ),
    "restart bot": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested bot restart"},
    ),
    "重启": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested restart"},
    ),
    "重启bot": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested bot restart"},
    ),
    "自更新": (
        "self_update",
        {"trigger_source": "manual", "reason": "User requested self-update"},
    ),
}


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
    ) -> Tuple[ActionPlan, Optional[str]]:
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

        return ActionPlan(
            action="chat",
            reply=(
                "我可以帮你控制 Agent 开发环境。试试这些指令：\n"
                "• 打开 sailzen\n"
                "• 启动 ~/projects/myapp\n"
                "• 查看状态\n"
                "• 帮我写代码...\n\n"
                "或者直接描述你需要做什么。"
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

                # 在感叹号模式下，解析控制指令
                # 完全匹配精确指令
                for kw, (action, params) in _BRAIN_FALLBACK_ACTIONS.items():
                    if cmd_lower == kw:
                        return ActionPlan(action=action, params=params)

                # 状态查询指令（!状态 或 !status）
                if cmd_lower in ["状态", "status", "s"]:
                    return ActionPlan(action="show_status", params={})

                # 解析工作区控制指令（启动、停止、切换等）
                if any(
                    k in cmd_lower for k in ["启动", "打开", "开启", "start", "open"]
                ):
                    path = extract_path_from_text(cmd_text, self.projects)
                    return ActionPlan(action="start_workspace", params={"path": path})

                if any(
                    k in cmd_lower for k in ["停止", "关闭", "结束", "stop", "kill"]
                ):
                    path = extract_path_from_text(cmd_text, self.projects)
                    return ActionPlan(
                        action="stop_workspace",
                        params={"path": path},
                        confirm_required=True,
                        confirm_summary=f"停止 {'所有会话' if not path else path}",
                    )

                if any(
                    k in cmd_lower for k in ["切换", "使用", "进入", "switch", "use"]
                ):
                    path = extract_path_from_text(cmd_text, self.projects)
                    if path:
                        return ActionPlan(
                            action="switch_workspace", params={"path": path}
                        )

                # 感叹号开头但不认识的指令 -> 提示用户
                return ActionPlan(
                    action="chat",
                    reply=f"未知的控制指令: {cmd_text}\n\n可用的控制指令:\n• !状态 / !status / !s - 查看当前状态\n• !启动 <项目> - 启动工作区\n• !停止 - 停止工作区\n• !切换 <项目> - 切换工作区\n• !帮助 / !help - 显示帮助",
                )

            # 非感叹号开头的消息 -> 直接转发给Agent
            return ActionPlan(
                action="send_task", params={"task": text, "path": ctx.active_workspace}
            )

        # === 状态1：不在工作区（idle）===
        # Level 1: 精确匹配（完全匹配，无歧义）
        for kw, (action, params) in _BRAIN_FALLBACK_ACTIONS.items():
            if t == kw:
                return ActionPlan(action=action, params=params)

        # 启动指令（进入coding模式）
        if any(k in t for k in ["start", "启动", "开启", "打开", "open"]):
            path = extract_path_from_text(text, self.projects)
            if path:
                return ActionPlan(action="start_workspace", params={"path": path})

        # 停止指令
        if any(k in t for k in ["stop", "停止", "关闭", "结束", "kill"]):
            path = extract_path_from_text(text, self.projects)
            return ActionPlan(
                action="stop_workspace",
                params={"path": path},
                confirm_required=True,
                confirm_summary=f"停止 {'所有会话' if not path else path}",
            )

        # 切换工作区指令
        if any(
            k in t
            for k in ["使用", "进入", "切换到", "切到", "use", "switch to", "enter"]
        ):
            path = extract_path_from_text(text, self.projects)
            if path:
                return ActionPlan(action="switch_workspace", params={"path": path})

        # 返回 chat action 表示需要 LLM 处理（Level 2）
        return ActionPlan(action="chat")
