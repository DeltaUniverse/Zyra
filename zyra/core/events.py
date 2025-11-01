from enum import Enum


class Events(str, Enum):
    MESSAGE = "message"
    CALLBACK_QUERY = "callback_query"
    INLINE_QUERY = "inline_query"
    CHOSEN_INLINE_RESULT = "chosen_inline_result"
    CHAT_ACTION = "chat_action"
    COMMAND = "command"


class Hooks(str, Enum):
    LOAD = "load"
    START = "start"
    STARTED = "started"
    STOP = "stop"
    STOPPED = "stopped"
