import logging

colorlog_enable = True
try:
    import colorlog
except ImportError:
    colorlog_enable = False

level = logging.INFO


def setup_log(colorlog_enable: bool = colorlog_enable) -> None:
    """Configures logging"""
    logging.root.setLevel(level)

    file_format = "[ %(asctime)s: %(levelname)-8s ] %(name)-15s - %(message)s"
    logfile = logging.FileHandler("zyra/zyra.log")
    formatter = logging.Formatter(file_format, datefmt="%H:%M:%S")
    logfile.setFormatter(formatter)
    logfile.setLevel(level)

    if not colorlog_enable:
        formatter = logging.Formatter(
            "  %(levelname)-8s  |  %(name)-11s  |  %(message)s"
        )
    else:
        formatter = colorlog.ColoredFormatter(
            "  %(log_color)s%(levelname)-8s%(reset)s  |  "
            "%(name)-11s  |  %(log_color)s%(message)s%(reset)s"
        )

    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(stream)
    root.addHandler(logfile)

    # Logging necessary for selected libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext._application").setLevel(logging.WARNING)
    logging.getLogger("google.genai").setLevel(logging.ERROR)
