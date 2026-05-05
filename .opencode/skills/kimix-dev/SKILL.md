# Kimix Lark Bot 开发 Skill

> 本 Skill 面向在 `kimix-lark-bot` 项目中处理 SSE 命令流、opencode serve 进程管理、飞书机器人交互的开发者。

---

## 1. 项目定位

`kimix-lark-bot` 是**多个 opencode serve session 的统一控制器 + 飞书机器人交互层**。

- 每个工作区路径对应一个独立的 `opencode serve` 子进程（HTTP + SSE）
- Bot 通过 HTTP API 向 opencode 发指令，通过 SSE `/event` 端点实时监听执行进度
- 所有进度实时回写到飞书卡片（ Lark Card ）

---

## 2. 上游 Kimi-CLI-X 的通信架构

Kimi-CLI-X（`../Kimi-CLI-X`）是底层的 Agent 运行时，提供两种对外通信模式：

### 2.1 Wire 协议 — JSON-RPC over stdio

源码核心：`kimi-cli/src/kimi_cli/wire/server.py`

- **传输**：每行一个 JSON-RPC 2.0 消息（`\n` 分隔），通过 `asyncio.StreamReader/Writer` 读写 stdio
- **Inbound**（客户端 → KimiCLI）：`initialize`, `prompt`, `steer`, `replay`, `set_plan_mode`, `cancel`
- **Outbound**（KimiCLI → 客户端）：`event`, `request`
- **事件类型**（`wire/types.py`）：`TurnBegin/End`, `StepBegin/Interrupted`, `ContentPart`, `StatusUpdate`, `ToolCallRequest`, `ApprovalRequest`, `QuestionRequest`, `HookRequest`, `SubagentEvent` 等
- **序列化**：`wire/serde.py` 负责 WireMessageEnvelope 的序列化/反序列化
- **并发模型**：`WireServer` 内部有 `_read_loop`（解析入站消息并 dispatch）、`_write_loop`（异步写队列）、`_root_hub_loop`（广播 root_wire_hub 事件）

### 2.2 Web 模式 — WebSocket 桥接

源码核心：`kimi-cli/src/kimi_cli/web/runner/process.py` + `web/api/sessions.py`

- `SessionProcess` 启动 KimiCLI 子进程，通过 **stdio JSON-RPC** 与 KimiCLI 交互
- WebSocket 端点 `/api/sessions/{session_id}/stream` 负责与前端通信
- `SessionProcess._read_loop()` 读取子进程 stdout 的 JSON-RPC，`_broadcast()`  fanout 到所有已连接 WebSocket
- 支持 **replay 模式**：新 WebSocket 连接先读取 `wire.jsonl` 历史事件，再进入实时流；实时消息在 replay 期间被缓冲，replay 结束后 flush
- busy 状态由 `_in_flight_prompt_ids` 集合维护，收到 prompt 的 success/error response 后解除

> ⚠️ **关键结论**：Kimi-CLI-X 内部没有原生 SSE，它用 **stdio JSON-RPC** 或 **WebSocket** 对外通信。当前项目的 "SSE" 是 **opencode serve** 在其之上封装出的 HTTP SSE 端点。

---

## 3. 当前项目的 SSE 命令流全链路

### 3.1 进程管理层

文件：`src/kimix_lark_bot/opencode/process_manager.py`

```
工作区路径 → OpenCodeProcessManager.ensure_running() → 启动 opencode serve --port N
                                     ↓
                            ManagedProcess (port, pid, session_id)
                                     ↓
                            状态持久化到 data/bot/state/sessions.json
```

- 每个路径唯一映射一个端口，基础端口默认 `4096`，自动递增
- 启动后通过 `check_health_sync(port)`（`GET /global/health`）轮询就绪
- `get_or_create_api_session(path)` 通过 `POST /session` 创建 opencode session，返回 `session_id`
- 进程日志写入 `data/bot/opencode_logs/agent_{port}.out.log` / `.err.log`

### 3.2 HTTP / SSE 客户端层

文件：`src/kimix_lark_bot/opencode/client.py`

| 方法 | 端点 | 用途 |
|------|------|------|
| `send_prompt_async` | `POST /session/{id}/prompt_async` | Fire-and-forget 发指令 |
| `send_message` | `POST /session/{id}/message` | 阻塞等待 LLM 回复 |
| `stream_events` | `GET /event` | 从**全局 SSE 端点**流式读取 |
| `stream_events_robust` | `GET /event` + 自动重连 | 断线自动重连，yield `__reconnected__` 哨兵 |
| `respond_permission` | `POST /session/{id}/permissions/{perm_id}` | 响应权限请求 |

**SSE 解析内部实现**（`_parse_sse_stream`）：

```python
async for raw_line in response.aiter_lines():
    # 按 SSE 规范解析 event / data / id 字段
    # 空行触发 yield SSEEvent
```

