from typing import TYPE_CHECKING, Any

ZyraBase: Any
if TYPE_CHECKING:
    from .bot import Zyra

    ZyraBase = Zyra

else:
    import abc

    ZyraBase = abc.ABC
