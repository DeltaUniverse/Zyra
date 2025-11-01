import logging
import sys
from pathlib import Path
from typing import Any, MutableMapping

import tomli


def load_config(path: str = "config.toml") -> MutableMapping[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    with cfg_path.open("rb") as f:
        return tomli.load(f)


def setup_logging(enable_color: bool = False) -> None:
    import colorlog

    level = logging.INFO
    logging.root.setLevel(level)

    file_format = "[ %(asctime)s: %(levelname)-8s ] %(name)-15s - %(message)s"
    logfile = logging.FileHandler("zyra/zyra.log")
    file_formatter = logging.Formatter(file_format, datefmt="%H:%M:%S")
    logfile.setFormatter(file_formatter)
    logfile.setLevel(level)

    if enable_color:
        stream_formatter = colorlog.ColoredFormatter(
            "  %(log_color)s%(levelname)-8s%(reset)s  |  %(name)-11s  |  %(log_color)s%(message)s%(reset)s"
        )
    else:
        stream_formatter = logging.Formatter(
            "  %(levelname)-8s  |  %(name)-11s  |  %(message)s"
        )

    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(stream_formatter)

    root = logging.getLogger()
    root.addHandler(stream)
    root.addHandler(logfile)

    for name, lvl in [
        ("httpx", logging.ERROR),
        ("httpcore", logging.ERROR),
        ("urllib3", logging.WARNING),
        ("telegram.ext.Application", logging.ERROR),
        ("telegram.ext._application", logging.ERROR),
        ("telegram.ext.Updater", logging.ERROR),
        ("telegram.ext._utils.networkloop", logging.ERROR),
    ]:
        logging.getLogger(name).setLevel(lvl)


def main() -> None:
    log = logging.getLogger("Main")

    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not config:
        log.error("config.toml is empty or invalid")
        sys.exit(1)

    setup_logging(config.get("bot", {}).get("colorlog", False))
    log.info("Configuration loaded")

    from .loader import run_bot

    run_bot(config)
