"""Logging configuration for the Zyra bot.

This module sets up the root logger to output to both the console (stream)
and a log file. It supports optional colored logging for the console output.
"""

import logging

import colorlog

level = logging.INFO


def setup_log(colorlog_enable: bool = False) -> None:
    """Configures the root logger for the application.

    This function sets up two handlers: one for writing logs to 'zyra/zyra.log'
    and another for printing logs to the console. It also adjusts the log levels
    for noisy third-party libraries.

    Args:
        colorlog_enable: If True, the console output will be color-coded
            based on the log level.
    """
    logging.root.setLevel(level)

    # File handler setup
    file_format = "[ %(asctime)s: %(levelname)-8s ] %(name)-15s - %(message)s"
    logfile = logging.FileHandler("zyra/zyra.log")
    file_formatter = logging.Formatter(file_format, datefmt="%H:%M:%S")
    logfile.setFormatter(file_formatter)
    logfile.setLevel(level)

    # Stream (console) handler setup
    if not colorlog_enable:
        stream_formatter = logging.Formatter(
            "  %(levelname)-8s  |  %(name)-11s  |  %(message)s"
        )
    else:
        stream_formatter = colorlog.ColoredFormatter(
            "  %(log_color)s%(levelname)-8s%(reset)s  |  "
            "%(name)-11s  |  %(log_color)s%(message)s%(reset)s"
        )

    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(stream_formatter)

    # Add handlers to the root logger
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(stream)
    root.addHandler(logfile)

    # Quieten noisy libraries
    noisy_loggers = [
        ("httpx", logging.ERROR),
        ("httpcore", logging.ERROR),
        ("urllib3", logging.WARNING),
        ("telegram.ext.Application", logging.ERROR),
        ("telegram.ext._application", logging.ERROR),
        ("telegram.ext.Updater", logging.ERROR),
        ("telegram.ext._utils.networkloop", logging.ERROR),
    ]
    for name, lvl in noisy_loggers:
        logging.getLogger(name).setLevel(lvl)
