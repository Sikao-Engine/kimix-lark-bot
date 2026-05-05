# -*- coding: utf-8 -*-
# @file __init__.py
# @brief Command registry initialisation — single source of truth for bot commands
# @date 2026-04-26
# ---------------------------------
"""Command registry bootstrap.

Importing this module populates the global ``CommandRegistry`` with every
command the bot supports.  New commands only need to be added here.
"""

from kimix_lark_bot.commands.registry import CommandRegistry, CommandEntry


def _bootstrap() -> CommandRegistry:
    r = CommandRegistry()

    # ------------------------------------------------------------------
    # Information
    # ------------------------------------------------------------------
    r.register(
        CommandEntry(
            action="show_help",
            exact_keywords=["帮助", "help"],
            title="帮助",
            description="显示帮助信息",
            examples=["帮助", "help", "!帮助"],
            category="信息",
            format_hint="帮助",
            log_msg="显示帮助信息",
        )
    )

    r.register(
        CommandEntry(
            action="show_status",
            exact_keywords=["状态", "status", "s"],
            title="状态",
            description="查看系统状态、工作区连接和最近任务",
            examples=["状态", "status", "!状态", "!s"],
            category="信息",
            format_hint="状态",
            log_msg="状态已显示",
        )
    )

    r.register(
        CommandEntry(
            action="show_workspace_dashboard",
            exact_keywords=["工作区"],
            fuzzy_keywords=["面板", "dashboard", "管理"],
            title="工作区面板",
            description="显示交互式工作区管理面板",
            examples=["工作区", "面板", "管理", "!面板"],
            category="信息",
            format_hint="面板",
            log_msg="显示工作区面板",
        )
    )

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------
    r.register(
        CommandEntry(
            action="start_workspace",
            fuzzy_keywords=["启动", "打开", "开启", "start", "open"],
            title="启动工作区",
            description="启动指定项目的工作区",
            examples=["启动 sailzen", "打开 sz", "start myproject", "!启动 sz"],
            category="工作区",
            format_hint="启动 <项目>",
            log_msg="启动工作区",
        )
    )

    r.register(
        CommandEntry(
            action="stop_workspace",
            fuzzy_keywords=["停止", "关闭", "结束", "stop", "kill"],
            title="停止工作区",
            description="停止当前或指定工作区",
            examples=["停止", "关闭", "stop", "!停止"],
            category="工作区",
            format_hint="停止 <项目>",
            confirm_required=True,
            confirm_summary_template="停止 {target}",
            log_msg="停止工作区",
        )
    )

    r.register(
        CommandEntry(
            action="switch_workspace",
            fuzzy_keywords=[
                "切换",
                "使用",
                "进入",
                "切换到",
                "切到",
                "switch",
                "use",
                "switch to",
                "enter",
            ],
            title="切换工作区",
            description="切换到另一个工作区",
            examples=["切换 sailzen", "使用 sz", "switch myproject", "!切换 sz"],
            category="工作区",
            format_hint="切换 <项目>",
            log_msg="切换工作区",
        )
    )

    # ------------------------------------------------------------------
    # Task
    # ------------------------------------------------------------------
    r.register(
        CommandEntry(
            action="send_task",
            title="发送任务",
            description="向当前工作区发送任务指令（自然语言）",
            examples=["帮我写个函数", "分析一下这个 bug", "重构这段代码"],
            category="任务",
            format_hint="<自然语言描述>",
            log_msg="发送任务",
        )
    )

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------
    r.register(
        CommandEntry(
            action="self_update",
            exact_keywords=[
                "更新",
                "update",
                "升级",
                "upgrade",
                "restart",
                "重启",
                "自更新",
                "更新bot",
                "升级bot",
                "重启bot",
                "update bot",
                "restart bot",
            ],
            title="自更新",
            description="更新或重启 Bot",
            examples=["更新", "restart", "升级", "!更新"],
            category="系统",
            format_hint="更新",
            confirm_required=True,
            log_msg="自更新",
        )
    )

    r.register(
        CommandEntry(
            action="confirm_self_update",
            hidden=True,
            title="确认自更新",
            log_msg="正在执行自更新...",
        )
    )

    return r


# Global singleton instance — populated on first import
_REGISTRY = _bootstrap()


def get_registry() -> CommandRegistry:
    """Return the globally initialised CommandRegistry."""
    return _REGISTRY


__all__ = ["CommandRegistry", "CommandEntry", "get_registry"]
