# -*- coding: utf-8 -*-
# @file bot_watcher.py
# @brief Backward-compatible wrapper around kimix_lark_bot watcher
# ---------------------------------
"""Backward-compatible wrapper.

Legacy usage:
    python bot_watcher.py -c bot.yaml

This simply forwards to the built-in watcher shipped with the library:
    kimix_lark_bot --support-update -c bot.yaml
"""

import sys

from kimix_lark_bot.__main__ import main

if __name__ == "__main__":
    # Inject --support-update so the library enters watcher mode
    if "--support-update" not in sys.argv:
        sys.argv.insert(1, "--support-update")
    sys.exit(main())
