import time
from datetime import timedelta
from typing import Union


def usec() -> int:
    return int(time.time() * 1000000)


def msec() -> int:
    return int(usec() / 1000)


def sec() -> int:
    return int(time.time())


def format_duration_us(t_us: Union[int, float]) -> str:
    t_us = int(t_us)
    if t_us >= 86400000000:
        return f"{t_us // 86400000000}d {(t_us % 86400000000) // 3600000000}h"

    if t_us >= 3600000000:
        return f"{t_us // 3600000000}h {(t_us % 3600000000) // 60000000}m"

    if t_us >= 60000000:
        return f"{t_us // 60000000}m {(t_us % 60000000) // 1000000}s"

    if t_us >= 1000000:
        return f"{t_us // 1000000} sec"

    if t_us >= 1000:
        return f"{t_us // 1000} ms"

    return f"{t_us} μs"


def format_duration_td(value: timedelta, precision: int = 0) -> str:
    pieces = []
    if value.days:
        pieces.append(f"{value.days}d")

    seconds = value.seconds
    if seconds >= 3600:
        hours = int(seconds / 3600)
        pieces.append(f"{hours}h")
        seconds -= hours * 3600

    if seconds >= 60:
        minutes = int(seconds / 60)
        pieces.append(f"{minutes}m")
        seconds -= minutes * 60

    if seconds > 0 or not pieces:
        pieces.append(f"{seconds}s")

    if precision == 0:
        return "".join(pieces)

    return "".join(pieces[:precision])
