"""Main entry point and configuration loader for the Zyra bot.

This script is responsible for loading the configuration from `config.toml`,
setting up logging, and initializing the bot's main execution loop.
"""

import logging
import sys
from pathlib import Path
from typing import Any, MutableMapping

import tomli

from . import loader, log


def load_config(path: str = "config.toml") -> MutableMapping[str, Any]:
    """Loads the bot configuration from a TOML file.

    Args:
        path: The file path to the configuration file. Defaults to "config.toml".

    Returns:
        A mutable mapping (dictionary) containing the parsed configuration.

    Raises:
        FileNotFoundError: If the specified config file does not exist.
    """
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    with cfg_path.open("rb") as f:
        return tomli.load(f)


def main() -> None:
    """Main entry point for the Zyra bot launcher.

    This function orchestrates the bot's startup sequence:
    1. Loads the configuration.
    2. Sets up logging (with optional color support).
    3. Hands over control to the loader to start the bot.
    """
    config = load_config()
    logs = logging.getLogger("Loader")

    if not config:
        logs.error("'config.toml' is missing. Configure before running the bot.")
        sys.exit(1)

    # Use config flag if present; default False
    log.setup_log(config.get("bot", {}).get("colorlog", False))
    logs.info("Loading code")
    loader.main(config)


if __name__ == "__main__":
    main()
