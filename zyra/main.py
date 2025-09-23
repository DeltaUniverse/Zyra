import logging
import sys
from pathlib import Path
from typing import Any, MutableMapping

import tomli

from . import loader, log


def load_config(path: str = "config.toml") -> MutableMapping[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    with cfg_path.open("rb") as f:
        return tomli.load(f)


def main() -> None:
    config = load_config()
    logs = logging.getLogger("Loader")
    if not config:
        logs.error("'config.toml' is missing. Configure before running the bot.")
        sys.exit(1)

    log.setup_log(config.get("bot", {}).get("colorlog", False))
    logs.info("Loading code")
    loader.main(config)


if __name__ == "__main__":
    main()
