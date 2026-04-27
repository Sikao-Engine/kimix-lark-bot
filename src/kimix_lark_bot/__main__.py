import argparse
import sys
from pathlib import Path
from kimix_lark_bot.config import create_default_config, load_config
from kimix_lark_bot.agent import FeishuBotAgent

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Main entry point.

    Returns:
        Exit code: 0 for normal exit, 42 for self-update restart
    """
    parser = argparse.ArgumentParser(
        description="Feishu OpenCode Bridge - Connect Feishu messages to OpenCode sessions"
    )
    parser.add_argument(
        "--config", "-c", default="code.bot.yaml", help="Config file path"
    )
    parser.add_argument(
        "--init", action="store_true", help="Create default config and exit"
    )
    parser.add_argument(
        "--restore-state",
        action="store_true",
        help="Restore state from backup (internal use)",
    )
    args = parser.parse_args()

    if args.init:
        create_default_config(args.config)
        return 0

    if not Path(args.config).exists():
        print(f"Config not found: {args.config}")
        create_default_config(args.config)
        print(f"\nPlease edit: {args.config}")
        return 1

    config = load_config(args.config)
    agent = FeishuBotAgent(config)
    exit_code = agent.run()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
