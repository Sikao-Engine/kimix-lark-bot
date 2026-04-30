import argparse
import sys
from pathlib import Path
from kimix_lark_bot.config import create_default_config, load_config
from kimix_lark_bot.agent import FeishuBotAgent

# ---------------------------------------------------------------------------
# Worker logic
# ---------------------------------------------------------------------------


def run_worker(config_path: str, restore_state: bool = False) -> int:
    """Run the actual bot worker process.

    Returns:
        0 for normal exit, 42 for self-update restart
    """
    if not Path(config_path).exists():
        print(f"Config not found: {config_path}")
        create_default_config(config_path)
        print(f"\nPlease edit: {config_path}")
        return 1

    config = load_config(config_path)
    agent = FeishuBotAgent(config)
    return agent.run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Main entry point.

    With ``--support-update`` the current process acts as a watcher
    that supervises a child worker process.  The worker is restarted
    automatically when it exits with code 42 (after ``git pull``) or
    on crash (with exponential backoff).  Exit code 0 means normal
    shutdown and the watcher stops.
    """
    parser = argparse.ArgumentParser(
        description="Feishu OpenCode Bridge - Connect Feishu messages to OpenCode sessions"
    )
    parser.add_argument(
        "--config", "-c", default="bot.yaml", help="Config file path"
    )
    parser.add_argument(
        "--init", action="store_true", help="Create default config and exit"
    )
    parser.add_argument(
        "--restore-state",
        action="store_true",
        help="Restore state from backup (internal use)",
    )
    parser.add_argument(
        "--support-update",
        action="store_true",
        help=(
            "Run in watcher mode: supervise the bot worker, "
            "restart on exit code 42 after git pull"
        ),
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=5,
        help="Maximum consecutive restarts in watcher mode (default: 5)",
    )
    args = parser.parse_args()
    config_path = args.config
    config_path_obj = Path(config_path)
    if not config_path_obj.exists() and not config_path_obj.is_absolute():
        fallback = Path(__file__).parent.parent.parent / config_path
        if fallback.exists():
            config_path = str(fallback)
    if args.init:
        create_default_config(config_path)
        return 0

    if args.support_update:
        from kimix_lark_bot.watcher import BotWatcher

        extra: list[str] = []
        if args.restore_state:
            extra.append("--restore-state")

        watcher = BotWatcher(
            config_path=config_path,
            max_restarts=args.max_restarts,
            extra_args=extra,
        )
        try:
            watcher.run()
        except KeyboardInterrupt:
            print("\n[Watcher] Stopped by user")
        return 0

    return run_worker(config_path, restore_state=args.restore_state)


if __name__ == "__main__":
    sys.exit(main())
