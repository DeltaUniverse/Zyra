import logging

import colorlog

level = logging.INFO


def setup_log(colorlog_enable: bool = False) -> None:
    logging.root.setLevel(level)
    file_format = "[ %(asctime)s: %(levelname)-8s ] %(name)-15s - %(message)s"
    logfile = logging.FileHandler("zyra/zyra.log")
    file_formatter = logging.Formatter(file_format, datefmt="%H:%M:%S")
    logfile.setFormatter(file_formatter)
    logfile.setLevel(level)
    if not colorlog_enable:
        stream_formatter = logging.Formatter(
            "  %(levelname)-8s  |  %(name)-11s  |  %(message)s"
        )
    else:
        stream_formatter = colorlog.ColoredFormatter(
            "  %(log_color)s%(levelname)-8s%(reset)s  |  %(name)-11s  |  %(log_color)s%(message)s%(reset)s"
        )

    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(stream_formatter)
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(stream)
    root.addHandler(logfile)
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
