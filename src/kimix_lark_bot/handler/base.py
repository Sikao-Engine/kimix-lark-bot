# -*- coding: utf-8 -*-
"""Base infrastructure for handlers."""

import threading
import time
import logging
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from kimix_lark_bot.context import ConversationContext
from kimix_lark_bot.messaging import FeishuMessagingClient
from kimix_lark_bot.process_manager import KimixProcessManager
from kimix_lark_bot.config import AgentConfig
from kimix_lark_bot.brain import BotBrain

logger = logging.getLogger(__name__)


class OperationTracker:
    """Simple operation tracker with timeouts."""

    def __init__(self):
        self._ops: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def start(self, path: str, description: str, timeout: float = 300.0) -> str:
        with self._lock:
            self._counter += 1
            op_id = f"op_{self._counter:04d}"
            self._ops[op_id] = {
                "path": path,
                "description": description,
                "started_at": time.time(),
                "timeout": timeout,
            }
            return op_id

    def finish(self, op_id: str) -> None:
        with self._lock:
            self._ops.pop(op_id, None)

    def is_active(self, op_id: str) -> bool:
        with self._lock:
            op = self._ops.get(op_id)
            if not op:
                return False
            return time.time() - op["started_at"] < op["timeout"]


class HandlerContext:
    def __init__(
        self,
        messaging: FeishuMessagingClient,
        process_mgr: KimixProcessManager,
        brain: BotBrain,
        config: AgentConfig,
        agent: Optional[Any] = None,
    ):
        self.messaging = messaging
        self.process_mgr = process_mgr
        self.brain = brain
        self.config = config
        self.agent = agent
        self.op_tracker = OperationTracker()

    def get_or_create_context(self, chat_id: str) -> ConversationContext:
        if self.agent:
            return self.agent._get_context(chat_id)
        raise NotImplementedError("Agent reference not set")

    def save_contexts(self) -> None:
        if self.agent:
            self.agent._save_contexts()


class BaseHandler:
    def __init__(self, ctx: HandlerContext):
        self.ctx = ctx

    def handle(self, *args, **kwargs) -> Any:
        raise NotImplementedError("Subclasses must implement handle()")


class _MessageDeduplicator:
    def __init__(self, ttl_seconds: int = 300):
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def is_duplicate(self, message_id: str) -> bool:
        now = time.time()
        with self._lock:
            if len(self._seen) > 500:
                cutoff = now - self._ttl
                self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
            if message_id in self._seen:
                return True
            self._seen[message_id] = now
            return False


_dedup = _MessageDeduplicator()
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="msg-handler")
