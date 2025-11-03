import logging
import sys

from .util.config import ZyraConfig


def setup_logging(enable_color: bool = False) -> None:

    level = logging.INFO
    logging.root.setLevel(level)

    file_format = "[ %(asctime)s: %(levelname)-8s ] %(name)-15s - %(message)s"
    logfile = logging.FileHandler("zyra/zyra.log")
    file_formatter = logging.Formatter(file_format, datefmt="%H:%M:%S")
    logfile.setFormatter(file_formatter)
    logfile.setLevel(level)

    if enable_color:
        import colorlog

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
        config = ZyraConfig()
    except SystemExit as e:
        print(f"Configuration Error: {e}")
        sys.exit(1)

    if not config:
        log.error("Configuration is empty or invalid")
        sys.exit(1)

    setup_logging(config.get("bot", {}).get("colorlog", False))
    log.info("Configuration loaded")

    from .loader import run_bot

    run_bot(config)
