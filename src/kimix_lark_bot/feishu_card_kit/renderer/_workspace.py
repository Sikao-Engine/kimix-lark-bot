# -*- coding: utf-8 -*-
# @file _workspace.py
# @brief Workspace / session card renderers
# ---------------------------------
"""Card templates for workspace and session management."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from kimix_lark_bot.feishu_card_kit.core import (
    CardColor,
    ButtonStyle,
    divider,
    text,
    note,
    button,
    action_row,
    field_row,
    card,
    get_state_color,
    get_state_icon,
    get_state_label,
)


class WorkspaceRenderer:
    """Static card templates for workspace and session interactions."""

    # ------------------------------------------------------------------
    # Workspace / Session cards
    # ------------------------------------------------------------------

    @staticmethod
    def workspace_dashboard(
        projects: List[Dict[str, str]],
        session_states: Optional[Dict[str, str]] = None,
        current_workspace: Optional[str] = None,
        text_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an interactive workspace management dashboard.

        Args:
            projects: List of project dicts with keys: slug, label, path
            session_states: Optional dict mapping resolved paths to state strings
            current_workspace: Currently active workspace path
        """
        session_states = session_states or {}
        elements: List[Dict[str, Any]] = [
            text("📱 **手机端完全按钮化操作**", bold=True),
            note("点击下方按钮即可管理工作区，无需输入文字"),
            divider(),
        ]

        for proj in projects:
            slug = proj.get("slug", "")
            label = proj.get("label", slug)
            path = proj.get("path", "")
            resolved = str(Path(path).expanduser()) if path else path
            state = session_states.get(resolved, "idle")
            icon = get_state_icon(state)
            state_label = get_state_label(state)
            is_current = current_workspace == resolved

            # Project info line
            current_marker = " 👈 当前" if is_current else ""
            elements.append(text(f"{icon} **{label}** ({slug}){current_marker}"))
            elements.append(note(f"状态: {state_label}"))

            # Action buttons based on state
            buttons: List[Dict[str, Any]] = []
            if state in ("idle", "error"):
                buttons.append(
                    button(
                        "🚀 启动",
                        "callback",
                        {"action": "btn_start_workspace", "path": resolved},
                        ButtonStyle.PRIMARY,
                    )
                )
            elif state == "running":
                if not is_current:
                    buttons.append(
                        button(
                            "🔀 切换",
                            "callback",
                            {"action": "btn_switch_workspace", "path": resolved},
                            ButtonStyle.PRIMARY,
                        )
                    )
                else:
                    buttons.append(
                        button(
                            "💻 当前",
                            "callback",
                            {"action": "btn_show_dashboard"},
                            ButtonStyle.DEFAULT,
                        )
                    )
                buttons.append(
                    button(
                        "⏹️ 停止",
                        "callback",
                        {"action": "btn_stop_workspace", "path": resolved},
                        ButtonStyle.DANGER,
                    )
                )
            elif state == "starting":
                buttons.append(
                    button(
                        "⏳ 启动中...",
                        "callback",
                        {"action": "btn_show_dashboard"},
                        ButtonStyle.DEFAULT,
                    )
                )

            if buttons:
                elements.append(action_row(buttons))
            elements.append(divider())

        # Global actions
        global_buttons: List[Dict[str, Any]] = [
            button(
                "🔄 刷新状态",
                "callback",
                {"action": "btn_refresh_dashboard"},
                ButtonStyle.DEFAULT,
            ),
        ]

        # Check if any process is running
        has_running = any(
            session_states.get(p.get("path", ""), "idle") == "running" for p in projects
        )
        if has_running:
            global_buttons.append(
                button(
                    "🛑 停止全部",
                    "callback",
                    {"action": "btn_stop_all"},
                    ButtonStyle.DANGER,
                )
            )

        elements.append(action_row(global_buttons))
        hint = text_hint or "💡 也可直接发送文字指令"
        elements.append(note(hint))

        return card(
            elements=elements,
            title="🖥 工作区管理面板",
            color=CardColor.BLUE,
        )

    @staticmethod
    def workspace_selection(
        projects: List[Dict[str, str]],
        session_states: Optional[Dict[str, str]] = None,
        start_verb: str = "启动",
        switch_verb: str = "使用",
    ) -> Dict[str, Any]:
        """Create a workspace selection card.

        Args:
            projects: List of project dicts with keys: slug, label, path
            session_states: Optional dict mapping resolved paths to state strings
            start_verb: Verb shown for starting a workspace (e.g. "启动")
            switch_verb: Verb shown for switching workspace (e.g. "使用")
        """
        session_states = session_states or {}
        elements: List[Dict[str, Any]] = [
            text("📱 手机端快捷指令", bold=True),
            note(f"直接发送「{start_verb} <项目名>」即可快速启动"),
            divider(),
        ]

        for proj in projects:
            slug = proj.get("slug", "")
            label = proj.get("label", slug)
            path = proj.get("path", "")
            resolved = str(Path(path).expanduser()) if path else path
            state = session_states.get(resolved, "idle")
            icon = get_state_icon(state)
            state_label = get_state_label(state)

            elements.append(text(f"{icon} **{label}** ({slug})  |  {state_label}"))

            if state in ("idle", "error"):
                cmd_text = f"发送「{start_verb} {slug}」启动此工作区"
            elif state == "running":
                cmd_text = f"发送「{switch_verb} {slug}」切换到该工作区"
            else:
                cmd_text = f"当前状态: {state_label}"

            elements.append(note(cmd_text))
            elements.append(divider())

        if not projects:
            elements.append(text("暂无配置的工作区"))
        else:
            elements.append(text("💡 提示", bold=True))
            slugs = [p.get("slug", "") for p in projects if p.get("slug")]
            if slugs:
                elements.append(note(f"可用名称: {', '.join(slugs)}"))

        return card(
            elements=elements,
            title="🖥 选择工作区",
            color=CardColor.BLUE,
        )

    @staticmethod
    def session_status(
        path: str,
        state: str,
        port: Optional[int] = None,
        pid: Optional[int] = None,
        last_error: Optional[str] = None,
        activities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a session status card.

        Args:
            path: Workspace path
            state: State string (idle/starting/running/stopping/error)
            port: Optional port number
            pid: Optional process ID
            last_error: Optional error message
            activities: Optional list of recent activity strings
        """
        color = get_state_color(state)
        icon = get_state_icon(state)
        state_label = get_state_label(state)
        name = Path(path).name if path else "未知"

        elements: List[Dict[str, Any]] = [text(f"{icon} **{state_label}**  |  {name}")]

        info_pairs: List = []
        if port:
            info_pairs.append(("端口", str(port)))
        if pid:
            info_pairs.append(("PID", str(pid)))
        if info_pairs:
            elements.append(field_row(info_pairs))

        if last_error:
            elements.append(divider())
            elements.append(text(f"错误：{last_error[:200]}"))

        if activities:
            elements.append(divider())
            elements.append(text("最近活动：", bold=True))
            for act in activities[-5:]:
                elements.append(note(act))

        return card(
            elements=elements,
            title=f"会话状态：{name}",
            color=color,
        )

    @staticmethod
    def all_sessions(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a card listing all sessions.

        Args:
            sessions: List of session dicts with keys: path, state, port
        """
        elements: List[Dict[str, Any]] = []
        if not sessions:
            elements.append(text("暂无会话"))
        else:
            for s in sessions:
                path = s.get("path", "")
                state = s.get("state", "idle")
                port = s.get("port")
                icon = get_state_icon(state)
                name = str(Path(path).name if path else "?")
                state_label = get_state_label(state)
                port_info = f":{port}" if port else ""
                elements.append(text(f"{icon} **{name}**{port_info}  {state_label}"))

        return card(
            elements=elements,
            title="📊 所有会话",
            color=CardColor.BLUE,
        )

    @staticmethod
    def current_workspace(
        path: str,
        mode: str = "coding",
        switch_verb: str = "使用",
        stop_verb: str = "停止",
    ) -> Dict[str, Any]:
        """Create a current workspace indicator card.

        Args:
            path: Current workspace path
            mode: Current mode (coding/idle)
            switch_verb: Verb shown for switching (e.g. "使用")
            stop_verb: Verb shown for stopping (e.g. "停止")
        """
        name = Path(path).name if path else "未知"

        elements: List[Dict[str, Any]] = [
            text(f"🎯 **当前工作区：{name}**", bold=True),
            note("已切换到该工作区，可以直接发送指令"),
            divider(),
            text("💡 **你可以：**"),
            note("• 直接发送任务指令"),
            note(f"• 发送「{switch_verb} <其他项目>」切换"),
            note(f"• 发送「{stop_verb} {name}」停止当前工作区"),
        ]

        return card(
            elements=elements,
            title="🔄 工作区切换成功",
            color=CardColor.GREEN,
        )

    @staticmethod
    def workspace_indicator(path: Optional[str] = None, mode: str = "idle") -> str:
        """Generate a simple text indicator for the current workspace.

        Returns a short markdown string to append to messages.
        """
        if mode == "coding" and path:
            name = Path(path).name
            return f"\n\n---\n💻 当前工作区：{name}"
        return ""