> ⚠️ `/event` 是**全局端点**，会推送所有 session 的事件。必须配合 `sse_parser.parse_event(event, session_id)` 过滤。

### 3.3 SSE 事件解析层

文件：`src/kimix_lark_bot/opencode/sse_parser.py`

解析后的事件类型 `EventType`：

| 类型 | 来源 | 含义 |
|------|------|------|
| `TEXT` / `TEXT_DELTA` | `message.part.updated` / `.delta` | 文本输出 |
| `REASONING` | `message.part.updated` (part_type=reasoning) | 推理过程 |
| `TOOL` | `message.part.updated` (part_type=tool) | 工具调用状态变化 |
| `PERMISSION` | `session.permission` / tool state pending | 权限/确认请求 |
| `STEP_START` / `STEP_FINISH` | `step-start` / `step-finish` | Step 生命周期 |
| `SESSION_IDLE` | `session.idle` / `session.status` (idle) | 任务最终完成 |
| `RECONNECTED` | `__reconnected__` 哨兵 | SSE 断线重连 |
| `SKIP` | 全局事件、其他 session、忽略类型 | 可安全忽略 |

**终端判定**：`ParsedEvent.is_terminal()`
- `SESSION_IDLE` → 终端
- `STEP_FINISH` 且 `reason not in ("tool-calls", "tool_calls")` → 终端（表示 agent 真正结束，而非中间工具调用）

### 3.4 SSE 打印与飞书适配层

文件：`src/kimix_lark_bot/opencode/sse_printer.py`

`SSEPrinter` 职责：
1. **终端可视化**：彩色 ANSI 输出，verbose 模式展开文本，非 verbose 模式进度点号
2. **统计累加**：`SSEStats` 记录耗时、字符数、工具调用、token 消耗、重连次数
3. **外部回调**（`PrinterCallbacks`）：
   - `on_tool(tool_name, status, title, **kwargs)` → 飞书卡片进度更新
   - `on_text(delta, total_chars)` → 文本增量（当前项目未使用，文本由最终 result 汇总）
   - `on_reasoning(total_text, delta, is_final)` → 推理过程滚动采样（每 3s flush）
   - `on_finish(summary, cost, tokens)` → 完成通知
   - `on_permission(permission_id, raw_data)` → 权限请求通知

**工具生命周期追踪**：以 `tool_call_id` 为 key 的 `_tool_registry`，避免同名工具（如多次 `ReadFile`）互相覆盖。

### 3.5 高层执行器

文件：`src/kimix_lark_bot/opencode/session_runner.py`

```python
runner = SessionRunner(port=4096, verbose=True, printer_callbacks=cbs)
result = await runner.run(prompt, session_id, timeout=14400.0)
```

执行流程：
1. `send_prompt_async` 发送指令
2. `stream_events_robust` 监听 SSE
3. `_EventCollector` 收集文本和工具调用
4. 遇到 `is_terminal()` 事件时 break
5. 返回 `RunResult`（success, summary, tool_calls, text_parts, error, elapsed_seconds）

取消机制：`runner.cancel()` → 设置 `_cancel_event` → `run()` 提前返回 `was_cancelled=True`

---

## 4. 飞书交互层

### 4.1 意图识别与指令分发

文件：`src/kimix_lark_bot/brain.py` + `src/kimix_lark_bot/handlers/plan_executor.py`

```
用户消息 → BotBrain.think() → ActionPlan
              ↓
     PlanExecutor.execute() → 各 Handler
```

- **Level 1**：确定性关键词匹配（`commands/registry.py` 维护的 exact/fuzzy map）
- **Level 2**：预留 LLM 语义理解（TODO）
- **Level 3**：降级为通用 chat 或 `send_task`

**双状态模式**：
- `idle`：不在工作区，解析控制指令（启动、状态、停止等）
- `coding`：在工作区中，非 `!` 开头消息直接转发给 Agent，`!` 开头消息在 Bot 层解析为控制指令

### 4.2 任务执行 Handler

文件：`src/kimix_lark_bot/handlers/task_handler.py`

核心流程：
1. `process_mgr.ensure_running_async(path)` 确保 opencode serve 进程就绪
2. `process_mgr.get_or_create_api_session(path)` 获取 session_id
3. 构建 `PrinterCallbacks`（实时更新飞书进度卡片）
4. `SessionRunner.run()` 执行并阻塞直到完成
5. `LongOutputHandler.process()` 处理长文本输出（支持分页卡片）

进度卡片更新策略：
- 工具事件触发立即更新
- 推理文本每 3s 采样更新
- 最少 5s 间隔防抖（`_update_card`）

---

## 5. 关键开发注意事项

### 5.1 SSE 断线与重连

