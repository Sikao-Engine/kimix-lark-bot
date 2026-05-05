# -*- coding: utf-8 -*-
# @file sse_printer.py
# @brief SSE 事件终端可视化打印器 + 飞书通知适配
# @author sailing-innocent
# @date 2026-04-25
# @version 1.0
# ---------------------------------
"""kimix_lark_bot.opencode.sse_printer — SSE 事件可视化打印器。

功能:
- 彩色终端输出（ANSI），自动兼容 Windows
- verbose 模式：展开所有文本 / reasoning
- 非 verbose 模式：进度点号 + 里程碑行
- 完整统计摘要（耗时、字符数、工具调用表格、成本）
- 支持外部回调：用于飞书卡片更新等

使用示例::

    from kimix_lark_bot.opencode import OpenCodeAsyncClient, parse_event, SSEPrinter
    from kimix_lark_bot.opencode.sse_parser import EventType

    async with OpenCodeAsyncClient(port=4096) as client:
        printer = SSEPrinter(verbose=True, session_id=session_id)
        async for raw in client.stream_events_robust(session_id):
            parsed = parse_event(raw, session_id)
            printer.handle_event(parsed)
            if parsed.is_terminal():
                break
        printer.print_summary()
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from dataclasses import dataclass
from kimix_lark_bot.opencode.sse_parser import EventType, ParsedEvent


# ── 回调接口 ─────────────────────────────────────────────────────


@dataclass
class PrinterCallbacks:
    """SSEPrinter 的外部回调接口。

    用于将事件通知到飞书卡片等外部系统。
    所有回调均为可选，未设置时不触发。
    """

    on_tool: Optional[Callable[..., None]] = None
    """工具事件回调: fn(tool_name, status, title, **kwargs)
    kwargs 包含: tool_call_id, error, is_done, is_new, tool_info, active_tools, tool_history
    """

    on_text: Optional[Callable[..., None]] = None
    """文本增量回调: fn(delta: str)"""

    on_reasoning: Optional[Callable[..., None]] = None
    """推理滚动采样回调: fn(total_text: str, delta: str, is_final: bool = False)
    每 3 秒触发一次，传递累积的 reasoning 文本和本次采样增量。
    """

    on_finish: Optional[Callable[..., None]] = None
    """完成回调: fn(summary: str)"""

    on_permission: Optional[Callable[..., None]] = None
    """权限请求回调: fn(permission_id: str, raw_data: dict)"""


# ── ANSI 颜色 ─────────────────────────────────────────────────────


class AnsiColor:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"

    @staticmethod
    def strip(text: str) -> str:
        return re.sub(r"\033\[[0-9;]*m", "", text)

    @staticmethod
    def enable_windows_ansi() -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


C = AnsiColor


# ── 辅助函数 ──────────────────────────────────────────────────────


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _truncate(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def format_tool_table(tool_calls: List[Dict[str, Any]]) -> str:
    """将工具调用列表格式化为可读统计表格。"""
    if not tool_calls:
        return "    (无工具调用)"
    lines = []
    tool_summary: Dict[str, Dict[str, int]] = {}
    for tc in tool_calls:
        name = tc.get("name", "?")
        status = tc.get("status", "?")
        if name not in tool_summary:
            tool_summary[name] = {}
        tool_summary[name][status] = tool_summary[name].get(status, 0) + 1

    lines.append(f"    {'工具名':<30s} {'调用情况'}")
    lines.append(f"    {'─' * 30} {'─' * 30}")
    for name, statuses in tool_summary.items():
        parts = [f"{status}×{cnt}" for status, cnt in statuses.items()]
        lines.append(f"    {name:<30s} {', '.join(parts)}")
    lines.append(f"    {'─' * 30} {'─' * 30}")
    lines.append(
        f"    总计: {len(tool_calls)} 次调用, {len(tool_summary)} 种工具"
    )
    return "\n".join(lines)


# ── SSE 统计累加器 ────────────────────────────────────────────────


class SSEStats:
    """累积 SSE 事件统计。"""

    def __init__(self) -> None:
        self.t0 = time.time()
        self.text_chars: int = 0
        self.text_lines: int = 0
        self.reasoning_chars: int = 0
        self.tool_calls: List[Dict[str, Any]] = []
        self.permissions: List[Dict[str, Any]] = []
        self.steps: int = 0
        self.step_finish_reason: str = ""
        self.step_cost: float = 0.0
        self.step_tokens: Dict[str, Any] = {}
        self.reconnects: int = 0
        self.unknown_events: int = 0
        self.event_count: int = 0
        self.last_tool_name: str = ""
        self.last_tool_status: str = ""
        self.errors: List[str] = []

    @property
    def elapsed(self) -> float:
        return time.time() - self.t0

    def elapsed_str(self) -> str:
        e = self.elapsed
        if e < 60:
            return f"{e:.1f}s"
        m, s = divmod(e, 60)
        return f"{int(m)}m{s:.0f}s"


# ── SSE 事件打印器 ────────────────────────────────────────────────


class SSEPrinter:
    """结构化 SSE 事件终端打印器。

    接收 ParsedEvent，以彩色格式输出到终端，并可选地触发外部回调。

    Args:
        verbose:     是否展开所有文本流
        log_file:    可选日志文件路径
        session_id:  当前 session ID
        on_tool:     工具事件回调 fn(tool_name, status, title)
        on_text:     文本增量回调 fn(delta, total_chars)
        on_finish:   完成回调 fn(reason, cost, tokens)
        on_permission: 权限请求回调 fn(permission_id, raw_data)
    """

    REASONING_FLUSH_INTERVAL: float = 3.0

    def __init__(
        self,
        verbose: bool = False,
        log_file: Optional[str] = None,
        session_id: str = "",
        callbacks: Optional[PrinterCallbacks] = None,
        # Legacy individual callbacks (prefer using `callbacks` dataclass)
        on_tool: Optional[Callable[..., None]] = None,
        on_text: Optional[Callable[..., None]] = None,
        on_reasoning: Optional[Callable[..., None]] = None,
        on_finish: Optional[Callable[..., None]] = None,
        on_permission: Optional[Callable[..., None]] = None,
    ) -> None:
        self.verbose = verbose
        self.session_id = session_id
        self.stats = SSEStats()
        self.finished = False
        self.finish_reason = ""
        self.accumulated_text = ""
        self._in_text_block = False
        self._log_fh = None

        # Tool state tracking: keyed by tool_call_id so multiple calls
        # with the same tool_name (e.g. repeated ReadFile) are kept separate.
        self._tool_registry: Dict[str, Dict[str, Any]] = {}
        self._tool_history: List[Dict[str, Any]] = []

        # Reasoning rolling sample buffer
        self._reasoning_buffer: str = ""
        self._reasoning_total: str = ""
        self._last_reasoning_flush: float = 0.0

        # External callbacks: prefer PrinterCallbacks, fallback to individual args
        cb = callbacks or PrinterCallbacks()
        self._on_tool = cb.on_tool or on_tool
        self._on_text = cb.on_text or on_text
        self._on_reasoning = cb.on_reasoning or on_reasoning
        self._on_finish = cb.on_finish or on_finish
        self._on_permission = cb.on_permission or on_permission

        AnsiColor.enable_windows_ansi()

        if log_file:
            self._log_fh = open(log_file, "a", encoding="utf-8")
            self._log_raw("=" * 60)
            self._log_raw(f"SSE session started at {datetime.now().isoformat()}")

    def close(self) -> None:
        self._flush_reasoning(is_final=True)
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None

    def _flush_reasoning(self, is_final: bool = False) -> None:
        """Flush pending reasoning buffer via callback."""
        if not self._reasoning_buffer or not self._on_reasoning:
            return
        try:
            self._on_reasoning(
                self._reasoning_total,
                delta=self._reasoning_buffer,
                is_final=is_final,
            )
        except Exception:
            pass
        self._reasoning_buffer = ""
        self._last_reasoning_flush = time.time()

    # ── 内部输出工具 ──────────────────────────────────────────────

    def _log_raw(self, text: str) -> None:
        if self._log_fh:
            self._log_fh.write(AnsiColor.strip(text) + "\n")
            self._log_fh.flush()

    def _end_text_block(self) -> None:
        if self._in_text_block:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._in_text_block = False

    def _print_line(self, line: str) -> None:
        self._end_text_block()
        print(line)
        self._log_raw(line)

    # ── 主入口 ────────────────────────────────────────────────────

    def handle_event(self, parsed: ParsedEvent) -> None:
        """处理单个已解析的 SSE 事件。"""
        self.stats.event_count += 1
        t = self.stats.elapsed_str()
        etype = parsed.type

        if etype == EventType.SKIP:
            return

        if etype == EventType.RECONNECTED:
            self.stats.reconnects += 1
            self._print_line(
                f"  {C.YELLOW}🔄 [{t}] SSE 重连 #{self.stats.reconnects}{C.RESET}"
            )
            return

        if etype in (EventType.TEXT, EventType.TEXT_DELTA):
            self._handle_text(parsed, t)
            return

        if etype == EventType.REASONING:
            self._handle_reasoning(parsed, t)
            return

        if etype == EventType.TOOL:
            self._handle_tool(parsed, t)
            return

        if etype == EventType.PERMISSION:
            self._handle_permission(parsed, t)
            return

        if etype == EventType.STEP_START:
            self.stats.steps += 1
            self._print_line(
                f"  {C.GRAY}[{t}]{C.RESET} "
                f"{C.BLUE}{C.BOLD}▶ step-start{C.RESET} "
                f"{C.DIM}(step #{self.stats.steps}){C.RESET}"
            )
            return

        if etype == EventType.STEP_FINISH:
            self._handle_step_finish(parsed, t)
            return

        if etype == EventType.SESSION_IDLE:
            if self._in_text_block:
                sys.stdout.write(f" {C.DIM}({self.stats.text_chars}c){C.RESET}\n")
                sys.stdout.flush()
                self._in_text_block = False
            self.finished = True
            self.finish_reason = "session_idle"
            self.stats.step_finish_reason = "session_idle"
            self._print_line(
                f"  {C.GRAY}[{t}]{C.RESET} "
                f"{C.GREEN}{C.BOLD}✅ session idle (任务完成){C.RESET}"
            )
            if self._on_finish:
                try:
                    self._on_finish("session_idle", self.stats.step_cost, self.stats.step_tokens)
                except Exception:
                    pass
            return

        # UNKNOWN
        self.stats.unknown_events += 1

    # ── 事件类型处理器 ─────────────────────────────────────────────

    def _handle_text(self, parsed: ParsedEvent, t: str) -> None:
        txt = parsed.delta or parsed.text
        if not txt:
            return

        if parsed.delta:
            self.accumulated_text += parsed.delta
        elif parsed.text and not self.accumulated_text:
            self.accumulated_text = parsed.text

        self.stats.text_chars += len(txt)
        self.stats.text_lines += txt.count("\n")

        if self._on_text:
            try:
                self._on_text(txt, self.stats.text_chars)
            except Exception:
                pass

        if self.verbose:
            if not self._in_text_block:
                sys.stdout.write(f"  {C.GRAY}[{t}]{C.RESET} {C.DIM}📝 text:{C.RESET} ")
                self._in_text_block = True
            sys.stdout.write(txt)
            sys.stdout.flush()
        else:
            if not self._in_text_block:
                self._in_text_block = True
                sys.stdout.write(f"  {C.GRAY}[{t}]{C.RESET} {C.DIM}📝 text streaming ")
                sys.stdout.flush()
            dots = self.stats.text_chars // 500
            prev_dots = (self.stats.text_chars - len(txt)) // 500
            if dots > prev_dots:
                sys.stdout.write("·")
                sys.stdout.flush()

    def _handle_reasoning(self, parsed: ParsedEvent, t: str) -> None:
        txt = parsed.text
        if not txt:
            return
        self.stats.reasoning_chars += len(txt)

        # Rolling sample: accumulate into buffer, flush every 3s
        self._reasoning_buffer += txt
        self._reasoning_total += txt
        now = time.time()
        if now - self._last_reasoning_flush >= self.REASONING_FLUSH_INTERVAL:
            self._flush_reasoning(is_final=False)

        if self.verbose:
            if not self._in_text_block:
                sys.stdout.write(f"  {C.GRAY}[{t}]{C.RESET} {C.GRAY}💭 reasoning:{C.RESET} ")
                self._in_text_block = True
            sys.stdout.write(f"{C.GRAY}{txt}{C.RESET}")
            sys.stdout.flush()

    def _handle_tool(self, parsed: ParsedEvent, t: str) -> None:
        tool_name = parsed.tool_name
        status = parsed.tool_status
        title = parsed.tool_title or tool_name
        call_id = parsed.tool_call_id or tool_name
        error = parsed.raw.get("state", {}).get("error", "") if parsed.raw else ""
        tool_input = parsed.tool_input or ""

        # Track tool lifecycle by call_id so repeated tools don't overwrite each other.
        is_new = call_id not in self._tool_registry
        prev_status = self._tool_registry.get(call_id, {}).get("status", "")

        tool_info = {
            "call_id": call_id,
            "name": tool_name,
            "status": status,
            "title": title,
            "error": error,
            "input": tool_input,
            "time": t,
            "updated_at": time.time(),
        }
        self._tool_registry[call_id] = tool_info
        self.stats.last_tool_name = tool_name
        self.stats.last_tool_status = status

        if status in ("completed", "done", "error", "failed"):
            if error and status in ("error", "failed"):
                self.stats.errors.append(f"{tool_name}({call_id}): {error}")
            # Move finished tool from active registry to history
            finished_tool = self._tool_registry.pop(call_id)
            self._tool_history.append(finished_tool)
            self.stats.tool_calls.append(finished_tool)
        else:
            self.stats.tool_calls.append(tool_info)

        if status == "pending":
            icon, color = "⏳", C.GRAY
        elif status == "running":
            icon, color = "⚙️ ", C.CYAN
        elif status in ("completed", "done"):
            icon, color = "✅", C.GREEN
        elif status in ("error", "failed"):
            icon, color = "❌", C.RED
        else:
            icon, color = "🔧", C.WHITE

        # Only print to terminal when status changes to avoid noise
        if status != prev_status or is_new or self.verbose:
            line = (
                f"  {C.GRAY}[{t}]{C.RESET} "
                f"{icon} {color}{title}{C.RESET}"
                f" → {color}{status}{C.RESET}"
                f" {C.DIM}(id={call_id[:20]}){C.RESET}"
            )
            if error:
                line += f"  {C.RED}err: {_truncate(error, 60)}{C.RESET}"
            self._print_line(line)

        if self._on_tool:
            try:
                is_done = status in ("completed", "done", "error", "failed")
                self._on_tool(
                    tool_name,
                    status,
                    title,
                    tool_call_id=call_id,
                    error=error,
                    is_done=is_done,
                    is_new=is_new,
                    tool_info=tool_info,
                    active_tools=list(self._tool_registry.values()),
                    tool_history=self._tool_history,
                )
            except Exception:
                pass

    def _handle_permission(self, parsed: ParsedEvent, t: str) -> None:
        perm_id = parsed.permission_id
        self.stats.permissions.append({"id": perm_id, "time": t, "data": parsed.raw})
        self._print_line(
            f"  {C.GRAY}[{t}]{C.RESET} "
            f"{C.BG_YELLOW}{C.BOLD} 🔒 PERMISSION REQUEST {C.RESET} "
            f"id={C.YELLOW}{perm_id[:20] if perm_id else 'N/A'}{C.RESET}"
        )
        if self._on_permission:
            try:
                self._on_permission(perm_id, parsed.raw)
            except Exception:
                pass

    def _handle_step_finish(self, parsed: ParsedEvent, t: str) -> None:
        reason = parsed.text
        cost = parsed.cost
        tokens = parsed.tokens
        is_terminal = parsed.is_terminal()

        if is_terminal and self._in_text_block:
            sys.stdout.write(f" {C.DIM}({self.stats.text_chars}c){C.RESET}\n")
            sys.stdout.flush()
            self._in_text_block = False

        if is_terminal:
            self.finished = True
            self.finish_reason = reason or "step-finish"
            self.stats.step_finish_reason = reason

        self.stats.step_cost += cost
        if tokens:
            self.stats.step_tokens = tokens

        token_info = ""
        if tokens:
            inp = tokens.get("input", tokens.get("prompt_tokens", 0))
            out = tokens.get("output", tokens.get("completion_tokens", 0))
            token_info = f", tokens: {inp}→{out}"

        if is_terminal:
            self._flush_reasoning(is_final=True)
            self._print_line(
                f"  {C.GRAY}[{t}]{C.RESET} "
                f"{C.GREEN}{C.BOLD}✅ step-finish{C.RESET} "
                f"{C.DIM}(reason={reason}, cost=${cost:.4f}{token_info}){C.RESET}"
            )
            if self._on_finish:
                try:
                    self._on_finish(reason, self.stats.step_cost, self.stats.step_tokens)
                except Exception:
                    pass
        else:
            self._print_line(
                f"  {C.GRAY}[{t}]{C.RESET} "
                f"{C.YELLOW}🔄 step-finish{C.RESET} "
                f"{C.DIM}(reason={reason} → 等待工具执行{token_info}){C.RESET}"
            )

    # ── 摘要打印 ──────────────────────────────────────────────────

    def print_summary(self, session_id: str = "") -> None:
        s = self.stats
        elapsed = s.elapsed_str()

        print()
        print(f"  {C.BOLD}{'═' * 56}{C.RESET}")
        print(f"  {C.BOLD}  📊 SSE 流统计摘要{C.RESET}")
        print(f"  {C.BOLD}{'═' * 56}{C.RESET}")

        sid = session_id or self.session_id
        if sid:
            print(f"    Session:      {sid[:24]}...")

        print(f"    总耗时:       {elapsed}")
        print(f"    事件总数:     {s.event_count}")
        print()

        print(f"  {C.CYAN}  📝 文本输出{C.RESET}")
        print(f"    字符数:       {s.text_chars:,}")
        print(f"    行数:         {s.text_lines:,}")
        if s.reasoning_chars:
            print(f"    推理字符:     {s.reasoning_chars:,}")
        print()

        print(f"  {C.CYAN}  🔧 工具调用{C.RESET}")
        print(format_tool_table(s.tool_calls))
        print()

        if s.permissions:
            print(f"  {C.YELLOW}  🔒 权限请求: {len(s.permissions)} 次{C.RESET}")
            print()

        if s.errors:
            print(f"  {C.RED}  ❌ 错误: {len(s.errors)} 个{C.RESET}")
            for err in s.errors[-5:]:
                print(f"    {C.RED}• {_truncate(err, 100)}{C.RESET}")
            print()

        if s.step_finish_reason:
            print(f"  {C.GREEN}  ✅ 完成{C.RESET}")
            print(f"    原因:         {s.step_finish_reason}")
            if s.step_cost:
                print(f"    成本:         ${s.step_cost:.4f}")
            if s.step_tokens:
                print(f"    Tokens:       {json.dumps(s.step_tokens)}")
            print()

        print(f"  {C.BOLD}{'═' * 56}{C.RESET}")
        print()

    def get_summary_text(self) -> str:
        """返回纯文本摘要（用于飞书通知）。"""
        s = self.stats
        lines = [
            f"📊 任务摘要 ({s.elapsed_str()})",
            f"  文本: {s.text_chars:,} 字符, {s.text_lines:,} 行",
            f"  工具: {len(s.tool_calls)} 次调用",
        ]
        if s.step_cost:
            lines.append(f"  成本: ${s.step_cost:.4f}")
        if s.errors:
            lines.append(f"  错误: {len(s.errors)} 个")
        if s.step_finish_reason:
            lines.append(f"  完成: {s.step_finish_reason}")
        return "\n".join(lines)
