# -*- coding: utf-8 -*-
# @file watcher.py
# @brief Bot process watcher - built-in supervisor with self-update support
# ---------------------------------
"""Built-in process supervisor for kimix-lark-bot.

Usage (inside library):
    from kimix_lark_bot.watcher import BotWatcher
    watcher = BotWatcher(config_path="bot.yaml")
    watcher.run()

Exit-code contract (shared with worker):
    0:  normal exit, do NOT restart
    42: self-update requested, git pull + restart
    other: error, restart with exponential backoff
"""

import json
import os
import subprocess
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

EXIT_CODE_UPDATE = 42
EXIT_CODE_NORMAL = 0
MAX_RESTART_ATTEMPTS = 5
RESTART_BACKOFF_SECONDS = [1, 2, 5, 10, 30]

logger = logging.getLogger(__name__)


@dataclass
class RestartState:
    """Tracks restart state to prevent infinite loops."""

    restart_count: int = 0
    last_restart_at: Optional[str] = None
    last_exit_code: int = 0
    consecutive_crashes: int = 0
    last_git_pull_at: Optional[str] = None
    git_pull_success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RestartState":
        return cls(**data)


class BotWatcher:
    """Watches and manages the bot worker process lifecycle."""

    def __init__(
        self,
        config_path: str = "bot.yaml",
        state_file: Optional[Path] = None,
        max_restarts: int = MAX_RESTART_ATTEMPTS,
        extra_args: Optional[List[str]] = None,
    ):
        self.config_path = config_path
        self.max_restarts = max_restarts
        self.extra_args = extra_args or []
        self.state_file = (
            state_file or Path.home() / ".sailzen" / "bot_restart_state.json"
        )
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        self.restart_state = self._load_state()
        self._running = False

    # ── state persistence ───────────────────────────────────────────

    def _load_state(self) -> RestartState:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                state = RestartState.from_dict(data)
                if state.last_restart_at:
                    last_time = datetime.fromisoformat(state.last_restart_at)
                    if datetime.now() - last_time > timedelta(hours=1):
                        state.restart_count = 0
                        state.consecutive_crashes = 0
                return state
            except Exception as exc:
                logger.info(f"[Watcher] Failed to load state: {exc}")
        return RestartState()

    def _save_state(self) -> None:
        try:
            self.state_file.write_text(
                json.dumps(self.restart_state.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.info(f"[Watcher] Failed to save state: {exc}")

    # ── git pull ────────────────────────────────────────────────────

    def _perform_git_pull(self) -> bool:
        logger.info("[Watcher] Performing git pull...")
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            repo_root = Path(result.stdout.strip())

            result = subprocess.run(
                ["git", "pull"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )

            self.restart_state.last_git_pull_at = datetime.now().isoformat()

            if result.returncode == 0:
                logger.info("[Watcher] Git pull successful")
                if result.stdout:
                    logger.info(f"[Watcher] Output: {result.stdout.strip()}")
                self.restart_state.git_pull_success = True
                return True
            else:
                logger.info(f"[Watcher] Git pull failed: {result.stderr}")
                self.restart_state.git_pull_success = False
                return False
        except Exception as exc:
            logger.info(f"[Watcher] Git pull error: {exc}")
            self.restart_state.git_pull_success = False
            return False

    # ── worker process ──────────────────────────────────────────────

    def _build_cmd(self) -> List[str]:
        cmd = ["kimix_lark_bot", "-c", self.config_path]
        cmd.extend(self.extra_args)
        return cmd

    def _start_bot(self) -> int:
        cmd = self._build_cmd()
        env = os.environ.copy()
        env["BOT_WATCHER_ENABLED"] = "1"

        logger.info(f"[Watcher] Starting bot: {' '.join(cmd)}")
        logger.info(f"[Watcher] Restart #{self.restart_state.restart_count + 1}")

        process: Optional[subprocess.Popen] = None
        try:
            process = subprocess.Popen(cmd, env=env)
            exit_code = process.wait()
            return exit_code
        except KeyboardInterrupt:
            logger.info("\n[Watcher] Interrupted by user")
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            return EXIT_CODE_NORMAL
        except Exception as exc:
            logger.info(f"[Watcher] Failed to start bot: {exc}")
            return 1

    # ── restart policy ──────────────────────────────────────────────

    def _should_restart(self, exit_code: int) -> bool:
        if exit_code == EXIT_CODE_NORMAL:
            logger.info("[Watcher] Bot exited normally, not restarting")
            return False

        if exit_code == EXIT_CODE_UPDATE:
            logger.info("[Watcher] Bot requested update restart")
            return True

        self.restart_state.consecutive_crashes += 1
        if self.restart_state.consecutive_crashes >= self.max_restarts:
            logger.info(
                f"[Watcher] Too many consecutive crashes "
                f"({self.restart_state.consecutive_crashes}), giving up"
            )
            return False
        return True

    def _get_backoff_delay(self) -> int:
        idx = min(
            self.restart_state.consecutive_crashes - 1,
            len(RESTART_BACKOFF_SECONDS) - 1,
        )
        return RESTART_BACKOFF_SECONDS[idx]

    # ── main loop ───────────────────────────────────────────────────

    def run(self) -> None:
        logger.info("=" * 60)
        logger.info("Bot Watcher Started")
        logger.info(f"Config: {self.config_path}")
        logger.info(f"State file: {self.state_file}")
        logger.info("=" * 60)

        self._running = True
        while self._running:
            self.restart_state.restart_count += 1
            self.restart_state.last_restart_at = datetime.now().isoformat()
            self._save_state()

            exit_code = self._start_bot()
            self.restart_state.last_exit_code = exit_code
            logger.info(f"[Watcher] Bot exited with code: {exit_code}")

            if not self._should_restart(exit_code):
                break

            if exit_code == EXIT_CODE_UPDATE:
                self.restart_state.consecutive_crashes = 0
                git_success = self._perform_git_pull()
                if not git_success:
                    logger.info(
                        "[Watcher] Warning: git pull failed, "
                        "will restart with current code"
                    )
                time.sleep(1)
            else:
                delay = self._get_backoff_delay()
                logger.info(f"[Watcher] Waiting {delay}s before restart...")
                time.sleep(delay)

            self._save_state()

        logger.info("[Watcher] Shutting down")
        self._save_state()