- `stream_events_robust` 在断线时自动重连，最多 `max_reconnects=5` 次
- 每次重连前 yield `SSEEvent(event="__reconnected__", data=str(reconnects))`
- `sse_parser` 将重连哨兵解析为 `EventType.RECONNECTED`
- `SSEPrinter` 统计重连次数并打印警告
- **开发注意**：重连后可能会丢失断线期间的事件，opencode serve 不会补发

### 5.2 全局 /event 端点的 session 过滤

```python
# 错误：直接消费所有事件
async for event in client.stream_events(session_id):
    ...

# 正确：必须用 parse_event(event, session_id) 过滤
async for event in client.stream_events_robust(session_id):
    parsed = parse_event(event, session_id)  # 非本 session 返回 SKIP
    if parsed.type == EventType.SKIP:
        continue
```

### 5.3 取消机制

- `SessionRunner.cancel()` 仅设置本地 `_cancel_event`，**不会调用 opencode 的 abort API**
- 如需强制中断 opencode 执行，需额外调用 `abort_session_sync(session_id, port)` 或 `client.abort_session()`
- `task_handler.py` 中通过 `op_tracker.register_cancel_callback(op_id, runner.cancel)` 注册卡片取消按钮回调

### 5.4 工具调用状态机

opencode 推送的 tool 事件状态序列通常为：
```
pending → running → completed / error
```

- `sse_printer.py` 中 `on_tool` 回调的 `is_done = status in ("completed", "done", "error", "failed")`
- 已完成工具从 `_tool_registry` 移至 `_tool_history`，避免 active tools 列表无限增长

### 5.5 进程生命周期边界

- `opencode serve` 进程由 `OpenCodeProcessManager` 管理，与 opencode **session** 是不同概念
- 一个进程可承载多个 session（但当前项目 `get_or_create_api_session` 每个进程只创建一个）
- 进程崩溃后 `is_alive`（端口探测）返回 False，下次任务会自动重新 `ensure_running`

### 5.6 信任环境变量

所有 `httpx.Client/AsyncClient` 都设置了 `trust_env=False`，防止本地 HTTP_PROXY 等环境变量把 127.0.0.1 连接转发到代理导致失败。

---

## 6. 文件速查表

| 文件 | 职责 |
|------|------|
| `src/kimix_lark_bot/opencode/process_manager.py` | opencode serve 进程启动/停止/健康检查/API session 创建 |
| `src/kimix_lark_bot/opencode/client.py` | HTTP 客户端 + SSE 流读取 + 重连逻辑 |
| `src/kimix_lark_bot/opencode/sse_parser.py` | SSEEvent → ParsedEvent（统一解码两种格式） |
| `src/kimix_lark_bot/opencode/sse_printer.py` | 终端打印 + 飞书回调接口 + 统计 |
| `src/kimix_lark_bot/opencode/session_runner.py` | prompt → SSE stream → RunResult 完整封装 |
| `src/kimix_lark_bot/handlers/task_handler.py` | 飞书任务指令 → 调用 SessionRunner → 更新卡片 |
| `src/kimix_lark_bot/brain.py` | 用户消息 → ActionPlan 意图识别 |
| `src/kimix_lark_bot/handlers/plan_executor.py` | ActionPlan → 具体 handler 分发 |

---

## 7. 上游 Kimi-CLI-X 相关文件速查

| 文件 | 职责 |
|------|------|
| `kimi-cli/src/kimi_cli/wire/server.py` | WireServer — JSON-RPC over stdio 服务端 |
| `kimi-cli/src/kimi_cli/wire/jsonrpc.py` | JSON-RPC 消息模型（Prompt/Steer/Cancel/Event/Request） |
| `kimi-cli/src/kimi_cli/wire/types.py` | Wire 事件类型定义（TurnBegin/End, StepBegin, ContentPart, ApprovalRequest 等） |
| `kimi-cli/src/kimi_cli/wire/serde.py` | WireMessageEnvelope 序列化/反序列化 |
| `kimi-cli/src/kimi_cli/web/runner/process.py` | SessionProcess — KimiCLI 子进程管理 + WebSocket fanout |
| `kimi-cli/src/kimi_cli/web/api/sessions.py` | FastAPI WebSocket 端点 `/api/sessions/{id}/stream` |

---

## 8. 常见调试技巧

1. **查看 opencode 进程日志**：`data/bot/opencode_logs/agent_{port}.err.log`
2. **查看 SSE 原始流**：设置 `logging.getLogger("kimix_lark_bot.opencode.sse_parser").setLevel(logging.DEBUG)`
3. **手动测试 opencode API**：直接 curl `POST /session/{id}/prompt_async` 然后 `GET /event`
4. **模拟重连**：kill opencode serve 进程，观察 `stream_events_robust` 重连行为
5. **检查 session 匹配**：确认 `parse_event(event, session_id)` 中的 `session_id` 与 opencode 返回的一致
